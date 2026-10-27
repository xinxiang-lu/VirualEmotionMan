from __future__ import annotations

from datetime import datetime, time, timedelta

from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import Assessment, AssessmentTag, Conversation, InterventionSession, Message, QuestionnaireSession, TagLibrary, User
from ..models.base import utcnow
from ..services.ai import (
    ProfileReportService,
    ProfileReportServiceError,
    RiskAssessmentService,
    RiskAssessmentServiceError,
)
from ..services.profile_memory_service import ProfileMemoryService
from ..services.questionnaire_service import QuestionnaireService
from ..services.system_settings import load_system_settings, save_system_settings
from ..utils.auth import admin_required, load_current_user
from ..utils.realtime import (
    emit_intervention_ended,
    emit_intervention_started,
    emit_message_created,
    emit_questionnaire_updated,
)
from ..utils.serializers import (
    UNASSESSED_RISK_LABEL,
    assessment_tag_names,
    get_latest_assessment,
    get_latest_user_assessment,
    serialize_admin_user,
    serialize_conversation,
    serialize_intervention_detail,
    serialize_message,
    serialize_risk_level,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _admin_users() -> list[User]:
    return User.query.filter_by(role="user").all()


def _recent_calendar_days(days: int = 7) -> list:
    end_day = utcnow().date()
    return [end_day - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _day_start(day) -> datetime:
    return datetime.combine(day, time.min)


def _normalize_risk_code(value: str | None) -> str | None:
    if value in {"critical", "high"}:
        return "high"
    if value in {"medium", "low"}:
        return value
    return None


def _build_dialogue_trend_card(user_ids: list[int], days: list) -> dict:
    start_at = _day_start(days[0])
    end_at = _day_start(days[-1] + timedelta(days=1))
    rows = (
        db.session.query(Message.created_at, Message.conversation_id, Conversation.user_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(
            Message.sender_type == "user",
            Conversation.user_id.in_(user_ids),
            Message.created_at >= start_at,
            Message.created_at < end_at,
        )
        .all()
    )

    grouped = {
        day: {"message_count": 0, "user_ids": set(), "conversation_ids": set()}
        for day in days
    }
    window_user_ids = set()
    window_conversation_ids = set()
    for created_at, conversation_id, user_id in rows:
        day = created_at.date()
        if day not in grouped:
            continue
        grouped[day]["message_count"] += 1
        grouped[day]["user_ids"].add(user_id)
        grouped[day]["conversation_ids"].add(conversation_id)
        window_user_ids.add(user_id)
        window_conversation_ids.add(conversation_id)

    series = []
    for day in days:
        bucket = grouped[day]
        series.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%m-%d"),
                "value": bucket["message_count"],
                "detail": f"{bucket['message_count']} 条",
                "activeUserCount": len(bucket["user_ids"]),
                "conversationCount": len(bucket["conversation_ids"]),
            }
        )

    total_messages = sum(item["value"] for item in series)
    peak_point = max(series, key=lambda item: item["value"]) if series else {"date": "", "value": 0}
    peak_active = max((item["activeUserCount"] for item in series), default=0)
    return {
        "key": "dialogues",
        "title": "对话趋势",
        "metricLabel": "近 7 天用户消息",
        "metricValue": str(total_messages),
        "chartType": "bars",
        "series": series,
        "breakdown": [
            {"label": "覆盖活跃用户", "value": f"{len(window_user_ids)} 人"},
            {"label": "峰值活跃用户", "value": f"{peak_active} 人"},
            {"label": "涉及会话数", "value": str(len(window_conversation_ids))},
        ],
        "description": (
            f"{days[0].isoformat()} 至 {days[-1].isoformat()} 共记录 {total_messages} 条用户消息，"
            f"峰值出现在 {peak_point['date']}（{peak_point['value']} 条）。"
        ),
        "summary": {
            "totalMessages": total_messages,
            "peakActiveUsers": peak_active,
            "windowConversationCount": len(window_conversation_ids),
        },
    }


def _build_risk_trend_card(user_ids: list[int], days: list) -> dict:
    end_at = _day_start(days[-1] + timedelta(days=1))
    rows = (
        db.session.query(Assessment.user_id, Assessment.evaluated_at, Assessment.id, Assessment.risk_level)
        .join(User, User.id == Assessment.user_id)
        .filter(
            User.role == "user",
            Assessment.evaluated_at < end_at,
        )
        .order_by(Assessment.evaluated_at.asc(), Assessment.id.asc())
        .all()
    )

    latest_by_user: dict[int, str | None] = {}
    pointer = 0
    series = []
    for day in days:
        day_end = _day_start(day + timedelta(days=1))
        while pointer < len(rows) and rows[pointer][1] < day_end:
            user_id, _, _, risk_level = rows[pointer]
            latest_by_user[user_id] = _normalize_risk_code(risk_level)
            pointer += 1

        counts = {"low": 0, "medium": 0, "high": 0, "unassessed": 0}
        for user_id in user_ids:
            normalized = latest_by_user.get(user_id)
            if normalized is None:
                counts["unassessed"] += 1
            else:
                counts[normalized] += 1

        series.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%m-%d"),
                "low": counts["low"],
                "medium": counts["medium"],
                "high": counts["high"],
                "unassessed": counts["unassessed"],
                "mediumHigh": counts["medium"] + counts["high"],
            }
        )

    current = series[-1] if series else {"low": 0, "medium": 0, "high": 0, "unassessed": 0, "mediumHigh": 0}
    baseline = series[0]["mediumHigh"] if series else 0
    delta = current["mediumHigh"] - baseline
    delta_text = "持平" if delta == 0 else f"{'+' if delta > 0 else ''}{delta} 人"
    return {
        "key": "risks",
        "title": "风险趋势",
        "metricLabel": "当前中高风险用户",
        "metricValue": str(current["mediumHigh"]),
        "chartType": "stacked",
        "series": series,
        "legend": [
            {"label": "高风险", "tone": "high"},
            {"label": "中风险", "tone": "medium"},
            {"label": "低风险", "tone": "low"},
            {"label": "未评估", "tone": "unassessed"},
        ],
        "breakdown": [
            {"label": "当前高风险", "value": f"{current['high']} 人"},
            {"label": "当前中风险", "value": f"{current['medium']} 人"},
            {"label": "当前未评估", "value": f"{current['unassessed']} 人"},
        ],
        "description": (
            f"截至 {days[-1].isoformat()}，中高风险用户 {current['mediumHigh']} 人，"
            f"较 {days[0].isoformat()} {delta_text}。"
        ),
        "summary": {
            "mediumHighUsers": current["mediumHigh"],
            "highUsers": current["high"],
            "unassessedUsers": current["unassessed"],
        },
    }


