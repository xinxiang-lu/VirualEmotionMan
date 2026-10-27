from __future__ import annotations

import json
from copy import deepcopy

from ..config import DATA_DIR


SYSTEM_SETTINGS_FILE = DATA_DIR / "system_settings.json"
DEFAULT_CHAT_PROMPT = (
    "你是“心陪陪”，一个面向青年心理陪伴场景的温和、耐心、克制的对话助手。"
    "请优先理解和承接用户情绪，避免诊断式表达，避免过度说教，"
    "给出贴近当下、可执行的小建议。"
)
DEFAULT_DIGITAL_HUMAN_OPTIONS = [
    {
        "code": "haru",
        "label": "Haru",
        "description": "更柔和、安静，适合作为默认陪伴形象。",
    },
    {
        "code": "hiyori",
        "label": "Hiyori Momose",
        "description": "更轻快、明亮，适合作为活泼风格的默认形象。",
    },
]
DEFAULT_DIGITAL_HUMAN_SETTING = {
    "activeCode": DEFAULT_DIGITAL_HUMAN_OPTIONS[0]["code"],
    "options": deepcopy(DEFAULT_DIGITAL_HUMAN_OPTIONS),
}

DEFAULT_PROFILE_MEMORY_TEMPLATE = {
    "version": "v3_simplified",
    "name": "用户动态心理画像模板",
    "description": "定义管理员刷新用户画像时，系统需要从历史对话中整理的核心字段。当前版本保持精简，优先服务演示和复核。",
    "fields": {
        "basic_background": {
            "label": "基础个人信息",
            "type": "text",
            "description": "昵称、账号、性别、年龄、身份/职业，以及历史对话中补充出现的稳定背景信息。",
        },
        "use_purpose": {
            "label": "使用目的",
            "type": "list",
            "description": "用户使用系统的主要目的，例如情绪陪伴、学习压力支持、人际困扰、睡眠改善、持续记录等。",
        },
        "academic_status": {
            "label": "学业状态",
            "type": "text",
            "description": "课程、考试、成绩、学习效率、注意力、学业挫败等信息。",
        },
        "emotion_pattern": {
            "label": "情绪模式",
            "type": "text",
            "description": "近期主要情绪、触发因素、持续方式和情绪波动特点。",
        },
        "risk_signals": {
            "label": "风险信号",
            "type": "list",
            "description": "需要持续观察或触发人工介入的风险线索，例如安全风险、明显功能下降、状态快速恶化等。",
        },
        "recent_context": {
            "label": "近期关键背景",
            "type": "list",
            "description": "最近几轮对话中对理解用户状态很重要的事实或表达。",
        },
        "sleep_and_body": {
            "label": "睡眠与身体状态",
            "type": "text",
            "description": "入睡、早醒、睡眠质量、疲惫、食欲、身体不适等信息。",
        },
        "main_stressors": {
            "label": "主要压力源",
            "type": "list",
            "description": "近期反复出现或对状态影响明显的压力来源，例如考试、学业、人际、家庭、就业等。",
        },
        "intervention_preferences": {
            "label": "干预偏好",
            "type": "list",
            "description": "用户偏好的陪伴方式、称呼、沟通风格、有效策略和无效策略。",
        },
    },
}

DEFAULT_SYSTEM_SETTINGS = {
    "defaultDigitalHuman": deepcopy(DEFAULT_DIGITAL_HUMAN_SETTING),
    "promptTemplate": DEFAULT_CHAT_PROMPT,
    "profileMemoryTemplate": deepcopy(DEFAULT_PROFILE_MEMORY_TEMPLATE),
}


def _normalize_default_digital_human(value) -> dict:
    normalized = deepcopy(DEFAULT_DIGITAL_HUMAN_SETTING)
    if not isinstance(value, dict):
        return normalized

    options = value.get("options")
    if isinstance(options, list):
        normalized_options = []
        seen = set()
        for item in options:
            if not isinstance(item, dict):
                continue
            code = (item.get("code") or "").strip().lower()
            if not code or code in seen:
                continue
            seen.add(code)
            normalized_options.append(
                {
                    "code": code,
                    "label": (item.get("label") or code).strip() or code,
                    "description": (item.get("description") or "").strip(),
                }
            )
        if len(normalized_options) >= 2:
            normalized["options"] = normalized_options[:2]

    available_codes = {item["code"] for item in normalized["options"]}
    active_code = (value.get("activeCode") or value.get("activeModel") or "").strip().lower()
    normalized["activeCode"] = (
        active_code if active_code in available_codes else normalized["options"][0]["code"]
    )
    return normalized


