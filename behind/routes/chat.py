from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, send_file

from ..extensions import db
from ..models import Conversation, Message
from ..models.base import utcnow
from ..services.questionnaire_service import QuestionnaireService
from ..services.ai import (
    GLMServiceError,
    UserInsightContextBuilder,
    custom_prompt_requires_model_intro,
)
from ..services.multimodal_service import MultimodalServiceError, MultimodalServiceUnavailableError
from ..utils.auth import load_current_user, login_required
from ..utils.intervention_requests import (
    TRANSFER_REQUEST_CONTENT_TYPE,
    TRANSFER_REQUEST_MESSAGE,
    get_active_intervention_for_user,
    get_pending_transfer_request_for_user,
)
from ..utils.realtime import (
    emit_intervention_requested,
    emit_message_created,
    emit_questionnaire_updated,
)
from ..utils.serializers import serialize_conversation, serialize_message


chat_bp = Blueprint("chat", __name__, url_prefix="/api")
_chat_context_builder = UserInsightContextBuilder()
_CHAT_RAG_TERM_GROUPS = [
    {"室友", "同学", "朋友", "人际", "关系", "社交", "孤独", "沟通", "相处", "开口"},
    {"焦虑", "紧张", "担心", "不安", "害怕", "心慌"},
    {"睡不着", "失眠", "睡眠", "熬夜", "睡前", "休息"},
    {"压力", "学业", "作业", "考试", "工作", "求职", "任务", "负担"},
    {"恋爱", "分手", "喜欢", "亲密", "爱情"},
    {"家庭", "父母", "家里", "亲人"},
    {"自伤", "自杀", "活不下去", "绝望", "崩溃"},
]


def _get_conversation_or_error(conversation_id: int, allow_admin: bool = True):
    user = load_current_user()
    conversation = Conversation.query.get(conversation_id)
    if conversation is None:
        return None, (jsonify({"message": "会话不存在"}), 404)
    if conversation.user_id != user.id and not (allow_admin and user.role == "admin"):
        return None, (jsonify({"message": "没有权限访问该会话"}), 403)
    return conversation, None


def _get_message_or_error(conversation: Conversation, message_id: int):
    message = Message.query.filter_by(id=message_id, conversation_id=conversation.id).first()
    if message is None:
        return None, (jsonify({"message": "消息不存在"}), 404)
    return message, None


def _get_message_payload():
    if request.files:
        return request.form.to_dict()
    return request.get_json(silent=True) or {}


def _fallback_reply_text(content: str, custom_prompt: str = "", model_name: str = "GLM") -> str:
    prefix = ""
    if custom_prompt_requires_model_intro(custom_prompt):
        prefix = f"我是心陪陪，当前系统默认接入的是 {model_name}。"

    if not content:
        return f"{prefix}我在这里，慢慢说就好。".strip()

    snippet = content[:18]
    if any(keyword in content for keyword in ["睡不着", "失眠", "睡眠"]):
        return f"{prefix}我留意到你提到“{snippet}”，听起来最近休息确实受到了影响，我们先一起把最难熬的那段说清楚。".strip()
    if any(keyword in content for keyword in ["焦虑", "害怕", "慌"]):
        return f"{prefix}我看到你提到“{snippet}”，这种持续绷着的感觉会很累，我们可以先只看眼前最让你不安的一件事。".strip()
    if any(keyword in content for keyword in ["压力", "工作", "求职"]):
        return f"{prefix}关于“{snippet}”这件事，你已经扛了不少。我们可以先把压力来源拆成几块，一次只处理一点。".strip()
    return f"{prefix}我收到你刚刚说的“{snippet}”。如果你愿意，我们可以顺着这里继续慢慢聊。".strip()