def _build_assessment_trend_card(user_ids: list[int], days: list) -> dict:
    total_users = len(user_ids)
    end_at = _day_start(days[-1] + timedelta(days=1))
    rows = (
        db.session.query(
            Assessment.user_id,
            Assessment.evaluated_at,
            Assessment.id,
            Assessment.source,
            Assessment.stress_index,
        )
        .join(User, User.id == Assessment.user_id)
        .filter(
            User.role == "user",
            ~Assessment.source.like("admin_%"),
            Assessment.evaluated_at < end_at,
        )
        .order_by(Assessment.evaluated_at.asc(), Assessment.id.asc())
        .all()
    )

    daily_generated = {day: 0 for day in days}
    daily_stress_sum = {day: 0 for day in days}
    daily_stress_count = {day: 0 for day in days}
    covered_users = set()
    pointer = 0
    series = []

    for day in days:
        day_end = _day_start(day + timedelta(days=1))
        while pointer < len(rows) and rows[pointer][1] < day_end:
            user_id, evaluated_at, _, _, stress_index = rows[pointer]
            covered_users.add(user_id)
            bucket_day = evaluated_at.date()
            if bucket_day in daily_generated:
                daily_generated[bucket_day] += 1
                if stress_index is not None:
                    daily_stress_sum[bucket_day] += stress_index
                    daily_stress_count[bucket_day] += 1
            pointer += 1

        avg_stress = None
        if daily_stress_count[day]:
            avg_stress = round(daily_stress_sum[day] / daily_stress_count[day], 1)
        coverage_rate = round((len(covered_users) / total_users) * 100, 1) if total_users else 0
        series.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%m-%d"),
                "value": daily_generated[day],
                "detail": f"{daily_generated[day]} 条",
                "coverageRate": coverage_rate,
                "avgStressIndex": avg_stress,
            }
        )

    total_generated = sum(item["value"] for item in series)
    current_coverage = series[-1]["coverageRate"] if series else 0
    covered_count = int(round((current_coverage / 100) * total_users)) if total_users else 0
    stress_values = [item["avgStressIndex"] for item in series if item["avgStressIndex"] is not None]
    recent_avg_stress = round(sum(stress_values) / len(stress_values), 1) if stress_values else None
    latest_generated = series[-1]["value"] if series else 0

    return {
        "key": "assessments",
        "title": "评估趋势",
        "metricLabel": "近 7 天状态评估",
        "metricValue": str(total_generated),
        "chartType": "bars",
        "series": series,
        "breakdown": [
            {"label": "当前覆盖率", "value": f"{current_coverage}%"},
            {"label": "已覆盖用户", "value": f"{covered_count} 人"},
            {"label": "近 7 天平均压力指数", "value": f"{recent_avg_stress}" if recent_avg_stress is not None else "暂无"},
        ],
        "description": (
            f"{days[0].isoformat()} 至 {days[-1].isoformat()} 共生成 {total_generated} 条状态评估，"
            f"最近一天新增 {latest_generated} 条，当前覆盖率 {current_coverage}%。"
        ),
        "summary": {
            "coveredUsers": covered_count,
            "coverageRate": current_coverage,
            "recentAverageStressIndex": recent_avg_stress,
        },
    }


