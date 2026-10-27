from __future__ import annotations

import json
from dataclasses import dataclass

from flask import current_app

from ...models import Assessment, Conversation, InterventionSession, Message, User
from .glm import GLMServiceError
from .prompts import get_profile_report_prompt
from .rag import resolve_rag_context
from .shared import RISK_LEVEL_LABELS


class ProfileReportServiceError(RuntimeError):
    """Raised when admin profile report generation cannot be completed."""


@dataclass
class ProfileReportResult:
    markdown: str
    context: dict


class ProfileReportService:
    def build_context(
        self,
        user: User,
        *,
        assessment_limit: int = 8,
        dialogue_limit: int = 24,
        strategy_limit: int = 8,
    ) -> dict:
        context = {
            "user_profile": self._user_profile(user),
            "historical_psych_state_logs": self._historical_assessments(user, limit=assessment_limit),
            "historical_strategies_logs": self._historical_strategies(user, limit=strategy_limit),
            "recent_dialogue_records": self._recent_dialogue(user, limit=dialogue_limit),
        }
        rag_context = resolve_rag_context("admin_profile_report", user=user, context=context)
        if rag_context:
            context["rag_context"] = rag_context
        return context

    def generate_for_user(
        self,
        user: User,
        *,
        assessment_limit: int = 8,
        dialogue_limit: int = 24,
        strategy_limit: int = 8,
    ) -> ProfileReportResult:
        context = self.build_context(
            user,
            assessment_limit=assessment_limit,
            dialogue_limit=dialogue_limit,
            strategy_limit=strategy_limit,
        )

        if not context["historical_psych_state_logs"] and not context["recent_dialogue_records"]:
            raise ProfileReportServiceError("缺少历史状态与近期对话，暂时无法生成心理档案报告")

        glm_service = current_app.extensions.get("glm_service")
        if glm_service is None:
            raise ProfileReportServiceError("当前未接入 GLM 服务，无法生成心理档案报告")

        payload_text = json.dumps(context, ensure_ascii=False, indent=2)
        try:
            markdown = glm_service.generate_text(
                messages=[{"role": "user", "content": payload_text}],
                system_prompt=get_profile_report_prompt(current_app, context["user_profile"]["nickname"]),
                temperature=0.35,
                max_tokens=1800,
            )
        except GLMServiceError as error:
            raise ProfileReportServiceError(str(error)) from error

        normalized = self._normalize_markdown(markdown, context["user_profile"]["nickname"])
        if not normalized:
            raise ProfileReportServiceError("模型未返回有效的心理档案报告")

        return ProfileReportResult(markdown=normalized, context=context)

    def _user_profile(self, user: User) -> dict:
        profile = user.profile
        nickname = self._safe_profile_text(profile.nickname if profile else "", fallback=user.phone or "该用户")
        gender = self._safe_profile_text(profile.gender if profile else "", fallback="未记录")
        occupation = self._safe_profile_text(profile.occupation if profile else "", fallback="未记录")
        return {
            "nickname": nickname,
            "gender": gender,
            "age": profile.age if profile and profile.age is not None else "未记录",
            "occupation": occupation,
            "use_purpose": [relation.tag.description or relation.tag.name for relation in user.profile_goals],
            "support_system": "当前缺少结构化支持系统记录",
            "joined_at": user.created_at.isoformat() if user.created_at else None,
        }

    def _historical_assessments(self, user: User, *, limit: int) -> list[dict]:
        rows = (
            Assessment.query.filter_by(user_id=user.id)
            .order_by(Assessment.evaluated_at.desc(), Assessment.id.desc())
            .limit(limit)
            .all()
        )
        result = []
        for item in reversed(rows):
            raw = item.raw_result_json if isinstance(item.raw_result_json, dict) else {}
            result.append(
                {
                    "assessment_id": item.id,
                    "source": item.source,
                    "evaluated_at": item.evaluated_at.isoformat() if item.evaluated_at else None,
                    "risk_level": RISK_LEVEL_LABELS.get(item.risk_level or "", "尚未评估"),
                    "mood_summary": item.mood_summary or "",
                    "trend": raw.get("trend", ""),
                    "risk_reason": raw.get("risk_reason", ""),
                    "core_psychological_issue": raw.get("core_psychological_issue", ""),
                    "advice": item.advice or "",
                    "tags": [relation.tag.name for relation in item.tags],
                }
            )
        return result

    def _historical_strategies(self, user: User, *, limit: int) -> list[dict]:
        strategies = []

        assessments = (
            Assessment.query.filter_by(user_id=user.id)
            .order_by(Assessment.evaluated_at.desc(), Assessment.id.desc())
            .limit(limit)
            .all()
        )
        for item in assessments:
            if item.advice:
                strategies.append(
                    {
                        "type": "system_advice",
                        "time": item.evaluated_at.isoformat() if item.evaluated_at else None,
                        "content": item.advice,
                        "source": item.source,
                    }
                )

        sessions = (
            InterventionSession.query.filter_by(user_id=user.id)
            .order_by(InterventionSession.started_at.desc(), InterventionSession.id.desc())
            .limit(limit)
            .all()
        )
        for session in sessions:
            human_messages = (
                Message.query.filter_by(intervention_session_id=session.id, sender_type="human")
                .order_by(Message.created_at.asc(), Message.id.asc())
                .all()
            )
            strategies.append(
                {
                    "type": "admin_intervention",
                    "time": session.started_at.isoformat() if session.started_at else None,
                    "status": session.status,
                    "note": session.note or "",
                    "message_count": len(human_messages),
                    "sample_messages": [item.content_text or "" for item in human_messages[:3]],
                }
            )

        strategies.sort(key=lambda item: item.get("time") or "", reverse=True)
        return strategies[:limit]

    def _recent_dialogue(self, user: User, *, limit: int) -> list[dict]:
        messages = (
            Message.query.join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
            .all()
        )

        result = []
        for item in reversed(messages):
            content = (item.content_text or "").strip()
            if not content:
                continue

            role = "assistant"
            if item.sender_type == "user":
                role = "user"
            elif item.sender_type == "human":
                role = "admin"
            elif item.sender_type == "system":
                role = "system"

            multimodal_summary = None
            if item.multimodal_analysis is not None:
                payload = item.multimodal_analysis.get_summary_payload() or {}
                multimodal_summary = {
                    "analysis_mode": payload.get("analysis_mode"),
                    "overall_summary": payload.get("overall_summary"),
                    "event_tags": payload.get("event_tags"),
                    "transcript_text": payload.get("transcript_text"),
                }

            result.append(
                {
                    "message_id": item.id,
                    "conversation_id": item.conversation_id,
                    "role": role,
                    "content": content,
                    "content_type": item.content_type,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "multimodal_summary": multimodal_summary,
                }
            )
        return result

    def _normalize_markdown(self, markdown: str, nickname: str) -> str:
        text = (markdown or "").strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        if not text:
            return ""

        safe_nickname = self._safe_profile_text(nickname, fallback="该用户")
        required_title = f"# 心理档案总结报告 - {safe_nickname}"
        text = text.replace("{{user_profile.nickname}}", safe_nickname)
        lines = text.splitlines()
        title_replaced = False
        for index, line in enumerate(lines):
            if line.strip().startswith("# 心理档案总结报告 -"):
                lines[index] = required_title
                title_replaced = True
                break
        text = "\n".join(lines).strip()
        if not title_replaced:
            text = f"{required_title}\n\n{text}"
        return text

    def _safe_profile_text(self, value, *, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        normalized = text.replace("？", "?").replace(" ", "")
        if normalized and set(normalized) == {"?"}:
            return fallback
        return text
