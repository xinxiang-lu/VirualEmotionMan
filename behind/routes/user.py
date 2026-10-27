from __future__ import annotations

from sqlalchemy import or_
from flask import Blueprint, current_app, jsonify, request, send_file

from ..extensions import db
from ..models import TagLibrary, User, UserProfile, UserProfileGoal, UserSetting
from ..utils.auth import load_current_user, login_required
from ..utils.serializers import serialize_profile, serialize_settings
from ..utils.voice_preferences import VOICE_SPEED_DEFAULT, normalize_voice_speed


user_bp = Blueprint("user", __name__, url_prefix="/api/users")


@user_bp.get("/me/profile")
@login_required
def my_profile():
    return jsonify({"profile": serialize_profile(load_current_user())})


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


@user_bp.put("/me/profile")
@login_required
def update_my_profile():
    user = load_current_user()
    payload = request.get_json(silent=True) or {}

    phone = (payload.get("phone") or "").strip()
    nickname = (payload.get("nickname") or "").strip()
    gender = (payload.get("gender") or "").strip()
    occupation = (payload.get("job") or payload.get("occupation") or "").strip()
    avatar_url = (payload.get("avatarUrl") or payload.get("avatar_url") or "").strip()
    age_value = payload.get("age")
    purposes = payload.get("purposes") or []
    custom_purpose = (payload.get("customPurpose") or payload.get("custom_purpose") or "").strip()

    if not phone:
        return jsonify({"message": "手机号不能为空"}), 400
    if not nickname:
        return jsonify({"message": "昵称不能为空"}), 400

    try:
        age = int(age_value) if age_value not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"message": "年龄格式不正确"}), 400

    if age is not None and (age < 10 or age > 120):
        return jsonify({"message": "年龄范围需在 10 到 120 岁之间"}), 400

    existing_phone_user = User.query.filter(User.id != user.id, User.phone == phone).first()
    if existing_phone_user is not None:
        return jsonify({"message": "手机号已被占用"}), 409

    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.session.add(profile)

    user.phone = phone
    profile.nickname = nickname
    profile.gender = gender
    profile.age = age
    profile.occupation = occupation
    profile.avatar_url = avatar_url

    selected_purposes = []
    if isinstance(purposes, list):
        selected_purposes.extend([str(item).strip() for item in purposes if str(item).strip()])
    if custom_purpose:
        selected_purposes.append(custom_purpose)

    unique_purposes = []
    seen = set()
    for item in selected_purposes:
        if item in seen:
            continue
        seen.add(item)
        unique_purposes.append(item)

    UserProfileGoal.query.filter_by(user_id=user.id).delete()
    for item in unique_purposes:
        goal_tag = _find_or_create_usage_goal(item)
        if goal_tag is not None:
            db.session.add(UserProfileGoal(user_id=user.id, tag_id=goal_tag.id))

    db.session.commit()
    return jsonify({"message": "个人信息已更新", "profile": serialize_profile(user)})


@user_bp.get("/me/settings")
@login_required
def my_settings():
    return jsonify({"settings": serialize_settings(load_current_user())})


@user_bp.get("/digital-human-identities")
@login_required
def list_digital_human_identities():
    identity_service = current_app.extensions.get("digital_human_identity_service")
    if identity_service is None:
        return jsonify({"identities": []})

    return jsonify(
        {
            "identities": [
                {
                    "code": item["code"],
                    "label": item["label"],
                    "portraitUrl": item["portrait_url"],
                    "modelPath": item["model_url"],
                }
                for item in identity_service.list_identities()
            ]
        }
    )


@user_bp.get("/digital-human-identities/<string:code>/portrait")
@login_required
def get_digital_human_identity_portrait(code: str):
    identity_service = current_app.extensions.get("digital_human_identity_service")
    if identity_service is None:
        return jsonify({"message": "数字人身份服务不可用"}), 503

    portrait_path = identity_service.get_portrait_path(code)
    if portrait_path is None or not portrait_path.exists():
        return jsonify({"message": "数字人形象图片不存在"}), 404

    return send_file(
        portrait_path,
        mimetype=identity_service.get_portrait_mimetype(portrait_path),
        as_attachment=False,
        download_name=portrait_path.name,
    )


@user_bp.put("/me/settings")
@login_required
def update_my_settings():
    user = load_current_user()
    payload = request.get_json(silent=True) or {}
    identity_service = current_app.extensions.get("digital_human_identity_service")

    settings = user.settings
    if settings is None:
        settings = UserSetting(user_id=user.id)
        db.session.add(settings)

    if "systemPrompt" in payload:
        settings.custom_prompt = payload.get("systemPrompt") or ""
    if "avatar" in payload:
        next_avatar = (payload.get("avatar") or "").strip()
        if next_avatar and identity_service is not None and identity_service.get_identity(next_avatar) is None:
            return jsonify({"message": "所选数字人形象不存在"}), 400
        settings.digital_human_code = next_avatar
    if "voiceSpeed" in payload:
        try:
            settings.voice_speed = normalize_voice_speed(payload.get("voiceSpeed"), fallback=VOICE_SPEED_DEFAULT)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400

    db.session.commit()
    return jsonify({"message": "个性化设置已更新", "settings": serialize_settings(user)})
