from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from flask import current_app

from ..models import Assessment, Conversation, InterventionSession, Message, QuestionnaireAnswer, QuestionnaireScore, QuestionnaireSession, User
from ..services.multimodal_service import MultimodalService
from ..services.system_settings import get_default_digital_human_code, load_profile_memory_template
from .voice_preferences import VOICE_SPEED_DEFAULT, normalize_voice_speed
from .intervention_requests import (
    get_active_intervention_for_user,
    get_pending_transfer_request_for_user,
)


RISK_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "高",
}

RISK_WEIGHTS = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

UNASSESSED_RISK_LABEL = "尚未评估"

QUESTIONNAIRE_DIMENSION_LABELS = {
    "sleep": "睡眠状态",
    "anxiety": "焦虑状态",
    "mood": "情绪低落",
    "stress": "主观压力",
    "function": "功能影响",
    "support": "支持系统",
    "safety": "安全风险",
}

PROFILE_MEMORY_FIELD_ALIASES = {
    "sleep_status": {"label": "睡眠与身体状态", "type": "text", "target": "sleep_and_body"},
    "stressors": {"label": "主要压力源", "type": "list", "target": "main_stressors"},
    "coping_style": {"label": "应对方式", "type": "text", "target": "intervention_preferences"},
    "stable_preferences": {"label": "陪伴偏好", "type": "list", "target": "intervention_preferences"},
    "recent_background": {"label": "近期关键背景", "type": "list", "target": "recent_context"},
}


def serialize_risk_level(risk_level: str | None) -> str:
    if not risk_level:
        return UNASSESSED_RISK_LABEL
    return RISK_LABELS.get(risk_level, UNASSESSED_RISK_LABEL)


def serialize_risk_weight(risk_level: str | None) -> int:
    if not risk_level:
        return 0
    return RISK_WEIGHTS.get(risk_level, 0)


def questionnaire_score_options(max_score: int) -> list[dict]:
    if max_score >= 4:
        labels = ["无", "轻度", "中度", "重度", "非常严重"]
    else:
        labels = ["没有", "偶尔/几天", "经常/一半以上时间", "几乎每天/非常明显"]
    return [{"score": score, "label": labels[min(score, len(labels) - 1)]} for score in range(max_score + 1)]


def format_datetime(value: datetime | None, fallback: str = "") -> str:
    if value is None:
        return fallback
    return value.strftime("%Y-%m-%d %H:%M")


def format_time_only(value: datetime | None, fallback: str = "") -> str:
    if value is None:
        return fallback
    return value.strftime("%H:%M")


def serialize_user_auth(user: User) -> dict:
    return {
        "id": user.id,
        "role": user.role,
        "phone": user.phone,
        "nickname": user.profile.nickname if user.profile else "",
        "avatarUrl": user.profile.avatar_url if user.profile else "",
    }


def serialize_profile(user: User) -> dict:
    profile = user.profile
    settings = user.settings
    goal_labels = [relation.tag.description or relation.tag.name for relation in user.profile_goals]

    return {
        "nickname": profile.nickname if profile and profile.nickname else user.phone,
        "phone": user.phone or "",
        "gender": profile.gender if profile else "",
        "age": profile.age if profile else None,
        "job": profile.occupation if profile else "",
        "purpose": "、".join(goal_labels),
        "purposeList": goal_labels,
        "joinedAt": user.created_at.strftime("%Y-%m-%d") if user.created_at else "",
        "avatarUrl": profile.avatar_url if profile else "",
        "customPrompt": settings.custom_prompt if settings else "",
    }