def _normalize_profile_memory_template(value) -> dict:
    normalized = deepcopy(DEFAULT_PROFILE_MEMORY_TEMPLATE)
    if not isinstance(value, dict):
        return normalized

    name = (value.get("name") or normalized["name"]).strip()
    description = (value.get("description") or normalized["description"]).strip()
    fields = value.get("fields") or {}
    if isinstance(fields, list):
        fields = {item.get("key"): item for item in fields if isinstance(item, dict) and item.get("key")}

    normalized_fields = {}
    if isinstance(fields, dict):
        for key, item in fields.items():
            if not isinstance(item, dict):
                continue
            field_key = str(item.get("key") or key or "").strip()
            if not field_key:
                continue
            field_key = "".join(char if char.isalnum() or char == "_" else "_" for char in field_key)
            field_type = (item.get("type") or "text").strip().lower()
            if field_type not in {"text", "list"}:
                field_type = "text"
            normalized_fields[field_key] = {
                "label": (item.get("label") or field_key).strip() or field_key,
                "type": field_type,
                "description": (item.get("description") or "").strip(),
            }

    normalized["name"] = name
    normalized["description"] = description
    raw_version = (value.get("version") or "").strip()
    normalized["version"] = raw_version or f"custom_{len(normalized_fields)}"
    if raw_version and raw_version != DEFAULT_PROFILE_MEMORY_TEMPLATE["version"] and not raw_version.startswith("custom_"):
        merged_fields = deepcopy(DEFAULT_PROFILE_MEMORY_TEMPLATE["fields"])
        for key in list(merged_fields):
            if key in normalized_fields:
                merged_fields[key].update(normalized_fields[key])
        normalized["version"] = DEFAULT_PROFILE_MEMORY_TEMPLATE["version"]
        normalized["fields"] = merged_fields
    else:
        normalized["fields"] = normalized_fields
    return normalized


def load_system_settings() -> dict:
    if not SYSTEM_SETTINGS_FILE.exists():
        return deepcopy(DEFAULT_SYSTEM_SETTINGS)

    try:
        raw = json.loads(SYSTEM_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_SYSTEM_SETTINGS)

    data = deepcopy(DEFAULT_SYSTEM_SETTINGS)
    for key in data:
        if key in raw and raw[key] not in (None, ""):
            if key == "defaultDigitalHuman":
                data[key] = _normalize_default_digital_human(raw[key])
            elif key == "profileMemoryTemplate":
                data[key] = _normalize_profile_memory_template(raw[key])
            else:
                data[key] = raw[key]

    return data


def save_system_settings(payload: dict) -> dict:
    data = load_system_settings()
    for key in data:
        if key not in payload or payload[key] is None:
            continue

        value = payload[key]
        if key == "defaultDigitalHuman":
            current_value = data.get("defaultDigitalHuman") or deepcopy(DEFAULT_DIGITAL_HUMAN_SETTING)
            if isinstance(value, dict):
                value = {
                    "activeCode": value.get("activeCode", current_value.get("activeCode")),
                    "options": value.get("options", current_value.get("options")),
                }
            data[key] = _normalize_default_digital_human(value)
            continue

        if key == "profileMemoryTemplate":
            data[key] = _normalize_profile_memory_template(value)
            continue

        if isinstance(value, str):
            value = value.strip()
        data[key] = value

    SYSTEM_SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _sync_profile_template_file(data.get("profileMemoryTemplate"))
    return data


def _sync_profile_template_file(template: dict | None) -> None:
    if not template:
        return
    path = DATA_DIR / "profile_template.json"
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")


def load_profile_memory_template() -> dict:
    settings = load_system_settings()
    return _normalize_profile_memory_template(settings.get("profileMemoryTemplate"))


def get_default_chat_prompt(fallback: str = "") -> str:
    prompt = (load_system_settings().get("promptTemplate") or "").strip()
    if prompt:
        return prompt
    if fallback:
        return fallback.strip()
    return DEFAULT_CHAT_PROMPT


def get_default_digital_human_code(fallback: str = "haru") -> str:
    setting = load_system_settings().get("defaultDigitalHuman") or {}
    active_code = (setting.get("activeCode") or "").strip().lower()
    if active_code:
        return active_code
    return (fallback or DEFAULT_DIGITAL_HUMAN_SETTING["activeCode"]).strip().lower()

