from __future__ import annotations

import json
from dataclasses import dataclass

from flask import current_app

from ...models import Conversation, User
from ..questionnaire_service import QuestionnaireScoreResult, QuestionnaireService
from .context_builder import UserInsightContextBuilder
from .glm import GLMServiceError
from .prompts import get_admin_risk_assessment_prompt
from .shared import clean_text, normalize_risk_level, parse_json_response


class RiskAssessmentServiceError(RuntimeError):
    """Raised when admin risk assessment cannot be generated."""


@dataclass
class RiskAssessmentResult:
    risk_level: str
    risk_reason: str
    core_psychological_issue: str
    context: dict
    raw_response: str


class RiskAssessmentService:
    def __init__(self) -> None:
        self._context_builder = UserInsightContextBuilder()

    def build_context(
        self,
        user: User,
        *,
        conversation: Conversation | None = None,
        dialogue_limit: int = 12,
        multimodal_limit: int = 3,
    ) -> dict:
        return self._context_builder.build_context(
            user,
            conversation=conversation,
            dialogue_limit=dialogue_limit,
            multimodal_limit=multimodal_limit,
            rag_scope="admin_risk_assessment",
        )

    def generate_for_user(
        self,
        user: User,
        *,
        conversation: Conversation | None = None,
        dialogue_limit: int = 12,
        multimodal_limit: int = 3,
    ) -> RiskAssessmentResult:
        context = self.build_context(
            user,
            conversation=conversation,
            dialogue_limit=dialogue_limit,
            multimodal_limit=multimodal_limit,
        )
        if not context["recent_dialogue"] and not context["multimodal_features"]:
            raise RiskAssessmentServiceError("缺少近期对话或多模态数据，暂时无法重新评估该用户")

        questionnaire_score = QuestionnaireService().score_user(user=user, conversation=conversation)
        glm_service = current_app.extensions.get("glm_service")
        if glm_service is None or not getattr(glm_service, "enabled", False):
            if questionnaire_score is None:
                raise RiskAssessmentServiceError("当前未接入 GLM 服务，且缺少问卷采集结果，无法重新评估风险")
            return self._build_questionnaire_result(context, questionnaire_score)

        payload_text = json.dumps(context, ensure_ascii=False, indent=2)

        try:
            raw_response = glm_service.generate_text(
                messages=[{"role": "user", "content": payload_text}],
                system_prompt=get_admin_risk_assessment_prompt(current_app),
                temperature=0.2,
                max_tokens=900,
            )
        except GLMServiceError as error:
            raise RiskAssessmentServiceError(str(error)) from error

        parsed = parse_json_response(raw_response, error_cls=RiskAssessmentServiceError)
        risk_level = normalize_risk_level(parsed.get("risk_level"))
        risk_reason = clean_text(parsed.get("risk_reason"))
        core_issue = clean_text(parsed.get("core_psychological_issue"))

        if not risk_level:
            raise RiskAssessmentServiceError("模型未返回有效的风险等级")
        if not risk_reason:
            raise RiskAssessmentServiceError("模型未返回有效的风险依据")
        if not core_issue:
            raise RiskAssessmentServiceError("模型未返回核心心理症结")

        if questionnaire_score is not None:
            risk_level = questionnaire_score.risk_level
            context["questionnaire_score"] = {
                "total_score": questionnaire_score.total_score,
                "stress_index": questionnaire_score.stress_index,
                "risk_level": questionnaire_score.risk_level,
                "dimension_scores": questionnaire_score.dimension_scores,
                "basis": questionnaire_score.basis,
                "answer_count": questionnaire_score.answer_count,
            }
            risk_reason = (
                f"风险等级以对话式问卷计分为准：总分 {questionnaire_score.total_score}，"
                f"维度分 {questionnaire_score.dimension_scores}；AI 复核补充依据：{risk_reason}"
            )

        return RiskAssessmentResult(
            risk_level=risk_level,
            risk_reason=risk_reason,
            core_psychological_issue=core_issue,
            context=context,
            raw_response=raw_response,
        )

    def _build_questionnaire_result(
        self,
        context: dict,
        questionnaire_score: QuestionnaireScoreResult,
    ) -> RiskAssessmentResult:
        context["questionnaire_score"] = {
            "total_score": questionnaire_score.total_score,
            "stress_index": questionnaire_score.stress_index,
            "risk_level": questionnaire_score.risk_level,
            "dimension_scores": questionnaire_score.dimension_scores,
            "basis": questionnaire_score.basis,
            "answer_count": questionnaire_score.answer_count,
        }
        dominant_dimension = max(questionnaire_score.dimension_scores, key=questionnaire_score.dimension_scores.get)
        labels = {
            "sleep": "睡眠受损",
            "anxiety": "焦虑担忧",
            "mood": "低落情绪",
            "function": "学习或日常功能受影响",
            "support": "支持系统不足",
            "safety": "安全风险",
        }
        dominant_text = labels.get(dominant_dimension, "压力信号")
        return RiskAssessmentResult(
            risk_level=questionnaire_score.risk_level,
            risk_reason=(
                f"风险等级来自对话式问卷计分：总分 {questionnaire_score.total_score}，"
                f"主要维度为{dominant_text}，维度分 {questionnaire_score.dimension_scores}。"
            ),
            core_psychological_issue=f"{dominant_text}正在放大用户近期压力，需要继续跟踪。",
            context=context,
            raw_response=json.dumps(
                {
                    "source": "local_questionnaire_scoring",
                    "questionnaire_score": context["questionnaire_score"],
                },
                ensure_ascii=False,
            ),
        )

    def infer_tag_names(self, result: RiskAssessmentResult) -> list[str]:
        combined_text = " ".join(
            [
                result.risk_reason,
                result.core_psychological_issue,
                json.dumps(result.context.get("recent_dialogue") or [], ensure_ascii=False),
                json.dumps(result.context.get("multimodal_features") or [], ensure_ascii=False),
            ]
        )
        tag_keywords = {
            "抑郁": ["低落", "无力", "没意义", "抑郁", "提不起劲", "耗竭", "绝望"],
            "焦虑": ["焦虑", "担心", "紧张", "不安", "害怕", "迷茫"],
            "孤独": ["孤独", "孤单", "没人", "独自", "社交退缩", "隔离"],
            "高压力": ["压力", "累", "崩", "学业", "工作", "求职", "负担"],
            "睡眠问题": ["失眠", "睡不着", "睡眠", "凌晨", "休息不好", "睡不好"],
        }

        names = [name for name, keywords in tag_keywords.items() if any(keyword in combined_text for keyword in keywords)]
        if not names and result.risk_level == "low":
            names.append("正常")
        return names

    def build_admin_response(self, result: RiskAssessmentResult) -> dict:
        return {
            "riskCode": result.risk_level,
            "riskReason": result.risk_reason,
            "corePsychologicalIssue": result.core_psychological_issue,
            "context": result.context,
        }
