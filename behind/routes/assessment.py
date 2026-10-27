from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Assessment, AssessmentTag, Conversation, TagLibrary, User
from ..models.base import utcnow
from ..services.ai import UserAssessmentService, UserAssessmentServiceError
from ..utils.auth import load_current_user, login_required
from ..utils.serializers import (
    build_assessment_cards,
    get_latest_user_assessment,
    serialize_assessment_summary,
)


assessment_bp = Blueprint("assessment", __name__, url_prefix="/api")


def _get_target_user(user_id: int | None = None) -> User | None:
    if user_id is None:
        return load_current_user()

    current_user = load_current_user()
    if current_user.role == "admin":
        return User.query.get(user_id)
    if current_user.id == user_id:
        return current_user
    return None


@assessment_bp.get("/assessment/dashboard")
@login_required
def assessment_dashboard():
    user = load_current_user()
    latest_item = get_latest_user_assessment(user)
    return jsonify(
        {
            "summary": serialize_assessment_summary(latest_item),
            "cards": build_assessment_cards(latest_item),
        }
    )


@assessment_bp.post("/assessment/generate")
@login_required
def generate_assessment():
    user = load_current_user()
    if user.role != "user":
        return jsonify({"message": "仅普通用户可生成状态评估"}), 403

    payload = request.get_json(silent=True) or {}
    conversation = None
    conversation_id = payload.get("conversation_id")
    if conversation_id:
        conversation = Conversation.query.filter_by(id=conversation_id, user_id=user.id).first()
        if conversation is None:
            return jsonify({"message": "未找到对应会话"}), 404

    service = UserAssessmentService()
    try:
        result = service.generate_for_user(
            user,
            conversation=conversation,
            dialogue_limit=int(payload.get("dialogue_limit") or 16),
            multimodal_limit=int(payload.get("multimodal_limit") or 3),
        )
    except UserAssessmentServiceError as error:
        message = str(error)
        status_code = 503 if "GLM" in message else 400
        return jsonify({"message": message}), status_code

    assessment = Assessment(
        user_id=user.id,
        conversation_id=conversation.id if conversation is not None else result.context.get("conversation_id"),
        source="user_status_assessment",
        mood_summary=result.mood_summary,
        stress_index=result.stress_index,
        risk_level=result.risk_level,
        advice=result.advice,
        raw_result_json={
            "trend": result.trend,
            "core_psychological_issue": result.core_psychological_issue,
            "context": result.context,
            "raw_response": result.raw_response,
            "trigger": "user_manual_generate",
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
            "message": "状态评估已生成",
            "summary": serialize_assessment_summary(assessment),
            "cards": build_assessment_cards(assessment),
            "assessment": {
                "assessmentId": assessment.id,
                "stressIndexValue": assessment.stress_index,
                "riskCode": assessment.risk_level,
                "evaluatedAt": assessment.evaluated_at.isoformat() if assessment.evaluated_at else None,
            },
        }
    )


@assessment_bp.get("/assessments/latest/<int:user_id>")
@login_required
def latest_assessment(user_id: int):
    user = _get_target_user(user_id)
    if user is None:
        return jsonify({"message": "没有权限查看该用户的评估结果"}), 403

    latest_item = get_latest_user_assessment(user)
    return jsonify(
        {
            "summary": serialize_assessment_summary(latest_item),
            "cards": build_assessment_cards(latest_item),
        }
    )