def serialize_settings(user: User) -> dict:
    settings = user.settings
    identity_service = current_app.extensions.get("digital_human_identity_service")
    default_avatar_code = get_default_digital_human_code()
    selected_code = settings.digital_human_code if settings and settings.digital_human_code else default_avatar_code
    selected_identity = None
    if identity_service is not None:
        selected_identity = identity_service.get_identity(selected_code)
        if selected_identity is None:
            selected_code = default_avatar_code
            selected_identity = identity_service.get_selected_identity(default_avatar_code)
    available_avatars = identity_service.list_identities() if identity_service is not None else []
    voice_speed = (
        normalize_voice_speed(settings.voice_speed, fallback=VOICE_SPEED_DEFAULT)
        if settings and getattr(settings, "voice_speed", None) is not None
        else VOICE_SPEED_DEFAULT
    )
    return {
        "systemPrompt": settings.custom_prompt if settings and settings.custom_prompt else "",
        "avatar": selected_identity["code"] if selected_identity else selected_code,
        "voiceSpeed": voice_speed,
        "defaultAvatarCode": default_avatar_code,
        "availableAvatars": [
            {
                "code": item["code"],
                "label": item["label"],
                "portraitUrl": item["portrait_url"],
                "modelPath": item["model_url"],
            }
            for item in available_avatars
        ],
        "selectedAvatar": (
            {
                "code": selected_identity["code"],
                "label": selected_identity["label"],
                "portraitUrl": selected_identity["portrait_url"],
                "modelPath": selected_identity["model_url"],
            }
            if selected_identity
            else None
        ),
    }