def _build_glm_messages(conversation: Conversation, pending_user_text: str) -> list[dict]:
    history_limit = current_app.config.get("GLM_HISTORY_LIMIT", 12)
    existing_messages = (
        Message.query.filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    messages = []
    for item in existing_messages[-history_limit:]:
        if item.sender_type == "user":
            role = "user"
        elif item.sender_type in {"assistant", "human"}:
            role = "assistant"
        elif item.sender_type == "system":
            role = "system"
        else:
            continue

        content = (item.content_text or "").strip()
        if not content:
            continue
        messages.append({"role": role, "content": content})

    if pending_user_text:
        normalized_pending = pending_user_text.strip()
        duplicated_latest_user = (
            bool(messages)
            and messages[-1]["role"] == "user"
            and messages[-1]["content"].strip() == normalized_pending
        )
        if normalized_pending and not duplicated_latest_user:
            messages.append({"role": "user", "content": normalized_pending})
    return messages[-history_limit:]


def _normalize_match_text(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _match_chat_rag_groups(user_text: str, hit_text: str) -> bool:
    normalized_user_text = _normalize_match_text(user_text)
    normalized_hit_text = _normalize_match_text(hit_text)
    if not normalized_user_text or not normalized_hit_text:
        return False

    for group in _CHAT_RAG_TERM_GROUPS:
        if any(term in normalized_user_text for term in group) and any(term in normalized_hit_text for term in group):
            return True
    return False


def _is_chat_rag_hit_relevant(hit: dict, user_text: str) -> bool:
    try:
        score = float(hit.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0

    title = hit.get("title") or ""
    category = hit.get("category") or ""
    tags = " ".join(hit.get("tags") or [])
    content = hit.get("content") or ""
    combined_hit_text = f"{title} {category} {tags} {content}"

    if _match_chat_rag_groups(user_text, combined_hit_text):
        return score >= 0.11

    normalized_user_text = _normalize_match_text(user_text)
    normalized_hit_text = _normalize_match_text(combined_hit_text)
    if normalized_user_text and normalized_hit_text:
        for fragment in [term for term in normalized_user_text.split(" ") if len(term) >= 2]:
            if fragment in normalized_hit_text:
                return score >= 0.14

    return score >= 0.24


def _build_chat_rag_context(user, conversation: Conversation, pending_user_text: str = "") -> dict | None:
    rag_capability = (
        current_app.extensions.get("service_capabilities", {}).get("rag", {})
    )
    if not rag_capability.get("available"):
        return None

    context = _chat_context_builder.build_context(
        user,
        conversation=conversation,
        dialogue_limit=current_app.config.get("GLM_HISTORY_LIMIT", 12),
        multimodal_limit=3,
        rag_scope="chat",
    )
    rag_context = context.get("rag_context")
    if not isinstance(rag_context, dict):
        return None

    relevance_text = pending_user_text.strip()
    if not relevance_text:
        recent_dialogue = context.get("recent_dialogue") or []
        for item in reversed(recent_dialogue):
            if isinstance(item, dict) and item.get("role") == "user" and (item.get("content") or "").strip():
                relevance_text = item["content"].strip()
                break

    filtered_hits = []
    for item in rag_context.get("hits") or []:
        if not isinstance(item, dict):
            continue
        if not _is_chat_rag_hit_relevant(item, relevance_text):
            continue
        filtered_hits.append(item)

    if not filtered_hits:
        return None

    return {
        **rag_context,
        "hits": filtered_hits[:3],
    }


def _generate_assistant_reply(
    conversation: Conversation,
    content_text: str,
    custom_prompt: str = "",
    rag_context: dict | None = None,
    conversation_guidance: str = "",
) -> tuple[str, str]:
    glm_service = current_app.extensions.get("glm_service")
    model_name = current_app.config.get("GLM_MODEL", "GLM")
    require_glm = bool(current_app.config.get("CHAT_REQUIRE_GLM", False))
    if glm_service is None:
        if require_glm:
            raise GLMServiceError("GLM 服务当前不可用，请稍后再试。")
        reply_text = _fallback_reply_text(content_text, custom_prompt=custom_prompt, model_name=model_name)
        if conversation_guidance:
            reply_text = f"{reply_text}\n\n{_extract_guidance_question(conversation_guidance)}".strip()
        return reply_text, "fallback"

    try:
        messages = _build_glm_messages(conversation, content_text)
        if conversation_guidance:
            system_prompt = f"{glm_service.build_system_prompt(custom_prompt, rag_context=rag_context)}\n\n{conversation_guidance}"
            reply_text = glm_service.generate_text(messages=messages, system_prompt=system_prompt)
        else:
            reply_text = glm_service.generate_reply(
                messages=messages,
                custom_prompt=custom_prompt,
                rag_context=rag_context,
            )
        return reply_text, "glm_rag" if rag_context else "glm"
    except GLMServiceError as error:
        current_app.logger.warning("GLM reply failed, fallback to local reply: %s", error)
        if require_glm:
            raise
        reply_text = _fallback_reply_text(content_text, custom_prompt=custom_prompt, model_name=model_name)
        if conversation_guidance:
            reply_text = f"{reply_text}\n\n{_extract_guidance_question(conversation_guidance)}".strip()
        return reply_text, "fallback"


def _extract_guidance_question(conversation_guidance: str) -> str:
    markers = ["当前量表题项：", "询问当前量表题项：", "询问这个问题："]
    for marker in markers:
        if marker not in conversation_guidance:
            continue
        question = conversation_guidance.split(marker, 1)[1].split("不要", 1)[0].strip()
        if question:
            return question
    return conversation_guidance.strip()


def _generate_assistant_audio(
    text: str,
    voice_speed: float | None = None,
    voice_code: str = "",
) -> str | None:
    tts_service = current_app.extensions.get("tts_service")
    if tts_service is None:
        return None

    try:
        return tts_service.synthesize(text, voice_code=voice_code, speed=voice_speed)
    except Exception as error:
        current_app.logger.warning("Assistant TTS failed, skipped audio generation: %s", error)
        return None


@chat_bp.get("/conversations")
@login_required
def list_conversations():
    user = load_current_user()
    conversations = (
        Conversation.query.filter_by(user_id=user.id)
        .order_by(Conversation.latest_message_at.desc().nullslast(), Conversation.id.desc())
        .all()
    )
    return jsonify(
        {
            "conversations": [serialize_conversation(item) for item in conversations],
            "active_conversation_id": conversations[0].id if conversations else None,
        }
    )


@chat_bp.post("/conversations")
@login_required
def create_conversation():
    user = load_current_user()
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip() or "新的聊天"
    now = utcnow()

    conversation = Conversation(
        user_id=user.id,
        title=title,
        summary="开始新的对话吧",
        status="active",
        latest_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db.session.add(conversation)
    db.session.commit()
    return jsonify({"message": "新会话已创建", "conversation": serialize_conversation(conversation)}), 201


@chat_bp.patch("/conversations/<int:conversation_id>")
@login_required
def rename_conversation(conversation_id: int):
    conversation, error = _get_conversation_or_error(conversation_id, allow_admin=False)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    if not title:
        return jsonify({"message": "会话名称不能为空"}), 400

    conversation.title = title[:255]
    conversation.updated_at = utcnow()
    db.session.commit()
    return jsonify({"message": "会话名称已更新", "conversation": serialize_conversation(conversation)})


@chat_bp.delete("/conversations/<int:conversation_id>")
@login_required
def delete_conversation(conversation_id: int):
    user = load_current_user()
    conversation, error = _get_conversation_or_error(conversation_id, allow_admin=False)
    if error:
        return error

    db.session.delete(conversation)
    db.session.commit()

    next_conversation = (
        Conversation.query.filter_by(user_id=user.id)
        .order_by(Conversation.latest_message_at.desc().nullslast(), Conversation.id.desc())
        .first()
    )
    return jsonify(
        {
            "message": "会话已删除",
            "deleted_conversation_id": conversation_id,
            "active_conversation_id": next_conversation.id if next_conversation else None,
        }
    )


@chat_bp.get("/conversations/<int:conversation_id>")
@login_required
def get_conversation(conversation_id: int):
    conversation, error = _get_conversation_or_error(conversation_id)
    if error:
        return error

    messages = (
        Message.query.filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return jsonify(
        {
            "conversation": serialize_conversation(conversation),
            "messages": [serialize_message(item) for item in messages],
        }
    )


@chat_bp.get("/conversations/<int:conversation_id>/messages")
@login_required
def list_messages(conversation_id: int):
    conversation, error = _get_conversation_or_error(conversation_id)
    if error:
        return error

    messages = (
        Message.query.filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return jsonify(
        {
            "conversation": serialize_conversation(conversation),
            "messages": [serialize_message(item) for item in messages],
        }
    )


@chat_bp.post("/interventions/request")
@login_required
def request_intervention():
    user = load_current_user()
    active_intervention = get_active_intervention_for_user(user.id)
    if active_intervention is not None:
        return jsonify({"message": "当前已经进入人工介入，会有管理员继续接管。"}), 200

    pending_request = get_pending_transfer_request_for_user(user.id)
    if pending_request is not None:
        return jsonify(
            {
                "message": "已提交转人工申请，请等待管理员处理。",
                "requested_at": pending_request.created_at.isoformat() if pending_request.created_at else None,
            }
        ), 200

    payload = request.get_json(silent=True) or {}
    conversation = None
    conversation_id = payload.get("conversation_id")
    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user.id).first()
    if conversation is None:
        conversation = (
            Conversation.query.filter_by(user_id=user.id)
            .order_by(Conversation.latest_message_at.desc().nullslast(), Conversation.id.desc())
            .first()
        )

    now = utcnow()
    if conversation is None:
        conversation = Conversation(
            user_id=user.id,
            title="人工协助申请",
            summary=TRANSFER_REQUEST_MESSAGE,
            status="active",
            latest_message_at=now,
            created_at=now,
            updated_at=now,
        )
        db.session.add(conversation)
        db.session.flush()

    request_message = Message(
        conversation_id=conversation.id,
        sender_type="system",
        content_type=TRANSFER_REQUEST_CONTENT_TYPE,
        content_text=TRANSFER_REQUEST_MESSAGE,
        created_at=now,
    )
    db.session.add(request_message)

    conversation.summary = TRANSFER_REQUEST_MESSAGE
    conversation.latest_message_at = now
    conversation.updated_at = now

    db.session.commit()
    conversation_payload = serialize_conversation(conversation)
    request_message_payload = serialize_message(request_message)
    emit_intervention_requested(
        user_id=user.id,
        conversation=conversation_payload,
        request_message=request_message_payload,
    )
    return jsonify(
        {
            "message": "已提交转人工申请，管理员端将显示人工介入入口。",
            "requested_at": request_message.created_at.isoformat() if request_message.created_at else None,
            "conversation": conversation_payload,
            "request_message": request_message_payload,
        }
    ), 201


@chat_bp.get("/questionnaire/scales")
@login_required
def list_questionnaire_scales():
    return jsonify({"scales": QuestionnaireService().list_scales()})


@chat_bp.post("/conversations/<int:conversation_id>/questionnaire/start")
@login_required
def start_questionnaire_session(conversation_id: int):
    user = load_current_user()
    conversation, error = _get_conversation_or_error(conversation_id, allow_admin=False)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    scale_id = (payload.get("scale_id") or payload.get("scaleId") or "PHQ9").strip()
    questionnaire_service = QuestionnaireService()
    try:
        result = questionnaire_service.start_session(user=user, conversation=conversation, scale_id=scale_id)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    now = utcnow()
    custom_prompt = user.settings.custom_prompt if user.settings and user.settings.custom_prompt else ""
    opening_guidance = (
        f"用户刚主动发起 {result.scale_name} 对话式评估。"
        "请结合已有对话，用一小段自然、陪伴式语言承接，不要像宣读问卷。"
        "需要说明这不是诊断，只是帮助整理近期状态。"
    )
    if result.next_question:
        opening_guidance = (
            f"{opening_guidance}"
            f"然后自然询问当前量表题项：{result.next_question}"
            "不要提到题号，不要说正在执行系统指令，不要混入其他量表，不要提前给风险结论。"
        )
    try:
        opening_text, reply_source = _generate_assistant_reply(
            conversation,
            f"我想开始一次 {result.scale_name} 对话式评估。",
            custom_prompt=custom_prompt,
            conversation_guidance=opening_guidance,
        )
    except GLMServiceError as error:
        current_app.logger.warning("GLM questionnaire opening stopped request: %s", error)
        return jsonify({"message": str(error)}), 503

    assistant_message = Message(
        conversation_id=conversation.id,
        sender_type="assistant",
        content_type="text",
        content_text=opening_text,
        created_at=now,
    )
    db.session.add(assistant_message)
    conversation.summary = opening_text[:80]
    conversation.latest_message_at = now
    conversation.updated_at = now
    db.session.commit()
    questionnaire_payload = questionnaire_service.serialize_session(result.session)
    assistant_message_payload = serialize_message(assistant_message)
    conversation_payload = serialize_conversation(conversation)
    emit_message_created(
        conversation_id=conversation.id,
        user_id=user.id,
        message=assistant_message_payload,
        conversation=conversation_payload,
    )
    emit_questionnaire_updated(
        conversation_id=conversation.id,
        user_id=user.id,
        questionnaire=questionnaire_payload,
    )

    return jsonify(
        {
            "message": result.message,
            "questionnaire": questionnaire_payload,
            "assistant_message": assistant_message_payload,
            "conversation": conversation_payload,
            "reply_source": reply_source,
        }
    ), 201


@chat_bp.get("/conversations/<int:conversation_id>/questionnaire/status")
@login_required
def get_questionnaire_session_status(conversation_id: int):
    user = load_current_user()
    conversation, error = _get_conversation_or_error(conversation_id, allow_admin=False)
    if error:
        return error

    questionnaire_service = QuestionnaireService()
    session = questionnaire_service.get_active_session(user=user, conversation=conversation)
    return jsonify({"questionnaire": questionnaire_service.serialize_session(session)})


@chat_bp.post("/conversations/<int:conversation_id>/questionnaire/cancel")
@login_required
def cancel_questionnaire_session(conversation_id: int):
    user = load_current_user()
    conversation, error = _get_conversation_or_error(conversation_id, allow_admin=False)
    if error:
        return error

    questionnaire_service = QuestionnaireService()
    session = questionnaire_service.invalidate_active_session(user=user, conversation=conversation)
    db.session.commit()
    return jsonify(
        {
            "message": "当前量表评估已作废，后续聊天将回到普通陪伴状态。",
            "questionnaire": questionnaire_service.serialize_session(session),
        }
    )


@chat_bp.post("/conversations/<int:conversation_id>/messages")
@login_required
def create_message(conversation_id: int):
    user = load_current_user()
    conversation, error = _get_conversation_or_error(conversation_id, allow_admin=False)
    if error:
        return error

    payload = _get_message_payload()
    content_text = (payload.get("content") or payload.get("content_text") or "").strip()
    content_type = (payload.get("content_type") or "text").strip() or "text"
    audio_url = payload.get("audio_url") or ""
    video_url = payload.get("video_url") or ""
    audio_file = request.files.get("audio")
    video_file = request.files.get("video")

    if not content_text and not audio_url and not video_url and not audio_file and not video_file:
        return jsonify({"message": "消息内容不能为空"}), 400

    now = utcnow()
    custom_prompt = user.settings.custom_prompt if user.settings and user.settings.custom_prompt else ""

    user_message = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_user_id=user.id,
        content_type=content_type,
        content_text=content_text,
        audio_url=audio_url or None,
        video_url=video_url or None,
        created_at=now,
    )
    db.session.add(user_message)
    db.session.flush()

    multimodal_result = None
    multimodal_service = current_app.extensions.get("multimodal_service")
    if multimodal_service is not None and (audio_file or video_file):
        try:
            multimodal_result = multimodal_service.process_message_media(
                user_id=user.id,
                conversation_id=conversation.id,
                message_id=user_message.id,
                content_text=content_text,
                audio_file=audio_file,
                video_file=video_file,
            )
        except MultimodalServiceUnavailableError as media_error:
            db.session.rollback()
            return jsonify({"message": str(media_error)}), 503
        except MultimodalServiceError as media_error:
            db.session.rollback()
            return jsonify({"message": str(media_error)}), 400

        user_message.content_text = multimodal_result["message_text"]
        user_message.audio_url = multimodal_result["audio_url"] or user_message.audio_url
        user_message.video_url = multimodal_result["video_url"] or user_message.video_url
        if user_message.audio_url and user_message.video_url:
            user_message.content_type = "multimodal"
        elif user_message.audio_url:
            user_message.content_type = "audio"
        elif user_message.video_url:
            user_message.content_type = "video"

    assistant_prompt_text = (
        multimodal_result["assistant_text"]
        if multimodal_result is not None
        else content_text
    )
    questionnaire_service = QuestionnaireService()
    questionnaire_result = questionnaire_service.process_user_message(
        user=user,
        conversation=conversation,
        message=user_message,
    )
    questionnaire_guidance = questionnaire_service.build_guidance(questionnaire_result)
    rag_context = _build_chat_rag_context(user, conversation, pending_user_text=assistant_prompt_text)

    try:
        assistant_text, reply_source = _generate_assistant_reply(
            conversation,
            assistant_prompt_text,
            custom_prompt=custom_prompt,
            rag_context=rag_context,
            conversation_guidance=questionnaire_guidance,
        )
    except GLMServiceError as error:
        db.session.rollback()
        current_app.logger.warning("GLM message generation stopped request: %s", error)
        return (
            jsonify(
                {
                    "message": str(error),
                    "reply_source": "glm_error",
                    "used_custom_prompt": bool(custom_prompt),
                }
            ),
            503,
        )

    assistant_message = Message(
        conversation_id=conversation.id,
        sender_type="assistant",
        content_type="text",
        content_text=assistant_text,
        audio_url=_generate_assistant_audio(
            assistant_text,
            voice_speed=user.settings.voice_speed if user.settings else None,
            voice_code=user.settings.digital_human_code if user.settings else "",
        ),
        created_at=now,
    )
    db.session.add(assistant_message)

    conversation_preview = user_message.content_text or content_text
    if conversation.title == "新的聊天" and conversation_preview:
        conversation.title = conversation_preview[:12]
    conversation.summary = conversation_preview[:80] if conversation_preview else "已发送一条新的消息"
    conversation.latest_message_at = now
    conversation.updated_at = now

    db.session.commit()
    user_message_payload = serialize_message(user_message)
    assistant_message_payload = serialize_message(assistant_message)
    conversation_payload = serialize_conversation(conversation)
    questionnaire_session_payload = questionnaire_service.serialize_session(questionnaire_result.session)
    emit_message_created(
        conversation_id=conversation.id,
        user_id=user.id,
        message=user_message_payload,
        conversation=conversation_payload,
    )
    emit_message_created(
        conversation_id=conversation.id,
        user_id=user.id,
        message=assistant_message_payload,
        conversation=conversation_payload,
    )
    emit_questionnaire_updated(
        conversation_id=conversation.id,
        user_id=user.id,
        questionnaire=questionnaire_session_payload,
    )
    return jsonify(
        {
            "message": "消息已发送",
            "user_message": user_message_payload,
            "assistant_message": assistant_message_payload,
            "conversation": conversation_payload,
            "reply_source": reply_source,
            "rag_used": bool(rag_context),
            "used_custom_prompt": bool(custom_prompt),
            "profile_memory_updated": False,
            "questionnaire": {
                "answers": [
                    {
                        "itemCode": answer.item_code,
                        "dimension": answer.dimension,
                        "score": answer.score,
                        "confidence": answer.confidence,
                    }
                    for answer in questionnaire_result.answers
                ],
                "nextQuestion": questionnaire_result.next_question,
                "status": questionnaire_result.status,
                "scaleId": questionnaire_result.scale_id,
                "scaleName": questionnaire_result.scale_name,
                "session": questionnaire_session_payload,
                "score": (
                    {
                        "totalScore": questionnaire_result.score.total_score,
                        "stressIndex": questionnaire_result.score.stress_index,
                        "riskLevel": questionnaire_result.score.risk_level,
                        "dimensionScores": questionnaire_result.score.dimension_scores,
                    }
                    if questionnaire_result.score
                    else None
                ),
            },
            "multimodal_summary": (
                multimodal_result["multimodal_summary"] if multimodal_result is not None else None
            ),
        }
    ), 201


@chat_bp.get("/conversations/<int:conversation_id>/messages/<int:message_id>/media/<string:kind>")
@login_required
def get_message_media(conversation_id: int, message_id: int, kind: str):
    if kind not in {"audio", "video"}:
        return jsonify({"message": "不支持的媒体类型"}), 404

    conversation, error = _get_conversation_or_error(conversation_id)
    if error:
        return error
    _, message_error = _get_message_or_error(conversation, message_id)
    if message_error:
        return message_error

    multimodal_service = current_app.extensions.get("multimodal_service")
    if multimodal_service is None:
        return jsonify({"message": "媒体服务不可用"}), 503

    media_path = multimodal_service.get_message_media_path(conversation.id, message_id, kind)
    if media_path is None or not media_path.exists():
        return jsonify({"message": "媒体文件不存在"}), 404

    return send_file(
        media_path,
        mimetype=multimodal_service.get_message_media_mimetype(media_path),
        as_attachment=False,
        download_name=media_path.name,
    )


@chat_bp.get("/conversations/<int:conversation_id>/messages/<int:message_id>/multimodal-analysis")
@login_required
def get_message_multimodal_analysis(conversation_id: int, message_id: int):
    conversation, error = _get_conversation_or_error(conversation_id)
    if error:
        return error
    _, message_error = _get_message_or_error(conversation, message_id)
    if message_error:
        return message_error

    multimodal_service = current_app.extensions.get("multimodal_service")
    if multimodal_service is None:
        return jsonify({"message": "多模态分析服务不可用"}), 503

    payload = multimodal_service.load_full_analysis(message_id)
    if payload is None:
        return jsonify({"message": "该消息暂时没有多模态分析结果"}), 404
    return jsonify(payload)