@admin_bp.get("/users")
@admin_required
def admin_users():
    keyword = (request.args.get("keyword") or request.args.get("q") or "").strip()
    tags_filter = [item.strip() for item in (request.args.get("tags") or "").split(",") if item.strip()]
    sort_by = (request.args.get("sort_by") or "risk").strip()

    users = [serialize_admin_user(user) for user in _admin_users()]
    has_unassessed_user = any(user["riskCode"] is None for user in users)

    if keyword:
        users = [user for user in users if keyword in f"{user['name']} {user['account']} {user['summary']}"]

    if tags_filter:
        users = [user for user in users if all(tag in user["tags"] for tag in tags_filter)]

    if sort_by == "age":
        users.sort(key=lambda item: item["age"] if item["age"] is not None else 0)
    elif sort_by == "active":
        users.sort(key=lambda item: item["activeAt"], reverse=True)
    else:
        users.sort(key=lambda item: item["riskWeight"], reverse=True)

    available_tags = [
        tag.name
        for tag in TagLibrary.query.filter_by(tag_type="risk", is_active=True)
        .order_by(TagLibrary.sort_order.asc(), TagLibrary.id.asc())
        .all()
    ]
    if has_unassessed_user and UNASSESSED_RISK_LABEL not in available_tags:
        available_tags.append(UNASSESSED_RISK_LABEL)
    return jsonify({"users": users, "available_tags": available_tags})


@admin_bp.get("/users/<int:user_id>")
@admin_required
def admin_user_detail(user_id: int):
    user = User.query.filter_by(id=user_id, role="user").first()
    if user is None:
        return jsonify({"message": "用户不存在"}), 404

    latest_assessment = get_latest_assessment(user)
    return jsonify(
        {
            "user": serialize_admin_user(user),
            "assessment": {
                "summary": latest_assessment.mood_summary if latest_assessment else "",
                "riskCode": latest_assessment.risk_level if latest_assessment else None,
                "riskLevel": serialize_risk_level(latest_assessment.risk_level if latest_assessment else None),
                "tags": assessment_tag_names(latest_assessment) if latest_assessment else [UNASSESSED_RISK_LABEL],
                "advice": latest_assessment.advice if latest_assessment else "",
            },
        }
    )


@admin_bp.get("/questionnaire/scales")
@admin_required
def admin_questionnaire_scales():
    return jsonify({"scales": QuestionnaireService().list_scale_details()})


@admin_bp.post("/questionnaire/scales")
@admin_required
def create_questionnaire_scale():
    payload = request.get_json(silent=True) or {}
    service = QuestionnaireService()
    try:
        scale = service.create_scale(payload)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    return jsonify({"message": "量表已新增", "scale": service.serialize_scale(scale, include_items=True)}), 201