def serialize_conversation(conversation: Conversation) -> dict:
    preview = conversation.summary or ""
    latest_message = (
        Message.query.filter_by(conversation_id=conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    if latest_message and latest_message.content_text:
        preview = latest_message.content_text[:80]

    latest_at = conversation.latest_message_at or conversation.updated_at or conversation.created_at
    return {
        "id": conversation.id,
        "title": conversation.title,
        "updatedAt": format_datetime(latest_at),
        "preview": preview,
        "status": conversation.status,
        "latestMessageAt": latest_at.isoformat() if latest_at else None,
    }


def serialize_message(message: Message) -> dict:
    multimodal_summary = None
    if getattr(message, "multimodal_analysis", None) is not None:
        multimodal_summary = message.multimodal_analysis.get_summary_payload()
    if multimodal_summary is None:
        try:
            multimodal_summary = MultimodalService().load_message_summary(message.id)
        except Exception:
            multimodal_summary = None

    sender_label = "心陪陪"
    sender = "assistant"
    if message.sender_type == "user":
        sender = "user"
        sender_label = "我"
    elif message.sender_type == "human":
        sender = "human"
        sender_label = "心陪陪（人工介入）"
    elif message.sender_type == "system":
        sender = "system"
        sender_label = "系统"

    if message.sender_type == "user" and message.sender_user:
        sender_label = (
            message.sender_user.profile.nickname
            if message.sender_user.profile and message.sender_user.profile.nickname
            else message.sender_user.phone
        )

    return {
        "id": message.id,
        "sender": sender,
        "senderLabel": sender_label,
        "content": message.content_text or "",
        "time": format_time_only(message.created_at),
        "createdAt": message.created_at.isoformat() if message.created_at else None,
        "contentType": message.content_type,
        "audioUrl": message.audio_url,
        "videoUrl": message.video_url,
        "hasMultimodalAnalysis": bool(multimodal_summary),
        "multimodalSummary": multimodal_summary,
    }


def serialize_assessment_summary(assessment: Assessment | None) -> dict:
    if assessment is None:
        return {
            "mood": "暂时还没有生成状态评估记录",
            "stressIndex": "暂无",
            "updatedAt": "",
            "trend": "需要更多对话或测评数据后才会生成趋势",
            "advice": "先从一次简短对话开始，系统会逐步整理你的状态变化。",
            "riskCode": None,
            "riskLevel": UNASSESSED_RISK_LABEL,
            "tags": [],
        }

    trend_text = ""
    if isinstance(assessment.raw_result_json, dict):
        trend_text = assessment.raw_result_json.get("trend", "")

    return {
        "mood": assessment.mood_summary or "",
        "stressIndex": f"{assessment.stress_index} / 100" if assessment.stress_index is not None else "暂无",
        "updatedAt": format_datetime(assessment.evaluated_at),
        "trend": trend_text or "近期状态保持轻微波动，建议继续观察。",
        "advice": assessment.advice or "",
        "riskCode": assessment.risk_level,
        "riskLevel": serialize_risk_level(assessment.risk_level),
        "tags": [relation.tag.name for relation in assessment.tags],
    }


def build_assessment_cards(assessment: Assessment | None) -> list[dict]:
    summary = serialize_assessment_summary(assessment)
    return [
        {
            "title": "今日情绪状态",
            "value": summary["mood"][:18] or "待生成",
            "description": summary["mood"] or "系统会根据近期对话内容整理情绪状态。",
        },
        {
            "title": "本周压力指数",
            "value": summary["stressIndex"],
            "description": summary["trend"],
        },
        {
            "title": "最近一次评估时间",
            "value": summary["updatedAt"] or "暂无",
            "description": "最近一次状态评估的生成时间。",
        },
        {
            "title": "简要建议",
            "value": summary["riskLevel"],
            "description": summary["advice"],
        },
    ]


def get_latest_assessment(user: User) -> Assessment | None:
    return (
        Assessment.query.filter_by(user_id=user.id)
        .order_by(Assessment.evaluated_at.desc(), Assessment.id.desc())
        .first()
    )


def get_latest_user_assessment(user: User) -> Assessment | None:
    return (
        Assessment.query.filter(
            Assessment.user_id == user.id,
            ~Assessment.source.like("admin_%"),
        )
        .order_by(Assessment.evaluated_at.desc(), Assessment.id.desc())
        .first()
    )


def _load_profile_template_fields() -> dict:
    return load_profile_memory_template().get("fields") or {}


def _load_questionnaire_config() -> dict:
    path = Path(current_app.config.get("QUESTIONNAIRE_ITEMS_PATH", ""))
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_questionnaire_items() -> dict:
    payload = _load_questionnaire_config()
    items = {}
    for item in payload.get("items") or []:
        if item.get("code"):
            items[item["code"]] = item
    for scale in payload.get("scales") or []:
        for item in scale.get("items") or []:
            if item.get("code"):
                items[item["code"]] = {**item, "scale_id": scale.get("id"), "scale_name": scale.get("name")}
    return items


def _has_profile_memory_value(value) -> bool:
    if isinstance(value, list):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def _recommend_questionnaire_scale(user: User, scales: list[dict]) -> dict:
    available_ids = {str(scale.get("id") or "").upper() for scale in scales}
    memory = getattr(user, "profile_memory", None)
    memory_text = ""
    if memory is not None and isinstance(memory.memory_json, dict):
        memory_text = json.dumps(memory.memory_json, ensure_ascii=False)

    if "ISI" in available_ids and any(keyword in memory_text for keyword in ["睡眠", "失眠", "两三点", "熬夜", "睡不着"]):
        return {"scaleId": "ISI", "reason": "画像中睡眠受损线索更突出，优先建议使用 ISI。"}
    if "GAD7" in available_ids and any(keyword in memory_text for keyword in ["焦虑", "担心", "紧张", "发慌", "不安"]):
        return {"scaleId": "GAD7", "reason": "画像中焦虑和担心线索更突出，优先建议使用 GAD-7。"}
    if "PHQ9" in available_ids:
        return {"scaleId": "PHQ9", "reason": "当前更适合先用 PHQ-9 对情绪低落、兴趣、睡眠和安全风险做基础筛查。"}
    first_scale = scales[0] if scales else {}
    return {"scaleId": first_scale.get("id") or "", "reason": "暂无明确画像偏向，默认使用第一张可用量表。"}


def _format_profile_basic_text(user: User) -> str:
    profile = user.profile
    basic_parts = []
    nickname = profile.nickname if profile and profile.nickname else user.phone
    if nickname:
        basic_parts.append(f"昵称：{nickname}")
    if profile and profile.gender:
        basic_parts.append(f"性别：{profile.gender}")
    if profile and profile.age is not None:
        basic_parts.append(f"年龄：{profile.age}")
    if profile and profile.occupation:
        basic_parts.append(f"身份/职业：{profile.occupation}")
    if user.phone:
        basic_parts.append(f"账号：{user.phone}")
    return "；".join(basic_parts)


def _format_profile_purpose_list(user: User) -> list[str]:
    return [relation.tag.description or relation.tag.name for relation in user.profile_goals]


def _merge_profile_text(base_value: str, memory_value) -> str:
    base_text = str(base_value or "").strip()
    memory_text = str(memory_value or "").strip()
    if not base_text:
        return memory_text
    if not memory_text or memory_text == base_text or memory_text in base_text:
        return base_text
    return f"{base_text}；补充：{memory_text}"


def _merge_profile_list(base_values: list[str], memory_value) -> list[str]:
    values = [str(item or "").strip() for item in base_values if str(item or "").strip()]
    candidates = memory_value if isinstance(memory_value, list) else [memory_value]
    for item in candidates:
        text = str(item or "").strip()
        if text and text not in values:
            values.append(text)
    return values


def serialize_profile_memory_for_admin(user: User) -> dict:
    memory = getattr(user, "profile_memory", None)
    template_fields = _load_profile_template_fields()
    memory_payload = memory.memory_json if memory is not None and isinstance(memory.memory_json, dict) else {}
    basic_text = _format_profile_basic_text(user)
    purpose_list = _format_profile_purpose_list(user)
    items = []

    for field, meta in template_fields.items():
        value = memory_payload.get(field)
        source = "profile_memory"
        if field == "basic_background":
            value = _merge_profile_text(basic_text, value)
            source = "profile+profile_memory"
        elif field == "use_purpose":
            value = _merge_profile_list(purpose_list, value)
            source = "profile+profile_memory"
        display_value = value if _has_profile_memory_value(value) else "无"
        items.append(
            {
                "key": field,
                "label": meta.get("label") or field,
                "type": meta.get("type") or ("list" if isinstance(value, list) else "text"),
                "value": display_value,
                "description": meta.get("description") or "",
                "empty": not _has_profile_memory_value(value),
                "source": source,
            }
        )

    if memory is None or not isinstance(memory.memory_json, dict):
        return {
            "updatedAt": "",
            "items": items,
            "emptyText": "暂未沉淀动态画像；管理员可基于历史对话手动刷新。",
        }

    return {
        "updatedAt": format_datetime(memory.updated_at),
        "items": items,
        "emptyText": "暂未沉淀动态画像；管理员可基于历史对话手动刷新。",
    }


def serialize_questionnaire_risk_for_admin(user: User) -> dict:
    config = _load_questionnaire_config()
    questionnaire_name = config.get("name") or "单量表对话式心理状态评估"
    questionnaire_description = config.get("description") or "每次评估只绑定一张心理量表，完整后才进入正式评分。"
    reference_scales = [
        {
            "id": scale.get("id"),
            "name": scale.get("name"),
            "label": scale.get("label"),
            "purpose": scale.get("description"),
            "timeWindow": scale.get("timeWindow"),
            "scoreRange": scale.get("scoreRange"),
            "itemCount": len(scale.get("items") or []),
            "severity": scale.get("severity") or [],
            "items": [
                {
                    "code": item.get("code"),
                    "dimension": item.get("dimension"),
                    "dimensionLabel": QUESTIONNAIRE_DIMENSION_LABELS.get(item.get("dimension"), item.get("dimension")),
                    "construct": item.get("construct"),
                    "prompt": item.get("prompt"),
                    "maxScore": item.get("max_score"),
                    "options": questionnaire_score_options(int(item.get("max_score") or 3)),
                }
                for item in scale.get("items") or []
            ],
        }
        for scale in config.get("scales") or []
    ]
    recommended_scale = _recommend_questionnaire_scale(user, reference_scales)
    active_session = (
        QuestionnaireSession.query.filter_by(user_id=user.id, status="assessment_active")
        .order_by(QuestionnaireSession.updated_at.desc(), QuestionnaireSession.id.desc())
        .first()
    )
    score = (
        QuestionnaireScore.query.filter(
            QuestionnaireScore.user_id == user.id,
            QuestionnaireScore.scale_id != "",
        )
        .order_by(QuestionnaireScore.created_at.desc(), QuestionnaireScore.id.desc())
        .first()
    )
    latest_session = (
        QuestionnaireSession.query.filter_by(user_id=user.id)
        .order_by(QuestionnaireSession.updated_at.desc(), QuestionnaireSession.id.desc())
        .first()
    )
    display_session = active_session or latest_session
    item_map = _load_questionnaire_items()
    answer_query = None
    if score and score.session_id:
        answer_query = QuestionnaireAnswer.query.filter_by(user_id=user.id, session_id=score.session_id)
    elif display_session is not None and display_session.status in {"assessment_active", "assessment_completed"}:
        answer_query = QuestionnaireAnswer.query.filter_by(user_id=user.id, session_id=display_session.id)
    answers = (
        answer_query.order_by(QuestionnaireAnswer.created_at.asc(), QuestionnaireAnswer.id.asc()).limit(12).all()
        if answer_query is not None
        else []
    )

    serialized_answers = []
    for answer in answers:
        item = item_map.get(answer.item_code) or {}
        serialized_answers.append(
            {
                "itemCode": answer.item_code,
                "itemLabel": item.get("prompt") or answer.item_code,
                "referenceScale": item.get("scale_name") or item.get("scale") or answer.scale_id or "",
                "construct": item.get("construct") or "",
                "dimension": answer.dimension,
                "dimensionLabel": QUESTIONNAIRE_DIMENSION_LABELS.get(answer.dimension, answer.dimension),
                "score": answer.score,
                "maxScore": item.get("max_score"),
                "evidence": answer.evidence_text or "",
                "confidence": round(float(answer.confidence or 0), 2),
                "source": answer.source or "",
                "createdAt": format_datetime(answer.created_at),
            }
        )

    if score is None:
        status_text = "暂未开始量表评估"
        if display_session is not None:
            if display_session.status == "assessment_active":
                status_text = f"{display_session.scale_name} 评估进行中：{display_session.answered_item_count}/{display_session.required_item_count} 题已完成。"
            elif display_session.status == "assessment_invalid":
                status_text = f"{display_session.scale_name} 评估未完成，已作废，不进入正式评分。"
            elif display_session.status == "assessment_completed":
                status_text = f"{display_session.scale_name} 已完成，正在等待评分记录。"
        return {
            "hasScore": False,
            "questionnaireName": questionnaire_name,
            "questionnaireDescription": questionnaire_description,
            "referenceScales": reference_scales,
            "recommendedScale": recommended_scale,
            "sessionStatus": display_session.status if display_session else "normal_chat",
            "activeScaleId": display_session.scale_id if display_session else "",
            "activeScaleName": display_session.scale_name if display_session else "",
            "answeredItemCount": display_session.answered_item_count if display_session else 0,
            "requiredItemCount": display_session.required_item_count if display_session else 0,
            "currentSession": (
                {
                    "id": display_session.id,
                    "status": display_session.status,
                    "scaleId": display_session.scale_id or "",
                    "scaleName": display_session.scale_name or "",
                    "answeredItemCount": display_session.answered_item_count or 0,
                    "requiredItemCount": display_session.required_item_count or 0,
                    "nextQuestion": display_session.last_question_text or "",
                }
                if display_session
                else None
            ),
            "latestScore": None,
            "riskCode": None,
            "riskLevel": UNASSESSED_RISK_LABEL,
            "totalScore": None,
            "stressIndex": None,
            "dimensionScores": [],
            "answers": serialized_answers,
            "updatedAt": "",
            "basisText": status_text,
        }

    dimension_scores = []
    for dimension, value in (score.dimension_scores_json or {}).items():
        dimension_scores.append(
            {
                "dimension": dimension,
                "label": QUESTIONNAIRE_DIMENSION_LABELS.get(dimension, dimension),
                "score": value,
            }
        )

    basis = score.basis_json if isinstance(score.basis_json, dict) else {}
    method_text = f"{score.scale_name or score.scale_id or '单量表'}完整对话式评估"
    if basis.get("redline"):
        method_text += "，包含安全红线信号"
    stress_basis = basis.get("stress_index") if isinstance(basis, dict) else None
    if isinstance(stress_basis, dict):
        method_text += "；压力指数为系统标准化换算值，非量表原始分"

    session_status = display_session.status if display_session else "assessment_completed"
    session_scale_id = display_session.scale_id if display_session else score.scale_id
    session_scale_name = display_session.scale_name if display_session else score.scale_name
    session_answered_count = display_session.answered_item_count if display_session else basis.get("answer_count") or len(serialized_answers)
    session_required_count = display_session.required_item_count if display_session else basis.get("required_item_count") or len(serialized_answers)
    current_session_payload = (
        {
            "id": display_session.id,
            "status": display_session.status,
            "scaleId": display_session.scale_id or "",
            "scaleName": display_session.scale_name or "",
            "answeredItemCount": display_session.answered_item_count or 0,
            "requiredItemCount": display_session.required_item_count or 0,
            "nextQuestion": display_session.last_question_text or "",
        }
        if display_session
        else None
    )
    latest_score_payload = {
        "scaleId": score.scale_id or "",
        "scaleName": score.scale_name or "",
        "riskCode": score.risk_level,
        "riskLevel": serialize_risk_level(score.risk_level),
        "totalScore": score.total_score,
        "stressIndex": score.stress_index,
        "answeredItemCount": basis.get("answer_count") or len(serialized_answers),
        "requiredItemCount": basis.get("required_item_count") or len(serialized_answers),
        "updatedAt": format_datetime(score.created_at),
    }
    if active_session is not None:
        method_text = (
            f"当前 {active_session.scale_name} 评估进行中："
            f"{active_session.answered_item_count}/{active_session.required_item_count} 题已完成；"
            f"最新正式结果为 {method_text}"
        )

    return {
        "hasScore": True,
        "questionnaireName": questionnaire_name,
        "questionnaireDescription": questionnaire_description,
        "referenceScales": reference_scales,
        "recommendedScale": recommended_scale,
        "sessionStatus": session_status,
        "activeScaleId": session_scale_id or "",
        "activeScaleName": session_scale_name or "",
        "answeredItemCount": session_answered_count or 0,
        "requiredItemCount": session_required_count or 0,
        "currentSession": current_session_payload,
        "latestScore": latest_score_payload,
        "riskCode": score.risk_level,
        "riskLevel": serialize_risk_level(score.risk_level),
        "totalScore": score.total_score,
        "stressIndex": score.stress_index,
        "dimensionScores": dimension_scores,
        "answers": serialized_answers,
        "updatedAt": format_datetime(score.created_at),
        "basisText": (
            f"{method_text}；完成 {basis.get('answer_count') or len(serialized_answers)}/"
            f"{basis.get('required_item_count') or len(serialized_answers)} 题。"
            "不同量表不混合计分，未完成量表不进入正式评级。"
        ),
    }


def serialize_admin_user(user: User) -> dict:
    profile = user.profile
    latest_assessment = get_latest_assessment(user)
    risk_code = latest_assessment.risk_level if latest_assessment else None
    tags = [relation.tag.name for relation in latest_assessment.tags] if latest_assessment else [UNASSESSED_RISK_LABEL]
    pending_transfer_request = get_pending_transfer_request_for_user(user.id)
    active_intervention = get_active_intervention_for_user(user.id)
    latest_conversation = (
        Conversation.query.filter_by(user_id=user.id)
        .order_by(Conversation.latest_message_at.desc(), Conversation.id.desc())
        .first()
    )
    if latest_conversation and latest_conversation.latest_message_at:
        active_at = latest_conversation.latest_message_at
    elif user.last_login_at:
        active_at = user.last_login_at
    else:
        active_at = user.created_at

    return {
        "id": user.id,
        "name": profile.nickname if profile and profile.nickname else user.phone,
        "gender": profile.gender if profile and profile.gender else "",
        "age": profile.age if profile else None,
        "tags": tags,
        "riskCode": risk_code,
        "riskLevel": serialize_risk_level(risk_code),
        "riskWeight": serialize_risk_weight(risk_code),
        "account": user.phone,
        "activeAt": format_datetime(active_at),
        "summary": latest_assessment.mood_summary if latest_assessment and latest_assessment.mood_summary else "尚未评估，暂无分析摘要",
        "prompt": user.settings.custom_prompt if user.settings and user.settings.custom_prompt else "",
        "transferRequested": pending_transfer_request is not None,
        "transferRequestedAt": format_datetime(pending_transfer_request.created_at) if pending_transfer_request else "",
        "hasActiveIntervention": active_intervention is not None,
        "profileMemory": serialize_profile_memory_for_admin(user),
        "questionnaireRisk": serialize_questionnaire_risk_for_admin(user),
    }


def serialize_intervention_detail(session: InterventionSession) -> dict:
    conversation_messages = (
        Message.query.filter_by(conversation_id=session.conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return {
        "id": session.id,
        "conversationId": session.conversation_id,
        "userId": session.user_id,
        "status": session.status,
        "startedAt": session.started_at.isoformat() if session.started_at else None,
        "endedAt": session.ended_at.isoformat() if session.ended_at else None,
        "interventionNote": session.note or "",
        "user": serialize_admin_user(session.user),
        "messages": [serialize_message(message) for message in conversation_messages],
    }


def assessment_tag_names(assessment: Assessment | None) -> list[str]:
    if assessment is None:
        return []
    return [relation.tag.name for relation in assessment.tags]

