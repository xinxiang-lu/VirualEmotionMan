from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer
from sqlalchemy.orm import joinedload

from ..models import User


RESET_CODE_TTL_MINUTES = 10
TOKEN_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
_reset_code_store: dict[str, dict[str, datetime | str]] = {}


def store_password(raw_password: str) -> str:
    """
    Temporary plain-text password storage.

    TODO:
    Replace with password hashing before production.
    """
    return raw_password


def check_password(raw_password: str, stored_password: str) -> bool:
    """
    Temporary plain-text password check.

    TODO:
    Replace with hashed password verification before production.
    """
    return raw_password == stored_password


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def create_access_token(user: User) -> str:
    return _serializer().dumps({"user_id": user.id, "role": user.role}, salt="access-token")


def verify_access_token(token: str) -> dict | None:
    try:
        return _serializer().loads(token, salt="access-token", max_age=TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, BadTimeSignature):
        return None


def extract_token() -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.headers.get("X-Access-Token", "").strip()


def load_current_user() -> User | None:
    if hasattr(g, "current_user"):
        return g.current_user

    token = extract_token()
    if not token:
        g.current_user = None
        return None

    token_data = verify_access_token(token)
    if not token_data:
        g.current_user = None
        return None

    user = (
        User.query.options(joinedload(User.profile), joinedload(User.settings))
        .filter(User.id == token_data.get("user_id"))
        .first()
    )
    g.current_user = user
    return user


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if user is None:
            return jsonify({"message": "未登录或登录状态已失效"}), 401
        return view_func(*args, **kwargs)

    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if user is None:
            return jsonify({"message": "未登录或登录状态已失效"}), 401
        if user.role != "admin":
            return jsonify({"message": "当前账号没有管理员权限"}), 403
        return view_func(*args, **kwargs)

    return wrapper


def issue_reset_code(target: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    _reset_code_store[target] = {
        "code": code,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=RESET_CODE_TTL_MINUTES),
    }
    return code


def verify_reset_code(target: str, code: str) -> bool:
    record = _reset_code_store.get(target)
    if not record:
        return False
    if datetime.now(timezone.utc) > record["expires_at"]:
        _reset_code_store.pop(target, None)
        return False
    if record["code"] != code:
        return False
    _reset_code_store.pop(target, None)
    return True