@admin_bp.put("/questionnaire/scales/<string:scale_id>")
@admin_required
def update_questionnaire_scale(scale_id: str):
    payload = request.get_json(silent=True) or {}
    service = QuestionnaireService()
    try:
        scale = service.update_scale(scale_id, payload)
    except ValueError as error:
        return jsonify({"message": str(error)}), 404 if "不存在" in str(error) else 400
    return jsonify({"message": "量表已更新", "scale": service.serialize_scale(scale, include_items=True)})


@admin_bp.delete("/questionnaire/scales/<string:scale_id>")
@admin_required
def delete_questionnaire_scale(scale_id: str):
    active_session = QuestionnaireSession.query.filter_by(scale_id=scale_id, status="assessment_active").first()
    if active_session is not None:
        return jsonify({"message": "该量表存在进行中的评估，暂不能删除"}), 409

    service = QuestionnaireService()
    try:
        service.delete_scale(scale_id)
    except ValueError as error:
        return jsonify({"message": str(error)}), 404
    return jsonify({"message": "量表已删除"})


@admin_bp.patch("/users/<int:user_id>/prompt")
@admin_required
def update_user_prompt(user_id: int):
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get("prompt") or "").strip()
    user = User.query.filter_by(id=user_id, role="user").first()
    if user is None:
        return jsonify({"message": "用户不存在"}), 404
    if user.settings is None:
        return jsonify({"message": "用户设置不存在"}), 404

    user.settings.custom_prompt = prompt
    db.session.commit()
    return jsonify({"message": "提示词已更新", "user": serialize_admin_user(user)})


@admin_bp.post("/users/<int:user_id>/risk-assessment/refresh")
@admin_required
def refresh_user_risk_assessment(user_id: int):
    user = User.query.filter_by(id=user_id, role="user").first()
    if user is None:
        return jsonify({"message": "用户不存在"}), 404

    payload = request.get_json(silent=True) or {}
    conversation = None
    conversation_id = payload.get("conversation_id")
    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user.id).first()
        if conversation is None:
            return jsonify({"message": "未找到该用户对应的会话"}), 404

    service = RiskAssessmentService()
    try:
        result = service.generate_for_user(
            user,
            conversation=conversation,
            dialogue_limit=int(payload.get("dialogue_limit") or 12),
            multimodal_limit=int(payload.get("multimodal_limit") or 3),
        )
    except RiskAssessmentServiceError as error:
        message = str(error)
        status_code = 503 if "GLM" in message else 400
        return jsonify({"message": message}), status_code

    assessment = Assessment(
        user_id=user.id,
        conversation_id=result.context.get("conversation_id"),
        source="admin_risk_refresh",
        mood_summary=result.core_psychological_issue,
        stress_index=None,
        risk_level=result.risk_level,
        advice="建议管理员结合近期对话与多模态表现持续观察，如有进一步升级信号请及时人工介入。",
        raw_result_json={
            "risk_reason": result.risk_reason,
            "core_psychological_issue": result.core_psychological_issue,
            "context": result.context,
            "raw_response": result.raw_response,
            "trigger": "admin_manual_refresh",
        },
        evaluated_at=utcnow(),
    )
    db.session.add(assessment)
    db.session.flush()

    tag_names = service.infer_tag_names(result)
    if tag_names:
        tag_lookup = {
            tag.name: tag
            for tag in TagLibrary.query.filter(
                TagLibrary.tag_type == "risk",
                TagLibrary.is_active.is_(True),
                TagLibrary.name.in_(tag_names),
            ).all()
        }
        for tag_name in tag_names:
            tag = tag_lookup.get(tag_name)
            if tag is not None:
                db.session.add(AssessmentTag(assessment_id=assessment.id, tag_id=tag.id))

    db.session.commit()

    return jsonify(
        {
            "message": "风险评估已刷新",
            "user": serialize_admin_user(user),
            "assessment": {
                **service.build_admin_response(result),
                "assessmentId": assessment.id,
                "riskLevel": serialize_risk_level(result.risk_level),
                "evaluatedAt": assessment.evaluated_at.isoformat() if assessment.evaluated_at else None,
            },
        }
    )


