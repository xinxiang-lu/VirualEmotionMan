from __future__ import annotations

from flask import request
from flask_socketio import disconnect, emit, join_room, leave_room

from ..extensions import socketio
from ..models import Conversation, User
from .auth import verify_access_token

_SOCKET_USERS: dict[str, dict] = {}


def conversation_room(conversation_id: int) -> str:
    return f"conversation:{conversation_id}"


def user_room(user_id: int) -> str:
    return f"user:{user_id}"


def admin_room() -> str:
    return "admins"


def _socket_user() -> User | None:
    socket_info = _SOCKET_USERS.get(request.sid) or {}
    user_id = socket_info.get("user_id")
    if user_id is None:
        return None
    return User.query.get(user_id)


def _can_join_conversation(user: User, conversation: Conversation | None) -> bool:
    if conversation is None:
        return False
    return user.role == "admin" or conversation.user_id == user.id


def register_socketio_handlers() -> None:
    @socketio.on("connect")
    def _connect(auth=None):
        token = ""
        if isinstance(auth, dict):
            token = str(auth.get("token") or "")
        token_data = verify_access_token(token)
        if not token_data:
            return False

        user = User.query.get(token_data.get("user_id"))
        if user is None:
            return False

        _SOCKET_USERS[request.sid] = {"user_id": user.id, "role": user.role}
        join_room(user_room(user.id))
        if user.role == "admin":
            join_room(admin_room())
        emit("socket:ready", {"userId": user.id, "role": user.role})

    @socketio.on("disconnect")
    def _disconnect():
        _SOCKET_USERS.pop(request.sid, None)

    @socketio.on("join_conversation")
    def _join_conversation(payload=None):
        user = _socket_user()
        if user is None:
            disconnect()
            return

        conversation_id = None
        if isinstance(payload, dict):
            conversation_id = payload.get("conversationId") or payload.get("conversation_id")
        try:
            conversation_id = int(conversation_id)
        except (TypeError, ValueError):
            emit("socket:error", {"message": "conversationId 无效"})
            return

        conversation = Conversation.query.get(conversation_id)
        if not _can_join_conversation(user, conversation):
            emit("socket:error", {"message": "没有权限加入该会话"})
            return

        join_room(conversation_room(conversation_id))
        emit("conversation:joined", {"conversationId": conversation_id})

    @socketio.on("leave_conversation")
    def _leave_conversation(payload=None):
        conversation_id = None
        if isinstance(payload, dict):
            conversation_id = payload.get("conversationId") or payload.get("conversation_id")
        try:
            conversation_id = int(conversation_id)
        except (TypeError, ValueError):
            return
        leave_room(conversation_room(conversation_id))


def emit_conversation_event(conversation_id: int, event: str, payload: dict) -> None:
    socketio.emit(event, payload, to=conversation_room(conversation_id))


def emit_user_event(user_id: int, event: str, payload: dict) -> None:
    socketio.emit(event, payload, to=user_room(user_id))


def emit_admin_event(event: str, payload: dict) -> None:
    socketio.emit(event, payload, to=admin_room())


def emit_message_created(*, conversation_id: int, user_id: int, message: dict, conversation: dict | None = None) -> None:
    payload = {
        "conversationId": conversation_id,
        "userId": user_id,
        "message": message,
        "conversation": conversation,
    }
    emit_conversation_event(conversation_id, "message:new", payload)
    emit_user_event(user_id, "message:new", payload)
    emit_admin_event("message:new", payload)


def emit_questionnaire_updated(*, conversation_id: int, user_id: int, questionnaire: dict | None) -> None:
    payload = {
        "conversationId": conversation_id,
        "userId": user_id,
        "questionnaire": questionnaire,
    }
    emit_conversation_event(conversation_id, "questionnaire:updated", payload)
    emit_user_event(user_id, "questionnaire:updated", payload)
    emit_admin_event("questionnaire:updated", payload)


def emit_intervention_requested(*, user_id: int, conversation: dict, request_message: dict) -> None:
    emit_admin_event(
        "intervention:requested",
        {
            "userId": user_id,
            "conversationId": conversation.get("id"),
            "conversation": conversation,
            "requestMessage": request_message,
        },
    )


def emit_intervention_started(*, user_id: int, conversation_id: int, session: dict) -> None:
    payload = {"userId": user_id, "conversationId": conversation_id, "session": session}
    emit_conversation_event(conversation_id, "intervention:started", payload)
    emit_user_event(user_id, "intervention:started", payload)
    emit_admin_event("intervention:started", payload)


def emit_intervention_ended(*, user_id: int, conversation_id: int, session: dict) -> None:
    payload = {"userId": user_id, "conversationId": conversation_id, "session": session}
    emit_conversation_event(conversation_id, "intervention:ended", payload)
    emit_user_event(user_id, "intervention:ended", payload)
    emit_admin_event("intervention:ended", payload)
