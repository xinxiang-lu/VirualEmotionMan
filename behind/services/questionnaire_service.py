from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flask import current_app

from ..extensions import db
from ..models import (
    Conversation,
    Message,
    QuestionnaireAnswer,
    QuestionnaireScore,
    QuestionnaireSession,
    User,
)
from ..models.base import utcnow
from .profile_memory_service import ProfileMemoryService


@dataclass
class QuestionnaireAnswerDraft:
    item_code: str
    dimension: str
    score: int
    evidence: str
    confidence: float
    source: str = "scale_session_rules"


@dataclass
class QuestionnaireScoreResult:
    total_score: int
    stress_index: int
    risk_level: str
    dimension_scores: dict[str, int]
    basis: dict[str, Any]
    answer_count: int


@dataclass
class QuestionnaireProcessResult:
    answers: list[QuestionnaireAnswer] = field(default_factory=list)
    score: QuestionnaireScoreResult | None = None
    next_question: str = ""
    triggered_dimensions: list[str] = field(default_factory=list)
    session: QuestionnaireSession | None = None
    status: str = "normal_chat"
    scale_id: str = ""
    scale_name: str = ""
    completed: bool = False
    message: str = ""


class QuestionnaireService:
    NORMAL_CHAT_STATUS = "normal_chat"
    ACTIVE_STATUS = "assessment_active"
    COMPLETED_STATUS = "assessment_completed"
    INVALID_STATUS = "assessment_invalid"

    def load_config(self) -> dict:
        path = Path(current_app.config.get("QUESTIONNAIRE_ITEMS_PATH", ""))
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"scales": []}

    def save_config(self, config: dict) -> None:
        path = Path(current_app.config.get("QUESTIONNAIRE_ITEMS_PATH", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_scales(self) -> list[dict]:
        return list(self.load_config().get("scales") or [])

    def load_items(self) -> list[dict]:
        items = []
        for scale in self.load_scales():
            for item in scale.get("items") or []:
                items.append({**item, "scale_id": scale.get("id"), "scale_name": scale.get("name")})
        return items

    def list_scales(self) -> list[dict]:
        return [self.serialize_scale(scale, include_items=False) for scale in self.load_scales()]

    def list_scale_details(self) -> list[dict]:
        return [self.serialize_scale(scale, include_items=True) for scale in self.load_scales()]

    def serialize_scale(self, scale: dict, *, include_items: bool = True) -> dict:
        payload = {
            "id": scale.get("id"),
            "name": scale.get("name"),
            "label": scale.get("label"),
            "description": scale.get("description"),
            "timeWindow": scale.get("timeWindow"),
            "scoreRange": scale.get("scoreRange"),
            "itemCount": len(scale.get("items") or []),
            "severity": scale.get("severity") or [],
        }
        if include_items:
            payload["items"] = [
                {
                    "code": item.get("code"),
                    "dimension": item.get("dimension"),
                    "construct": item.get("construct"),
                    "prompt": item.get("prompt"),
                    "keywords": item.get("keywords") or [],
                    "maxScore": item.get("max_score") or item.get("maxScore") or 3,
                    "redline": bool(item.get("redline")),
                    "options": self.score_options(int(item.get("max_score") or item.get("maxScore") or 3)),
                }
                for item in scale.get("items") or []
            ]
        return payload

    def score_options(self, max_score: int) -> list[dict]:
        if max_score >= 4:
            labels = ["无", "轻度", "中度", "重度", "非常严重"]
        else:
            labels = ["没有", "偶尔/几天", "经常/一半以上时间", "几乎每天/非常明显"]
        return [{"score": score, "label": labels[min(score, len(labels) - 1)]} for score in range(max_score + 1)]

    def create_scale(self, payload: dict) -> dict:
        config = self.load_config()
        scales = list(config.get("scales") or [])
        scale = self._normalize_scale_payload(payload)
        if any(str(item.get("id") or "").upper() == scale["id"] for item in scales):
            raise ValueError("量表 ID 已存在")
        scales.append(scale)
        config["scales"] = scales
        self.save_config(config)
        return scale

    def update_scale(self, scale_id: str, payload: dict) -> dict:
        config = self.load_config()
        scales = list(config.get("scales") or [])
        target = str(scale_id or "").strip().upper()
        for index, scale in enumerate(scales):
            if str(scale.get("id") or "").strip().upper() == target:
                next_payload = {**scale, **payload, "id": scale.get("id")}
                scales[index] = self._normalize_scale_payload(next_payload)
                config["scales"] = scales
                self.save_config(config)
                return scales[index]
        raise ValueError("量表不存在")

    def delete_scale(self, scale_id: str) -> None:
        config = self.load_config()
        scales = list(config.get("scales") or [])
        target = str(scale_id or "").strip().upper()
        kept = [scale for scale in scales if str(scale.get("id") or "").strip().upper() != target]
        if len(kept) == len(scales):
            raise ValueError("量表不存在")
        config["scales"] = kept
        self.save_config(config)

    def _normalize_scale_payload(self, payload: dict) -> dict:
        scale_id = str(payload.get("id") or payload.get("scaleId") or "").strip().upper()
        name = str(payload.get("name") or scale_id).strip()
        label = str(payload.get("label") or name).strip()
        description = str(payload.get("description") or "").strip()
        time_window = str(payload.get("timeWindow") or payload.get("time_window") or "最近两周").strip()
        items = payload.get("items") or []
        if not scale_id:
            raise ValueError("量表 ID 不能为空")
        if not name:
            raise ValueError("量表名称不能为空")
        if not isinstance(items, list) or not items:
            raise ValueError("量表至少需要一个题项")

        normalized_items = []
        max_total = 0
        for index, item in enumerate(items, start=1):
            max_score = int(item.get("max_score") or item.get("maxScore") or 3)
            if max_score < 1:
                max_score = 1
            code = str(item.get("code") or f"{scale_id.lower()}_{index:02d}").strip()
            prompt = str(item.get("prompt") or "").strip()
            if not prompt:
                raise ValueError(f"第 {index} 个题项的问题不能为空")
            max_total += max_score
            keywords = item.get("keywords") or []
            if isinstance(keywords, str):
                keywords = [part.strip() for part in keywords.replace("，", ",").split(",") if part.strip()]
            normalized_items.append(
                {
                    "code": code,
                    "dimension": str(item.get("dimension") or "custom").strip(),
                    "construct": str(item.get("construct") or prompt[:24]).strip(),
                    "prompt": prompt,
                    "keywords": keywords,
                    "max_score": max_score,
                    **({"redline": True} if item.get("redline") else {}),
                }
            )

        return {
            "id": scale_id,
            "name": name,
            "label": label,
            "description": description,
            "timeWindow": time_window,
            "scoreRange": f"0-{max_total}",
            "completionRequired": len(normalized_items),
            "severity": payload.get("severity") or self._default_severity(max_total),
            "items": normalized_items,
        }

    def _default_severity(self, max_total: int) -> list[dict]:
        low_max = max(1, round(max_total * 0.25))
        medium_max = max(low_max + 1, round(max_total * 0.65))
        return [
            {"level": "low", "min": 0, "max": low_max, "label": "低风险或轻微波动"},
            {"level": "medium", "min": low_max + 1, "max": medium_max, "label": "需要关注的中等风险"},
            {"level": "high", "min": medium_max + 1, "max": max_total, "label": "高风险关注"},
        ]

    def start_session(
        self,
        *,
        user: User,
        conversation: Conversation,
        scale_id: str,
    ) -> QuestionnaireProcessResult:
        scale = self._scale_by_id(scale_id)
        if scale is None:
            raise ValueError("量表不存在")

        active = self.get_active_session(user=user, conversation=conversation)
        if active is not None and active.scale_id != scale.get("id"):
            return QuestionnaireProcessResult(
                session=active,
                status=active.status,
                scale_id=active.scale_id or "",
                scale_name=active.scale_name or "",
                next_question=active.last_question_text or "",
                message="当前会话已有进行中的量表，请先完成或作废后再切换。",
            )

        if active is None:
            first_item = (scale.get("items") or [None])[0]
            active = QuestionnaireSession(
                user_id=user.id,
                conversation_id=conversation.id,
                scale_id=scale.get("id") or "",
                scale_name=scale.get("name") or "",
                status=self.ACTIVE_STATUS,
                active_dimension=first_item.get("dimension") if first_item else None,
                pending_item_code=first_item.get("code") if first_item else None,
                last_question_text=first_item.get("prompt") if first_item else "",
                required_item_count=len(scale.get("items") or []),
                answered_item_count=0,
            )
            db.session.add(active)
            db.session.flush()

        return QuestionnaireProcessResult(
            session=active,
            status=active.status,
            scale_id=active.scale_id or "",
            scale_name=active.scale_name or "",
            next_question=active.last_question_text or "",
            message=f"已开始 {active.scale_name} 对话式评估。",
        )

    def invalidate_active_session(self, *, user: User, conversation: Conversation) -> QuestionnaireSession | None:
        session = self.get_active_session(user=user, conversation=conversation)
        if session is None:
            return None
        session.status = self.INVALID_STATUS
        session.updated_at = utcnow()
        return session

    def get_active_session(self, *, user: User, conversation: Conversation) -> QuestionnaireSession | None:
        return (
            QuestionnaireSession.query.filter_by(
                user_id=user.id,
                conversation_id=conversation.id,
                status=self.ACTIVE_STATUS,
            )
            .order_by(QuestionnaireSession.created_at.desc(), QuestionnaireSession.id.desc())
            .first()
        )

    def process_user_message(
        self,
        *,
        user: User,
        conversation: Conversation,
        message: Message,
    ) -> QuestionnaireProcessResult:
        content = (message.content_text or "").strip()
        if not content:
            return QuestionnaireProcessResult()

        session = self.get_active_session(user=user, conversation=conversation)
        if session is None:
            return QuestionnaireProcessResult(
                status=self.NORMAL_CHAT_STATUS,
                message="普通聊天未进入正式量表评估，本轮只用于动态画像沉淀。",
            )

        scale = self._scale_by_id(session.scale_id)
        if scale is None:
            session.status = self.INVALID_STATUS
            session.updated_at = utcnow()
            return QuestionnaireProcessResult(
                session=session,
                status=session.status,
                message="当前量表配置不存在，本次评估已作废。",
            )

        pending_item = self._item_by_code(scale, session.pending_item_code)
        if pending_item is None:
            pending_item = self._first_unanswered_item(user=user, conversation=conversation, scale=scale, session=session)

        drafts = []
        if pending_item is not None:
            score, confidence, source = self._score_content(content, pending_item)
            if confidence >= 0.45:
                drafts.append(
                    QuestionnaireAnswerDraft(
                        item_code=pending_item.get("code") or "",
                        dimension=pending_item.get("dimension") or "unknown",
                        score=score,
                        evidence=content,
                        confidence=confidence,
                        source=source,
                    )
                )

        answers = self._persist_answers(user, conversation, message, session, drafts)
        completed_score = self._complete_if_ready(user=user, conversation=conversation, session=session, scale=scale)

        if completed_score is None:
            next_item = self._first_unanswered_item(user=user, conversation=conversation, scale=scale, session=session)
            if next_item is not None and answers:
                session.pending_item_code = next_item.get("code")
                session.active_dimension = next_item.get("dimension")
                session.last_question_text = next_item.get("prompt") or ""
            elif pending_item is not None and not answers:
                session.pending_item_code = pending_item.get("code")
                session.active_dimension = pending_item.get("dimension")
                session.last_question_text = self._follow_up_prompt(pending_item)
            session.answered_item_count = self._answered_count(user=user, conversation=conversation, session=session)
            session.updated_at = utcnow()

        next_question = "" if completed_score else (session.last_question_text or "")
        return QuestionnaireProcessResult(
            answers=answers,
            score=completed_score,
            next_question=next_question,
            triggered_dimensions=sorted({answer.dimension for answer in answers}),
            session=session,
            status=session.status,
            scale_id=session.scale_id or "",
            scale_name=session.scale_name or "",
            completed=bool(completed_score),
            message="量表已完成，结果已写入画像。" if completed_score else "量表评估进行中。",
        )

    def score_user(self, *, user: User, conversation: Conversation | None = None) -> QuestionnaireScoreResult | None:
        query = QuestionnaireScore.query.filter(
            QuestionnaireScore.user_id == user.id,
            QuestionnaireScore.scale_id != "",
        )
        if conversation is not None:
            query = query.filter_by(conversation_id=conversation.id)
        score = query.order_by(QuestionnaireScore.created_at.desc(), QuestionnaireScore.id.desc()).first()
        if score is None:
            return None
        basis = score.basis_json if isinstance(score.basis_json, dict) else {}
        return QuestionnaireScoreResult(
            total_score=score.total_score,
            stress_index=score.stress_index,
            risk_level=score.risk_level,
            dimension_scores=score.dimension_scores_json or {},
            basis=basis,
            answer_count=int(basis.get("answer_count") or 0),
        )

    def build_guidance(self, result: QuestionnaireProcessResult | None) -> str:
        if not result:
            return ""
        if result.completed:
            return (
                f"用户刚完成 {result.scale_name} 对话式评估。请先温和回应用户当前感受，"
                "再用一句话说明这次评估已经整理完成，避免医学诊断式表达。"
            )
        if result.status != self.ACTIVE_STATUS or not result.next_question:
            return ""
        return (
            f"当前正在进行 {result.scale_name} 单量表对话式评估。"
            "请先自然回应用户刚才的话，再用一句温和、不生硬的问题继续询问当前量表题项："
            f"{result.next_question}"
            "不要提到题号，不要混入其他量表，不要提前给风险结论。"
        )

    def serialize_session(self, session: QuestionnaireSession | None) -> dict | None:
        if session is None:
            return None
        return {
            "id": session.id,
            "scaleId": session.scale_id,
            "scaleName": session.scale_name,
            "status": session.status,
            "requiredItemCount": session.required_item_count,
            "answeredItemCount": session.answered_item_count,
            "nextQuestion": session.last_question_text or "",
            "totalScore": session.total_score,
            "riskLevel": session.risk_level,
            "completedAt": session.completed_at.isoformat() if session.completed_at else None,
        }

    def _scale_by_id(self, scale_id: str | None) -> dict | None:
        normalized = str(scale_id or "").strip().upper()
        for scale in self.load_scales():
            if str(scale.get("id") or "").upper() == normalized:
                return scale
        return None

    def _item_by_code(self, scale: dict, code: str | None) -> dict | None:
        for item in scale.get("items") or []:
            if item.get("code") == code:
                return item
        return None

    def _first_unanswered_item(
        self,
        *,
        user: User,
        conversation: Conversation,
        scale: dict,
        session: QuestionnaireSession | None,
    ) -> dict | None:
        query = QuestionnaireAnswer.query.filter_by(
            user_id=user.id,
            conversation_id=conversation.id,
            scale_id=scale.get("id") or "",
        )
        if session is not None:
            query = query.filter_by(session_id=session.id)
        answered = {answer.item_code for answer in query.all()}
        for item in scale.get("items") or []:
            if item.get("code") not in answered:
                return item
        return None

    def _answered_count(self, *, user: User, conversation: Conversation, session: QuestionnaireSession) -> int:
        return (
            db.session.query(QuestionnaireAnswer.item_code)
            .filter_by(user_id=user.id, conversation_id=conversation.id, session_id=session.id)
            .distinct()
            .count()
        )

    def _persist_answers(
        self,
        user: User,
        conversation: Conversation,
        message: Message,
        session: QuestionnaireSession,
        drafts: list[QuestionnaireAnswerDraft],
    ) -> list[QuestionnaireAnswer]:
        answers: list[QuestionnaireAnswer] = []
        for draft in drafts:
            existing = QuestionnaireAnswer.query.filter_by(
                session_id=session.id,
                item_code=draft.item_code,
            ).first()
            if existing is not None:
                existing.message_id = message.id
                existing.score = draft.score
                existing.evidence_text = draft.evidence
                existing.confidence = draft.confidence
                existing.created_at = utcnow()
                answers.append(existing)
                continue

            answer = QuestionnaireAnswer(
                session_id=session.id,
                user_id=user.id,
                conversation_id=conversation.id,
                message_id=message.id,
                scale_id=session.scale_id or "",
                item_code=draft.item_code,
                dimension=draft.dimension,
                score=draft.score,
                evidence_text=draft.evidence,
                confidence=draft.confidence,
                source=draft.source,
            )
            db.session.add(answer)
            db.session.flush()
            answers.append(answer)
        return answers

    def _complete_if_ready(
        self,
        *,
        user: User,
        conversation: Conversation,
        session: QuestionnaireSession,
        scale: dict,
    ) -> QuestionnaireScoreResult | None:
        answers = (
            QuestionnaireAnswer.query.filter_by(
                user_id=user.id,
                conversation_id=conversation.id,
                session_id=session.id,
                scale_id=scale.get("id") or "",
            )
            .order_by(QuestionnaireAnswer.created_at.asc(), QuestionnaireAnswer.id.asc())
            .all()
        )
        latest_by_item = {answer.item_code: answer for answer in answers}
        required_codes = [item.get("code") for item in scale.get("items") or [] if item.get("code")]
        session.required_item_count = len(required_codes)
        session.answered_item_count = len([code for code in required_codes if code in latest_by_item])

        if session.answered_item_count < session.required_item_count:
            return None

        dimension_scores: dict[str, int] = {}
        total_score = 0
        redline = False
        for item in scale.get("items") or []:
            answer = latest_by_item.get(item.get("code"))
            if answer is None:
                continue
            score = int(answer.score or 0)
            total_score += score
            dimension_scores[answer.dimension] = dimension_scores.get(answer.dimension, 0) + score
            if item.get("redline") and score >= 2:
                redline = True

        risk_level = self._risk_level(scale, total_score, redline=redline)
        stress_index = self._stress_index(scale, total_score, redline=redline)
        basis = {
            "method": "single_scale_dialogue_assessment",
            "scale_id": scale.get("id"),
            "scale_name": scale.get("name"),
            "complete": True,
            "answer_count": session.answered_item_count,
            "required_item_count": session.required_item_count,
            "evidence_message_ids": sorted({answer.message_id for answer in latest_by_item.values()}),
            "redline": redline,
            "severity": scale.get("severity") or [],
            "policy": "只有完整量表结果进入正式评分，本次量表已完成。",
        }
        result = QuestionnaireScoreResult(
            total_score=total_score,
            stress_index=stress_index,
            risk_level=risk_level,
            dimension_scores=dimension_scores,
            basis=basis,
            answer_count=session.answered_item_count,
        )

        existing_score = QuestionnaireScore.query.filter_by(session_id=session.id).first()
        if existing_score is None:
            db.session.add(
                QuestionnaireScore(
                    session_id=session.id,
                    user_id=user.id,
                    conversation_id=conversation.id,
                    scale_id=scale.get("id") or "",
                    scale_name=scale.get("name") or "",
                    total_score=total_score,
                    stress_index=stress_index,
                    risk_level=risk_level,
                    dimension_scores_json=dimension_scores,
                    basis_json=basis,
                )
            )
        else:
            existing_score.total_score = total_score
            existing_score.stress_index = stress_index
            existing_score.risk_level = risk_level
            existing_score.dimension_scores_json = dimension_scores
            existing_score.basis_json = basis

        summary = self._build_scale_summary(scale, result, latest_by_item)
        session.status = self.COMPLETED_STATUS
        session.total_score = total_score
        session.risk_level = risk_level
        session.summary_json = summary
        session.pending_item_code = None
        session.last_question_text = None
        session.completed_at = utcnow()
        session.updated_at = utcnow()

        ProfileMemoryService().update_from_scale_summary(
            user=user,
            conversation=conversation,
            session=session,
            summary=summary,
            answers=list(latest_by_item.values()),
        )
        return result

    def _build_scale_summary(
        self,
        scale: dict,
        score: QuestionnaireScoreResult,
        latest_by_item: dict[str, QuestionnaireAnswer],
    ) -> dict:
        high_items = []
        for item in scale.get("items") or []:
            answer = latest_by_item.get(item.get("code"))
            if answer is None:
                continue
            max_score = int(item.get("max_score") or 3)
            if int(answer.score or 0) >= max(2, max_score - 1):
                high_items.append(
                    {
                        "construct": item.get("construct") or item.get("code"),
                        "score": answer.score,
                        "evidence": answer.evidence_text or "",
                    }
                )
        main_issues = [item["construct"] for item in high_items[:4]]
        return {
            "scale_id": scale.get("id"),
            "scale_name": scale.get("name"),
            "total_score": score.total_score,
            "stress_index": score.stress_index,
            "risk_level": score.risk_level,
            "dimension_scores": score.dimension_scores,
            "main_issues": main_issues,
            "summary": self._summary_text(scale, score, main_issues),
            "profile_updates": self._profile_update_hints(scale, score, high_items),
        }

    def _summary_text(self, scale: dict, score: QuestionnaireScoreResult, main_issues: list[str]) -> str:
        issue_text = "、".join(main_issues) if main_issues else "未见明显高分题项"
        risk_text = {"low": "整体风险较低", "medium": "需要持续关注", "high": "需要重点关注"}.get(
            score.risk_level,
            "需要继续观察",
        )
        return f"{scale.get('name')} 已完整完成，总分 {self._format_total_score(scale, score)}，{risk_text}；主要线索为：{issue_text}。"

    def _profile_update_hints(self, scale: dict, score: QuestionnaireScoreResult, high_items: list[dict]) -> dict:
        evidence_text = "；".join(item["evidence"] for item in high_items if item.get("evidence"))[:240]
        constructs = [item["construct"] for item in high_items]
        total_score_text = self._format_total_score(scale, score)
        updates: dict[str, Any] = {
            "scale_assessment_history": (
                f"{scale.get('name')}：总分 {total_score_text}，风险等级 {score.risk_level}，"
                f"压力指数 {score.stress_index}/100。"
            )
        }
        construct_text = "、".join(constructs) if constructs else "当前未见突出高分线索"
        if scale.get("id") == "PHQ9":
            updates["emotion_pattern"] = f"完整 PHQ-9 评估提示：{construct_text}。{evidence_text}"
        elif scale.get("id") == "GAD7":
            updates["anxiety_pattern"] = f"完整 GAD-7 评估提示：{construct_text}。{evidence_text}"
        elif scale.get("id") == "ISI":
            updates["sleep_and_body"] = f"完整 ISI 评估提示：{construct_text}。{evidence_text}"
        if score.risk_level in {"medium", "high"}:
            updates["risk_signals"] = f"{scale.get('name')} 完整评估为 {score.risk_level}，总分 {total_score_text}"
        return updates

    def _format_total_score(self, scale: dict, score: QuestionnaireScoreResult) -> str:
        max_score = self._max_total_score(scale)
        if max_score > 0:
            return f"{score.total_score}/{max_score}"
        return str(score.total_score)

    def _max_total_score(self, scale: dict) -> int:
        score_range = str(scale.get("scoreRange") or scale.get("score_range") or "").strip()
        if "-" in score_range:
            tail = score_range.rsplit("-", 1)[-1].strip()
            if tail.isdigit():
                return int(tail)
        max_total = 0
        for item in scale.get("items") or []:
            try:
                max_total += int(item.get("max_score") or item.get("maxScore") or 0)
            except (TypeError, ValueError):
                continue
        return max_total

    def _risk_level(self, scale: dict, total_score: int, *, redline: bool) -> str:
        if redline:
            return "high"
        for item in scale.get("severity") or []:
            if int(item.get("min", 0)) <= total_score <= int(item.get("max", 0)):
                return item.get("level") or "low"
        return "low"

    def _stress_index(self, scale: dict, total_score: int, *, redline: bool) -> int:
        if redline:
            return 95
        max_score = sum(int(item.get("max_score") or 3) for item in scale.get("items") or [])
        if max_score <= 0:
            return 0
        return max(0, min(100, round(total_score / max_score * 100)))

    def _score_content(self, content: str, item: dict) -> tuple[int, float, str]:
        ai_score = self._score_content_by_ai(content, item)
        if ai_score is not None:
            return ai_score
        return self._score_content_by_rules(content, item)

    def _score_content_by_ai(self, content: str, item: dict) -> tuple[int, float, str] | None:
        if not bool(current_app.config.get("QUESTIONNAIRE_AI_SCORING_ENABLED", True)):
            return None
        glm_service = current_app.extensions.get("glm_service")
        if glm_service is None or not getattr(glm_service, "enabled", False):
            return None

        max_score = int(item.get("max_score") or 3)
        redline_text = "这是安全风险题，若回答出现明确自伤/自杀意图或计划，应给高分。" if item.get("redline") else ""
        system_prompt = (
            "你是心理量表对话答案的题项评分助手。"
            "你只负责判断用户当前回答是否足以回答给定题项，并给出该题分数。"
            "不要诊断，不要安慰，不要扩展解释。"
            "必须只输出 JSON，不要 Markdown，不要代码块。"
        )
        user_payload = {
            "scale_item": {
                "dimension": item.get("dimension"),
                "construct": item.get("construct"),
                "question": item.get("prompt"),
                "max_score": max_score,
                "score_options": self._score_options_text(max_score),
                "keywords": item.get("keywords") or [],
                "redline_note": redline_text,
            },
            "user_answer": content,
            "scoring_rules": [
                "score 必须是 0 到 max_score 的整数。",
                "confidence 必须是 0 到 1 的小数。",
                "如果用户回答没有覆盖该题项，confidence 应低于 0.45。",
                "如果回答能明确对应频率、程度或否定，应提高 confidence。",
                "不要因为语气强烈就越过题项本身含义打分。",
            ],
            "output_schema": {
                "score": "integer",
                "confidence": "number",
                "reason": "short string",
            },
        }
        try:
            raw_response = glm_service.generate_text(
                messages=[{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=180,
            )
            payload = self._parse_json_object(raw_response)
            score = int(payload.get("score"))
            confidence = float(payload.get("confidence"))
            score = max(0, min(max_score, score))
            confidence = max(0.0, min(1.0, confidence))
            return score, confidence, "scale_session_ai"
        except Exception as error:  # pragma: no cover - external model dependent
            current_app.logger.warning("Questionnaire AI scoring failed, fallback to rules: %s", error)
            return None

    def _score_content_by_rules(self, content: str, item: dict) -> tuple[int, float, str]:
        max_score = int(item.get("max_score") or 3)
        text = content.strip()
        if item.get("redline"):
            if self._contains(text, ["自杀", "自伤", "轻生", "结束自己", "跳楼", "割腕", "吃药", "准备好了"]):
                return max_score, 0.96, "scale_session_rules"
            if self._contains(text, ["不想活", "活不下去", "消失", "死了算了", "没必要活"]):
                return min(max_score, 2), 0.86, "scale_session_rules"
            if self._contains(text, ["没有", "不会", "没想过", "不想伤害自己", "没有伤害自己的想法"]):
                return 0, 0.82, "scale_session_rules"
            return 0, 0.55, "scale_session_rules"

        if self._contains(text, ["没有", "不会", "不怎么", "很少", "基本没有", "还好", "不明显"]):
            return 0, 0.74, "scale_session_rules"
        if self._contains(text, ["每天", "几乎每天", "一直", "大部分时间", "总是", "很久", "非常", "严重", "完全"]):
            return max_score, 0.9, "scale_session_rules"
        if self._contains(text, ["四五天", "五六天", "经常", "好几天", "明显", "很多时候", "大概一半"]):
            return min(max_score, max(2, round(max_score * 0.67))), 0.82, "scale_session_rules"
        if self._contains(text, ["两三天", "三天", "有几次", "有点", "偶尔", "一两天", "一会儿"]):
            return min(max_score, 1), 0.72, "scale_session_rules"
        if any(keyword in text for keyword in (item.get("keywords") or [])):
            return min(max_score, 2), 0.68, "scale_session_rules"
        return min(max_score, 1), 0.5, "scale_session_rules"

    def _score_options_text(self, max_score: int) -> list[dict]:
        labels = (
            ["无", "轻度", "中度", "重度", "非常严重"]
            if max_score >= 4
            else ["没有", "偶尔/几天", "经常/一半以上时间", "几乎每天/非常明显"]
        )
        return [
            {"score": score, "label": labels[min(score, len(labels) - 1)]}
            for score in range(max_score + 1)
        ]

    def _parse_json_object(self, text: str) -> dict:
        raw = (text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end >= start:
            raw = raw[start : end + 1]
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("AI scoring response is not an object")
        return payload

    def _follow_up_prompt(self, item: dict) -> str:
        return (
            f"刚才这个问题我还想确认得更清楚一点：{item.get('prompt') or ''}"
            "你可以用“没有、偶尔、经常、几乎每天”这样的方式简单说说。"
        )

    def _contains(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)