@admin_bp.post("/users/<int:user_id>/questionnaire/start")
@admin_required
def start_user_questionnaire(user_id: int):
    user = User.query.filter_by(id=user_id, role="user").first()
    if user is None:
        return jsonify({"message": "用户不存在"}), 404

    payload = request.get_json(silent=True) or {}
    scale_id = (payload.get("scale_id") or payload.get("scaleId") or "PHQ9").strip()
    conversation_id = payload.get("conversation_id") or payload.get("conversationId")
    conversation = None
    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user.id).first()
        if conversation is None:
            return jsonify({"message": "未找到该用户对应的会话"}), 404

    now = utcnow()
    if conversation is None:
        conversation = (
            Conversation.query.filter_by(user_id=user.id)
            .order_by(Conversation.latest_message_at.desc().nullslast(), Conversation.id.desc())
            .first()
        )
    if conversation is None:
        conversation = Conversation(
            user_id=user.id,
            title="状态评估",
            summary="管理员发起了一次对话式量表评估",
            status="active",
            latest_message_at=now,
            created_at=now,
            updated_at=now,
        )
        db.session.add(conversation)
        db.session.flush()

    questionnaire_service = QuestionnaireService()
    existing_active = questionnaire_service.get_active_session(user=user, conversation=conversation)
    try:
        result = questionnaire_service.start_session(user=user, conversation=conversation, scale_id=scale_id)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    assistant_message = None
    if existing_active is None:
        opening_text = (
            f"管理员为你开启了 {result.scale_name} 对话式评估。"
            "这不是诊断，只是帮助系统更准确地理解你最近的状态。"
        )
        if result.next_question:
            opening_text = f"{opening_text}\n\n{result.next_question}"
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
    conversation_payload = serialize_conversation(conversation)
    assistant_message_payload = serialize_message(assistant_message) if assistant_message else None
    if assistant_message_payload is not None:
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
            "user": serialize_admin_user(user),
            "questionnaire": questionnaire_payload,
            "assistant_message": assistant_message_payload,
            "conversation": conversation_payload,
        }
    ), 201


@admin_bp.post("/users/<int:user_id>/profile-memory/refresh")
@admin_required
def refresh_user_profile_memory(user_id: int):
    user = User.query.filter_by(id=user_id, role="user").first()
    if user is None:
        return jsonify({"message": "用户不存在"}), 404

    payload = request.get_json(silent=True) or {}
    dialogue_limit = int(payload.get("dialogue_limit") or payload.get("dialogueLimit") or 40)
    service = ProfileMemoryService()
    result = service.update_from_history(user=user, dialogue_limit=dialogue_limit)
    db.session.commit()
    return jsonify(
        {
            "message": f"用户画像已刷新，更新 {len(result.updates)} 个字段",
            "updated": result.updated,
            "updateCount": len(result.updates),
            "fields": [update.field for update in result.updates],
            "user": serialize_admin_user(user),
        }
    )


@admin_bp.post("/users/<int:user_id>/profile-report/generate")
@admin_required
def generate_user_profile_report(user_id: int):
    user = User.query.filter_by(id=user_id, role="user").first()
    if user is None:
        return jsonify({"message": "用户不存在"}), 404

    payload = request.get_json(silent=True) or {}
    service = ProfileReportService()
    try:
        result = service.generate_for_user(
            user,
            assessment_limit=int(payload.get("assessment_limit") or 8),
            dialogue_limit=int(payload.get("dialogue_limit") or 24),
            strategy_limit=int(payload.get("strategy_limit") or 8),
        )
    except ProfileReportServiceError as error:
        message = str(error)
        status_code = 503 if "GLM" in message else 400
        return jsonify({"message": message}), status_code

    return jsonify(
        {
            "message": "心理档案报告已生成",
            "report_markdown": result.markdown,
            "generated_at": utcnow().isoformat(),
            "context_meta": {
                "assessment_count": len(result.context.get("historical_psych_state_logs") or []),
                "strategy_count": len(result.context.get("historical_strategies_logs") or []),
                "dialogue_count": len(result.context.get("recent_dialogue_records") or []),
            },
        }
    )


