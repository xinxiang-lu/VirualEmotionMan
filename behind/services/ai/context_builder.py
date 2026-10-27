from __future__ import annotations

from ...models import Assessment, Conversation, Message, MultimodalAnalysis, QuestionnaireScore, User
from .rag import resolve_rag_context


class UserInsightContextBuilder:
    def build_context(
        self,
        user: User,
        *,
        conversation: Conversation | None = None,
        dialogue_limit: int = 12,
        multimodal_limit: int = 3,
        rag_scope: str | None = None,
    ) -> dict:
        target_conversation = conversation or self._latest_conversation(user)
        context = {
            "user_profile": self._user_profile(user),
            "profile_memory": self._profile_memory(user),
            "recent_dialogue": self._recent_dialogue(target_conversation, limit=dialogue_limit),
            "multimodal_features": self._multimodal_features(
                user,
                conversation=target_conversation,
                limit=multimodal_limit,
            ),
            "previous_assessment": self._previous_assessment(user),
            "questionnaire_score": self._questionnaire_score(user, conversation=target_conversation),
            "conversation_id": target_conversation.id if target_conversation else None,
        }

        if rag_scope:
            rag_context = resolve_rag_context(
                rag_scope,
                user=user,
                conversation=target_conversation,
                context=context,
            )
            if rag_context:
                context["rag_context"] = rag_context

        return context

    def _latest_conversation(self, user: User) -> Conversation | None:
        return (
            Conversation.query.filter_by(user_id=user.id)
            .order_by(Conversation.latest_message_at.desc(), Conversation.id.desc())
            .first()
        )

    def _recent_dialogue(self, conversation: Conversation | None, *, limit: int) -> list[dict]:
        if conversation is None:
            return []

        messages = (
            Message.query.filter_by(conversation_id=conversation.id)
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

            result.append(
                {
                    "message_id": item.id,
                    "role": role,
                    "content": content,
                    "content_type": item.content_type,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
            )
        return result

    def _multimodal_features(
        self,
        user: User,
        *,
        conversation: Conversation | None,
        limit: int,
    ) -> list[dict]:
        query = MultimodalAnalysis.query.filter_by(user_id=user.id)
        if conversation is not None:
            scoped_records = (
                query.filter_by(conversation_id=conversation.id)
                .order_by(MultimodalAnalysis.updated_at.desc(), MultimodalAnalysis.id.desc())
                .limit(limit)
                .all()
            )
        else:
            scoped_records = []

        if not scoped_records:
            scoped_records = (
                query.order_by(MultimodalAnalysis.updated_at.desc(), MultimodalAnalysis.id.desc())
                .limit(limit)
                .all()
            )

        result = []
        for record in scoped_records:
            payload = record.get_summary_payload() or {}
            result.append(
                {
                    "message_id": record.message_id,
                    "analysis_mode": record.analysis_mode,
                    "transcript_text": payload.get("transcript_text") or record.transcript_text or "",
                    "transcript_confidence": payload.get("transcript_confidence") or record.transcript_confidence,
                    "overall_summary": payload.get("overall_summary") or {},
                    "event_tags": payload.get("event_tags") or [],
                    "key_segments": payload.get("key_segments") or [],
                    "prediction_meta": payload.get("prediction_meta") or {},
                }
            )
        return result

    def _previous_assessment(self, user: User) -> dict | None:
        assessment = (
            Assessment.query.filter_by(user_id=user.id)
            .order_by(Assessment.evaluated_at.desc(), Assessment.id.desc())
            .first()
        )
        if assessment is None:
            return None

        raw_result = assessment.raw_result_json if isinstance(assessment.raw_result_json, dict) else {}
        return {
            "assessment_id": assessment.id,
            "source": assessment.source,
            "risk_level": assessment.risk_level,
            "mood_summary": assessment.mood_summary or "",
            "advice": assessment.advice or "",
            "core_psychological_issue": raw_result.get("core_psychological_issue", ""),
            "risk_reason": raw_result.get("risk_reason", ""),
            "evaluated_at": assessment.evaluated_at.isoformat() if assessment.evaluated_at else None,
        }

    def _user_profile(self, user: User) -> dict:
        profile = user.profile
        return {
            "nickname": profile.nickname if profile and profile.nickname else user.phone,
            "gender": profile.gender if profile and profile.gender else "",
            "age": profile.age if profile else None,
            "occupation": profile.occupation if profile and profile.occupation else "",
            "use_purpose": [relation.tag.description or relation.tag.name for relation in user.profile_goals],
        }

    def _profile_memory(self, user: User) -> dict:
        memory = getattr(user, "profile_memory", None)
        profile = user.profile
        base_profile = {
            "nickname": profile.nickname if profile and profile.nickname else user.phone,
            "gender": profile.gender if profile and profile.gender else "",
            "age": profile.age if profile else None,
            "occupation": profile.occupation if profile and profile.occupation else "",
            "use_purpose": [relation.tag.description or relation.tag.name for relation in user.profile_goals],
        }
        if memory is None or not isinstance(memory.memory_json, dict):
            return {"base_profile": base_profile, "memory": {}}
        return {
            "template_version": memory.template_version,
            "base_profile": base_profile,
            "memory": memory.memory_json,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
        }

    def _questionnaire_score(self, user: User, *, conversation: Conversation | None) -> dict | None:
        query = QuestionnaireScore.query.filter(
            QuestionnaireScore.user_id == user.id,
            QuestionnaireScore.scale_id != "",
        )
        if conversation is not None:
            query = query.filter_by(conversation_id=conversation.id)
        score = query.order_by(QuestionnaireScore.created_at.desc(), QuestionnaireScore.id.desc()).first()
        if score is None:
            return None
        return {
            "score_id": score.id,
            "source": score.source,
            "total_score": score.total_score,
            "stress_index": score.stress_index,
            "risk_level": score.risk_level,
            "dimension_scores": score.dimension_scores_json or {},
            "basis": score.basis_json or {},
            "created_at": score.created_at.isoformat() if score.created_at else None,
        }
