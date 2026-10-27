from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from flask import current_app

from ..extensions import db
from ..models import Conversation, Message, QuestionnaireAnswer, QuestionnaireSession, User, UserProfileMemory, UserProfileMemoryEvent
from .ai import GLMServiceError
from .system_settings import load_profile_memory_template


@dataclass
class ProfileMemoryUpdate:
    field: str
    operation: str
    value: Any
    confidence: float
    evidence: str
    source: str = "rules"


@dataclass
class ProfileMemoryResult:
    updated: bool
    updates: list[ProfileMemoryUpdate]
    memory: dict


class ProfileMemoryService:
    def load_template(self) -> dict:
        return load_profile_memory_template()

    def get_or_create_memory(self, user: User) -> UserProfileMemory:
        memory = UserProfileMemory.query.filter_by(user_id=user.id).first()
        template = self.load_template()
        template_fields = template.get("fields") or {}
        if memory is not None:
            current = self._normalize_memory_to_template(memory.memory_json or {}, template_fields)
            if memory.template_version != (template.get("version") or memory.template_version) or current != (memory.memory_json or {}):
                memory.template_version = template.get("version") or memory.template_version
                memory.memory_json = current
            return memory

        initial_memory = {}
        for field, meta in template_fields.items():
            initial_memory[field] = [] if meta.get("type") == "list" else ""

        memory = UserProfileMemory(
            user_id=user.id,
            template_version=template.get("version") or "v1",
            memory_json=initial_memory,
        )
        db.session.add(memory)
        db.session.flush()
        return memory

    def update_from_message(
        self,
        *,
        user: User,
        conversation: Conversation,
        message: Message,
    ) -> ProfileMemoryResult:
        content = (message.content_text or "").strip()
        memory = self.get_or_create_memory(user)
        updates = self._extract_updates(content)
        return self._apply_updates(
            user=user,
            conversation=conversation,
            message=message,
            memory=memory,
            updates=updates,
        )

    def update_from_history(
        self,
        *,
        user: User,
        dialogue_limit: int = 40,
    ) -> ProfileMemoryResult:
        memory = self.get_or_create_memory(user)
        latest_conversation = (
            Conversation.query.filter_by(user_id=user.id)
            .order_by(Conversation.latest_message_at.desc(), Conversation.updated_at.desc(), Conversation.id.desc())
            .first()
        )
        if latest_conversation is None:
            return ProfileMemoryResult(updated=False, updates=[], memory=dict(memory.memory_json or {}))

        messages = (
            Message.query.join(Conversation, Conversation.id == Message.conversation_id)
            .filter(Conversation.user_id == user.id, Message.sender_type.in_(["user", "assistant", "human"]))
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(max(8, min(int(dialogue_limit or 40), 120)))
            .all()
        )
        messages = list(reversed(messages))
        if not messages:
            return ProfileMemoryResult(updated=False, updates=[], memory=dict(memory.memory_json or {}))

        updates = self._extract_updates_from_history(user=user, messages=messages, memory=memory)
        return self._apply_updates(
            user=user,
            conversation=latest_conversation,
            message=None,
            memory=memory,
            updates=updates,
        )

    def update_from_scale_summary(
        self,
        *,
        user: User,
        conversation: Conversation,
        session: QuestionnaireSession,
        summary: dict,
        answers: list[QuestionnaireAnswer],
    ) -> ProfileMemoryResult:
        memory = self.get_or_create_memory(user)
        profile_updates = summary.get("profile_updates") if isinstance(summary, dict) else {}
        if not isinstance(profile_updates, dict):
            profile_updates = {}

        evidence = "；".join((answer.evidence_text or "").strip() for answer in answers if answer.evidence_text)[:500]
        template_fields = self.load_template().get("fields") or {}
        updates: list[ProfileMemoryUpdate] = []

        for field, value in profile_updates.items():
            if field not in template_fields:
                continue
            operation = "append" if template_fields[field].get("type") == "list" else "upsert"
            updates.append(
                ProfileMemoryUpdate(
                    field=field,
                    operation=operation,
                    value=value,
                    confidence=0.9,
                    evidence=evidence or str(summary.get("summary") or ""),
                    source="completed_scale_assessment",
                )
            )

        if summary.get("summary") and "recent_context" in template_fields:
            updates.append(
                ProfileMemoryUpdate(
                    field="recent_context",
                    operation="append",
                    value=str(summary["summary"])[:180],
                    confidence=0.86,
                    evidence=evidence or str(summary["summary"]),
                    source="completed_scale_assessment",
                )
            )

        result = self._apply_updates(
            user=user,
            conversation=conversation,
            message=None,
            memory=memory,
            updates=updates,
        )
        session.summary_json = {
            **(summary or {}),
            "profile_memory_updated": result.updated,
            "profile_memory_update_count": len(result.updates),
        }
        return result

    def _apply_updates(
        self,
        *,
        user: User,
        conversation: Conversation,
        message: Message | None,
        memory: UserProfileMemory,
        updates: list[ProfileMemoryUpdate],
    ) -> ProfileMemoryResult:
        template_fields = self.load_template().get("fields") or {}
        current_memory = self._normalize_memory_to_template(memory.memory_json or {}, template_fields)
        applied: list[ProfileMemoryUpdate] = []

        for update in updates:
            if update.field not in template_fields:
                continue
            if update.confidence < 0.55:
                continue
            old_value = current_memory.get(update.field)
            new_value = self._merge_value(old_value, update.value)
            if new_value == old_value:
                continue

            current_memory[update.field] = new_value
            applied.append(update)
            db.session.add(
                UserProfileMemoryEvent(
                    memory_id=memory.id,
                    user_id=user.id,
                    conversation_id=conversation.id,
                    message_id=message.id if message is not None else None,
                    field=update.field,
                    operation=update.operation,
                    old_value_json=old_value,
                    new_value_json=new_value,
                    confidence=update.confidence,
                    evidence_text=update.evidence,
                    source=update.source,
                )
            )

        if applied:
            memory.memory_json = current_memory

        return ProfileMemoryResult(updated=bool(applied), updates=applied, memory=current_memory)

    def _normalize_memory_to_template(self, memory_json: dict, template_fields: dict) -> dict:
        normalized = {}
        source = memory_json if isinstance(memory_json, dict) else {}
        for field, meta in template_fields.items():
            if field in source:
                normalized[field] = source[field]
            else:
                normalized[field] = [] if meta.get("type") == "list" else ""
        return normalized

    def _merge_value(self, old_value, new_value):
        if isinstance(old_value, list):
            values = list(old_value)
            candidates = new_value if isinstance(new_value, list) else [new_value]
            for item in candidates:
                text = str(item or "").strip()
                if text and text not in values:
                    values.append(text)
            return values[-12:]

        text = str(new_value or "").strip()
        if not text:
            return old_value
        if not old_value:
            return text
        return text if text != old_value else old_value

    def _extract_updates_from_history(
        self,
        *,
        user: User,
        messages: list[Message],
        memory: UserProfileMemory,
    ) -> list[ProfileMemoryUpdate]:
        template = self.load_template()
        template_fields = template.get("fields") or {}
        if not template_fields:
            return []

        glm_service = current_app.extensions.get("glm_service")
        if glm_service is None or not glm_service.enabled:
            combined = "\n".join((message.content_text or "").strip() for message in messages if message.content_text)
            return self._filter_template_updates(self._extract_updates(combined), template_fields)

        profile = user.profile
        purpose = [relation.tag.description or relation.tag.name for relation in user.profile_goals]
        base_profile = {
            "nickname": profile.nickname if profile and profile.nickname else user.phone,
            "gender": profile.gender if profile and profile.gender else "",
            "age": profile.age if profile else None,
            "occupation": profile.occupation if profile and profile.occupation else "",
            "use_purpose": purpose,
        }
        dialogue = [
            {
                "role": message.sender_type,
                "content": (message.content_text or "").strip()[:500],
            }
            for message in messages
            if (message.content_text or "").strip()
        ]
        prompt_payload = {
            "base_profile": base_profile,
            "current_memory": memory.memory_json or {},
            "profile_template": template,
            "recent_dialogue": dialogue,
        }
        system_prompt = """
你是心陪陪系统的用户画像整理助手。请从历史对话中提取稳定、可追溯的用户画像信息。

要求：
1. 只能更新 profile_template.fields 中存在的字段，不要新增字段。
2. 如果证据不足，字段不要输出；不要猜测、不要诊断、不要编造。
3. text 字段输出一句简洁中文；list 字段输出中文字符串数组。
4. 每个更新必须包含 evidence，引用能支撑判断的用户表达或对话事实。
5. confidence 取 0-1，低于 0.55 的不要输出。
6. 只输出 JSON，不要 Markdown，不要额外解释。

JSON 格式：
{
  "updates": [
    {
      "field": "字段key",
      "operation": "upsert|append",
      "value": "文本或数组",
      "confidence": 0.8,
      "evidence": "依据"
    }
  ]
}
""".strip()
        try:
            raw = glm_service.generate_text(
                messages=[{"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)}],
                system_prompt=system_prompt,
                temperature=0.15,
                max_tokens=1200,
            )
            payload = self._parse_json_response(raw)
            updates = []
            for item in payload.get("updates") or []:
                if not isinstance(item, dict):
                    continue
                field = str(item.get("field") or "").strip()
                if field not in template_fields:
                    continue
                meta = template_fields[field]
                operation = "append" if meta.get("type") == "list" else "upsert"
                updates.append(
                    ProfileMemoryUpdate(
                        field=field,
                        operation=operation,
                        value=item.get("value"),
                        confidence=float(item.get("confidence") or 0),
                        evidence=str(item.get("evidence") or "")[:500],
                        source="admin_history_ai_refresh",
                    )
                )
            return updates
        except (GLMServiceError, ValueError, TypeError, json.JSONDecodeError) as error:
            current_app.logger.warning("Profile memory AI refresh failed, fallback to rules: %s", error)
            combined = "\n".join((message.content_text or "").strip() for message in messages if message.content_text)
            return self._filter_template_updates(self._extract_updates(combined), template_fields)

    def _filter_template_updates(
        self,
        updates: list[ProfileMemoryUpdate],
        template_fields: dict,
    ) -> list[ProfileMemoryUpdate]:
        filtered = []
        for update in updates:
            if update.field not in template_fields:
                continue
            meta = template_fields[update.field]
            filtered.append(
                ProfileMemoryUpdate(
                    field=update.field,
                    operation="append" if meta.get("type") == "list" else "upsert",
                    value=update.value,
                    confidence=update.confidence,
                    evidence=update.evidence,
                    source="admin_history_rules_refresh",
                )
            )
        return filtered

    def _parse_json_response(self, text: str) -> dict:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end >= start:
            cleaned = cleaned[start : end + 1]
        return json.loads(cleaned)

    def _extract_updates(self, content: str) -> list[ProfileMemoryUpdate]:
        if not content:
            return []

        updates: list[ProfileMemoryUpdate] = []

        if self._contains(content, ["大一", "大二", "大三", "大四", "学生", "专业", "大学", "学校"]):
            updates.append(self._update("basic_background", self._clip(f"用户背景线索：{content}"), content, 0.68))

        if self._contains(content, ["考试", "数学", "成绩", "考核", "作业", "课程", "学不进去", "复习", "挂科"]):
            updates.append(self._update("academic_status", self._clip(f"近期学业状态：{content}"), content, 0.82))
            updates.append(self._update("main_stressors", "学业或考试压力", content, 0.78, operation="append"))

        if self._contains(content, ["睡不着", "失眠", "睡眠", "熬夜", "很晚才睡", "睡不好", "醒"]):
            updates.append(self._update("sleep_and_body", self._clip(f"近期睡眠线索：{content}"), content, 0.86))
            updates.append(self._update("risk_signals", "睡眠受损", content, 0.74, operation="append"))

        if self._contains(content, ["低落", "难受", "无力", "崩溃", "完蛋", "沮丧", "没希望", "自责"]):
            updates.append(self._update("emotion_pattern", self._clip(f"近期情绪线索：{content}"), content, 0.82))

        if self._contains(content, ["焦虑", "紧张", "担心", "害怕", "心慌", "不安", "控制不住", "发慌"]):
            updates.append(self._update("anxiety_pattern", self._clip(f"近期焦虑线索：{content}"), content, 0.8))

        if self._contains(content, ["学不进去", "看不进去", "效率", "上课", "作业", "生活", "起不来"]):
            updates.append(self._update("functioning", self._clip(f"近期功能影响：{content}"), content, 0.78))

        if self._contains(content, ["朋友", "同学", "室友", "老师", "家人", "父母", "没人", "一个人"]):
            updates.append(self._update("support_system", self._clip(f"支持系统线索：{content}"), content, 0.72))

        if self._contains(content, ["呼吸", "散步", "听歌", "写下来", "运动", "找人聊", "休息", "刷视频", "逃避"]):
            updates.append(
                self._update(
                    "intervention_preferences",
                    self._clip(f"应对方式线索：{content}"),
                    content,
                    0.68,
                    operation="append",
                )
            )

        if self._contains(content, ["自杀", "自伤", "轻生", "不想活", "活不下去", "死了算了", "结束自己"]):
            updates.append(self._update("risk_signals", "明确安全风险表达", content, 0.95, operation="append"))

        if updates:
            updates.append(self._update("recent_context", self._clip(content, limit=120), content, 0.65, operation="append"))
        return updates

    def _update(
        self,
        field: str,
        value: Any,
        evidence: str,
        confidence: float,
        *,
        operation: str = "upsert",
    ) -> ProfileMemoryUpdate:
        return ProfileMemoryUpdate(
            field=field,
            operation=operation,
            value=value,
            confidence=confidence,
            evidence=evidence,
        )

    def _contains(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _clip(self, text: str, *, limit: int = 160) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 1].rstrip()}..."