@admin_bp.get("/business-stats")
@admin_required
def business_stats():
    now = utcnow()
    users = _admin_users()
    user_ids = [user.id for user in users]
    total_users = len(users)
    days = _recent_calendar_days(7)

    dialogue_trend = _build_dialogue_trend_card(user_ids, days)
    risk_trend = _build_risk_trend_card(user_ids, days)
    assessment_trend = _build_assessment_trend_card(user_ids, days)

    recent_days = now - timedelta(days=7)
    active_users = 0
    for user in users:
        latest_conversation = (
            Conversation.query.filter_by(user_id=user.id)
            .order_by(Conversation.latest_message_at.desc(), Conversation.id.desc())
            .first()
        )
        if (user.last_login_at and user.last_login_at >= recent_days) or (
            latest_conversation and latest_conversation.latest_message_at and latest_conversation.latest_message_at >= recent_days
        ):
            active_users += 1

    daily_dialogues = dialogue_trend["series"][-1]["value"] if dialogue_trend["series"] else 0
    weekly_dialogues = Message.query.filter(Message.created_at >= recent_days, Message.sender_type == "user").count()
    monthly_dialogues = Message.query.filter(Message.created_at >= now - timedelta(days=30), Message.sender_type == "user").count()
    intervention_total = InterventionSession.query.count()
    risk_users = risk_trend["summary"]["mediumHighUsers"]
    assessed_users = assessment_trend["summary"]["coveredUsers"]

    stats = [
        {"label": "总用户数", "value": str(total_users), "tone": "blue"},
        {"label": "活跃用户数", "value": str(active_users), "tone": "green"},
        {"label": "已生成状态评估用户数", "value": str(assessed_users), "tone": "blue"},
        {"label": "日/周/月新增对话数", "value": f"{daily_dialogues} / {weekly_dialogues} / {monthly_dialogues}", "tone": "purple"},
        {"label": "风险用户数量", "value": str(risk_users), "tone": "orange"},
        {"label": "人工介入次数", "value": str(intervention_total), "tone": "orange"},
    ]
    trend_cards = [dialogue_trend, risk_trend, assessment_trend]

    return jsonify({"stats": stats, "trend_cards": trend_cards})


@admin_bp.get("/ops-stats")
@admin_required
def ops_stats():
    metrics = current_app.extensions.get("runtime_metrics")
    glm_service = current_app.extensions.get("glm_service")
    glm_status = glm_service.status() if glm_service else None
    if metrics is None:
        logs = []
        request_count = 0
        error_count = 0
        average_response_time = 0
    else:
        logs = metrics.latest_logs()
        request_count = metrics.request_count
        error_count = metrics.error_count
        average_response_time = metrics.average_response_time_ms

    system_status = "正常" if error_count == 0 else "关注中"
    if glm_status and glm_status.configured and glm_status.sdk_available:
        model_service_status = "已接入 GLM"
    elif glm_status and glm_status.configured and not glm_status.sdk_available:
        model_service_status = "已配置 Key，缺少 SDK"
    else:
        model_service_status = "未配置"

    stats = [
        {"label": "系统运行状态", "value": system_status, "tone": "green" if error_count == 0 else "orange"},
        {"label": "接口调用次数", "value": str(request_count), "tone": "blue"},
        {"label": "接口错误次数", "value": str(error_count), "tone": "orange" if error_count else "green"},
        {"label": "平均响应时间", "value": f"{average_response_time} ms", "tone": "purple"},
        {"label": "模型服务调用状态", "value": model_service_status, "tone": "green" if glm_status and glm_status.enabled else "orange"},
        {"label": "近日日志数", "value": str(len(logs)), "tone": "blue"},
    ]
    return jsonify({"stats": stats, "logs": logs})


@admin_bp.get("/system-settings")
@admin_required
def system_settings():
    return jsonify({"settings": load_system_settings()})


@admin_bp.put("/system-settings")
@admin_required
def update_system_settings():
    payload = request.get_json(silent=True) or {}
    settings = save_system_settings(payload)
    return jsonify({"message": "系统设置已更新", "settings": settings})


