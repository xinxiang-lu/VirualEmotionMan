from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from ..extensions import db
from ..models import TagLibrary, User, UserProfile, UserProfileGoal, UserSetting
from ..models.base import utcnow
from ..services.oss_service import OSSService, OSSServiceUnavailableError
from ..utils.auth import (
    check_password,
    create_access_token,
    issue_reset_code,
    store_password,
    verify_reset_code,
)
from ..utils.serializers import serialize_user_auth
from ..utils.voice_preferences import VOICE_SPEED_DEFAULT


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/avatar-upload")
def upload_avatar():
    file = request.files.get("file")
    if file is None:
        return jsonify({"message": "请先选择头像文件。"}), 400

    try:
        result = OSSService().upload_avatar(file)
    except OSSServiceUnavailableError as error:
        return jsonify({"message": str(error)}), 503
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    except Exception:
        return jsonify({"message": "头像上传失败，请稍后重试。"}), 500

    return jsonify({"message": "头像上传成功", **result})


def _find_user_by_phone(phone: str, role: str | None = None) -> User | None:
    if not phone:
        return None

    query = User.query.filter(User.phone == phone)
    if role:
        query = query.filter(User.role == role)
    return query.first()


def _resolve_age(age_value) -> int | None:
    if age_value in (None, ""):
        return None

    try:
        age = int(age_value)
    except (TypeError, ValueError) as error:
        raise ValueError("年龄格式不正确。") from error

    if age < 10 or age > 120:
        raise ValueError("年龄范围需在 10 到 120 岁之间。")

    return age


def _find_or_create_usage_goal(raw_value: str) -> TagLibrary | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    tag = TagLibrary.query.filter(
        TagLibrary.tag_type == "usage_goal",
        or_(TagLibrary.name == value, TagLibrary.description == value),
    ).first()
    if tag is not None:
        return tag

    tag = TagLibrary(
        name=value,
        tag_type="usage_goal",
        description=value,
        sort_order=999,
        is_active=True,
    )
    db.session.add(tag)
    db.session.flush()
    return tag


@auth_bp.post("/login")
def user_login():
    payload = request.get_json(silent=True) or {}
    phone = (payload.get("phone") or payload.get("identifier") or "").strip()
    password = payload.get("password") or ""

    if not phone or not password:
        return jsonify({"message": "请填写手机号和密码。"}), 400

    user = _find_user_by_phone(phone, role="user")
    if user is None or not check_password(password, user.password):
        return jsonify({"message": "手机号不存在或密码错误。"}), 401

    user.last_login_at = utcnow()
    db.session.commit()
    return jsonify(
        {
            "message": "登录成功",
            "access_token": create_access_token(user),
            "user": serialize_user_auth(user),
        }
    )


@auth_bp.post("/admin-login")
def admin_login():
    payload = request.get_json(silent=True) or {}
    phone = (payload.get("phone") or payload.get("username") or payload.get("identifier") or "").strip()
    password = payload.get("password") or ""

    if not phone or not password:
        return jsonify({"message": "请填写管理员手机号和密码。"}), 400

    user = _find_user_by_phone(phone, role="admin")
    if user is None or not check_password(password, user.password):
        return jsonify({"message": "管理员手机号不存在或密码错误。"}), 401

    user.last_login_at = utcnow()
    db.session.commit()
    return jsonify(
        {
            "message": "管理员登录成功",
            "access_token": create_access_token(user),
            "user": serialize_user_auth(user),
        }
    )


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    nickname = (payload.get("nickname") or payload.get("username") or "").strip()
    phone = (payload.get("phone") or payload.get("contact") or "").strip()
    password = payload.get("password") or ""
    avatar_url = (payload.get("avatarUrl") or payload.get("avatar_url") or "").strip()
    gender = (payload.get("gender") or "").strip()
    occupation = (payload.get("job") or "").strip()
    age = payload.get("age")
    purpose = (payload.get("purpose") or "").strip()
    purposes = payload.get("purposes") or []
    custom_purpose = (payload.get("customPurpose") or payload.get("custom_purpose") or "").strip()

    if not nickname or not phone or not password:
        return jsonify({"message": "昵称、手机号和密码不能为空。"}), 400

    try:
        profile_age = _resolve_age(age)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    existing_phone_user = _find_user_by_phone(phone)
    if existing_phone_user is not None:
        return jsonify({"message": "手机号已被占用。"}), 409

    user = User(
        phone=phone,
        password=store_password(password),
        role="user",
        last_login_at=utcnow(),
    )
    db.session.add(user)
    db.session.flush()

    db.session.add(
        UserProfile(
            user_id=user.id,
            nickname=nickname,
            gender=gender,
            age=profile_age,
            occupation=occupation,
            avatar_url=avatar_url,
        )
    )
    db.session.add(
        UserSetting(
            user_id=user.id,
            custom_prompt="",
            digital_human_code="温柔陪伴型",
            voice_speed=VOICE_SPEED_DEFAULT,
        )
    )

    selected_purposes = []
    if isinstance(purposes, list):
        selected_purposes.extend([str(item).strip() for item in purposes if str(item).strip()])
    if purpose:
        selected_purposes.append(purpose)
    if custom_purpose:
        selected_purposes.append(custom_purpose)

    seen = set()
    for item in selected_purposes:
        if item in seen:
            continue
        seen.add(item)
        goal_tag = _find_or_create_usage_goal(item)
        if goal_tag:
            db.session.add(UserProfileGoal(user_id=user.id, tag_id=goal_tag.id))

    db.session.commit()
    return (
        jsonify(
            {
                "message": "注册成功",
                "access_token": create_access_token(user),
                "user": serialize_user_auth(user),
            }
        ),
        201,
    )


@auth_bp.post("/forgot-password/code")
def forgot_password_code():
    payload = request.get_json(silent=True) or {}
    phone = (payload.get("phone") or payload.get("contact") or "").strip()
    if not phone:
        return jsonify({"message": "请填写手机号。"}), 400

    user = _find_user_by_phone(phone)
    if user is None:
        return jsonify({"message": "未找到对应手机号。"}), 404

    code = issue_reset_code(phone)
    return jsonify(
        {
            "message": "验证码已生成，当前为开发环境直返验证码。",
            "verification_code": code,
        }
    )


@auth_bp.post("/forgot-password/reset")
def forgot_password_reset():
    payload = request.get_json(silent=True) or {}
    phone = (payload.get("phone") or payload.get("contact") or "").strip()
    code = (payload.get("code") or "").strip()
    password = payload.get("password") or payload.get("new_password") or ""

    if not phone or not code or not password:
        return jsonify({"message": "请完整填写手机号、验证码和新密码。"}), 400

    user = _find_user_by_phone(phone)
    if user is None:
        return jsonify({"message": "未找到对应手机号。"}), 404

    if not verify_reset_code(phone, code):
        return jsonify({"message": "验证码错误或已过期。"}), 400

    user.password = store_password(password)
    user.updated_at = utcnow()
    db.session.commit()
    return jsonify({"message": "密码重置成功"})
