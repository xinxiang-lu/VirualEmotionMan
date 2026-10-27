from __future__ import annotations

from ..models import Conversation, InterventionSession, Message


TRANSFER_REQUEST_CONTENT_TYPE = "transfer_request"
TRANSFER_REQUEST_MESSAGE = "已发起转人工申请，管理员会尽快介入当前会话。"


def get_active_intervention_for_user(user_id: int) -> InterventionSession | None:
    return (
        InterventionSession.query.filter_by(user_id=user_id, status="active")
        .order_by(InterventionSession.started_at.desc(), InterventionSession.id.desc())
        .first()
    )


def get_latest_transfer_request_for_user(user_id: int) -> Message | None:
    return (
        Message.query.join(Conversation, Conversation.id == Message.conversation_id)
        .filter(
            Conversation.user_id == user_id,
            Message.sender_type == "system",
            Message.content_type == TRANSFER_REQUEST_CONTENT_TYPE,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )


def get_pending_transfer_request_for_user(user_id: int) -> Message | None:
    latest_request = get_latest_transfer_request_for_user(user_id)
    if latest_request is None:
        return None

    handled_session = (
        InterventionSession.query.filter(
            InterventionSession.user_id == user_id,
            InterventionSession.started_at >= latest_request.created_at,
        )
        .order_by(InterventionSession.started_at.desc(), InterventionSession.id.desc())
        .first()
    )
    if handled_session is not None:
        return None
    return latest_request