@admin_bp.post("/interventions")
@admin_required
def create_intervention():
    admin_user = load_current_user()
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    if not user_id:
        return jsonify({"message": "user_id 不能为空"}), 400

    user = User.query.filter_by(id=user_id, role="user").first()
    if user is None:
        return jsonify({"message": "用户不存在"}), 404

    conversation = None
    conversation_id = payload.get("conversation_id")
    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user.id).first()
    if conversation is None:
        conversation = (
            Conversation.query.filter_by(user_id=user.id)
            .order_by(Conversation.latest_message_at.desc(), Conversation.id.desc())
            .first()
        )
    if conversation is None:
        return jsonify({"message": "该用户还没有会话记录，无法发起人工介入"}), 400

    existing = (
        InterventionSession.query.filter_by(conversation_id=conversation.id, status="active")
        .order_by(InterventionSession.started_at.desc(), InterventionSession.id.desc())
        .first()
    )
    if existing is not None:
        return jsonify({"message": "已存在进行中的人工介入", "session": serialize_intervention_detail(existing)})

    latest_assessment = get_latest_assessment(user)
    session = InterventionSession(
        conversation_id=conversation.id,
        user_id=user.id,
        admin_id=admin_user.id,
        trigger_assessment_id=latest_assessment.id if latest_assessment else None,
        status="active",
        note=(payload.get("note") or "已进入人工介入，请优先承接用户情绪，再逐步展开对话。").strip(),
        started_at=utcnow(),
    )
    db.session.add(session)
    db.session.commit()
    session_payload = serialize_intervention_detail(session)
    emit_intervention_started(
        user_id=user.id,
        conversation_id=conversation.id,
        session=session_payload,
    )
    return jsonify({"message": "人工介入已创建", "session": session_payload}), 201


@admin_bp.get("/interventions/<int:session_id>")
@admin_required
def intervention_detail(session_id: int):
    session = InterventionSession.query.get(session_id)
    if session is None:
        return jsonify({"message": "人工介入会话不存在"}), 404
    return jsonify({"session": serialize_intervention_detail(session)})


@admin_bp.get("/interventions/user/<int:user_id>")
@admin_required
def intervention_by_user(user_id: int):
    session = (
        InterventionSession.query.filter_by(user_id=user_id)
        .order_by(InterventionSession.started_at.desc(), InterventionSession.id.desc())
        .first()
    )
    if session is None:
        return jsonify({"message": "当前用户还没有人工介入记录"}), 404
    return jsonify({"session": serialize_intervention_detail(session)})


@admin_bp.post("/interventions/<int:session_id>/messages")
@admin_required
def create_intervention_message(session_id: int):
    session = InterventionSession.query.get(session_id)
    if session is None:
        return jsonify({"message": "人工介入会话不存在"}), 404
    if session.status != "active":
        return jsonify({"message": "人工介入已结束，无法继续发送消息"}), 400

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or payload.get("content_text") or "").strip()
    if not content:
        return jsonify({"message": "消息内容不能为空"}), 400

    admin_user = load_current_user()
    now = utcnow()
    message = Message(
        conversation_id=session.conversation_id,
        sender_type="human",
        sender_user_id=admin_user.id,
        intervention_session_id=session.id,
        content_type="text",
        content_text=content,
        created_at=now,
    )
    db.session.add(message)

    conversation = Conversation.query.get(session.conversation_id)
    if conversation is not None:
        conversation.summary = content[:80]
        conversation.latest_message_at = now
        conversation.updated_at = now

    db.session.commit()
    session_payload = serialize_intervention_detail(session)
    message_payload = session_payload["messages"][-1]
    emit_message_created(
        conversation_id=session.conversation_id,
        user_id=session.user_id,
        message=message_payload,
        conversation=serialize_conversation(conversation) if conversation is not None else None,
    )
    return jsonify({"message": "人工回复已发送", "chat_message": message_payload}), 201


@admin_bp.post("/interventions/<int:session_id>/finish")
@admin_required
def finish_intervention(session_id: int):
    session = InterventionSession.query.get(session_id)
    if session is None:
        return jsonify({"message": "人工介入会话不存在"}), 404
    session.status = "ended"
    session.ended_at = utcnow()
    db.session.commit()
    session_payload = serialize_intervention_detail(session)
    emit_intervention_ended(
        user_id=session.user_id,
        conversation_id=session.conversation_id,
        session=session_payload,
    )
    return jsonify({"message": "人工介入已结束", "session": session_payload})
