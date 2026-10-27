from __future__ import annotations

import json
from dataclasses import dataclass

from flask import current_app

from ...models import Conversation, User
from ..questionnaire_service import QuestionnaireScoreResult, QuestionnaireService
from .context_builder import UserInsightContextBuilder
from .glm import GLMServiceError
from .prompts import get_user_assessment_prompt
from .shared import clean_text, normalize_risk_level, parse_json_response


class UserAssessmentServiceError(RuntimeError):
    """Raised when user-side assessment cannot be generated."""


@dataclass
class UserAssessmentResult:
    mood_summary: str
    stress_index: int
    risk_level: str
    trend: str
    advice: str
    core_psychological_issue: str
    context: dict
    raw_response: str


class UserAssessmentService:
    def __init__(self) -> None:
        self._context_builder = UserInsightContextBuilder()

    def build_context(
        self,
        user: User,
        *,
        conversation: Conversation | None = None,
        dialogue_limit: int = 16,
        multimodal_limit: int = 3,
    ) -> dict:
        return self._context_builder.build_context(
            user,
            conversation=conversation,
            dialogue_limit=dialogue_limit,
            multimodal_limit=multimodal_limit,
            rag_scope="user_assessment",
        )

    def generate_for_user(
        self,
        user: User,
        *,
        conversation: Conversation | None = None,
        dialogue_limit: int = 16,
        multimodal_limit: int = 3,
    ) -> UserAssessmentResult:
        context = self.build_context(
            user,
            conversation=conversation,
            dialogue_limit=dialogue_limit,
            multimodal_limit=multimodal_limit,
        )
        if not context["recent_dialogue"] and not context["multimodal_features"]:
            raise UserAssessmentServiceError("缺少近期对话或多模态数据，暂时无法生成状态评估")

        questionnaire_score = QuestionnaireService().score_user(user=user, conversation=conversation)
        glm_service = current_app.extensions.get("glm_service")
        if glm_service is None or not getattr(glm_service, "enabled", False):
            if questionnaire_score is None:
                raise UserAssessmentServiceError("当前未接入 GLM 服务，且缺少问卷采集结果，无法生成状态评估")
            return self._build_local_result(context, questionnaire_score)

        payload_text = json.dumps(context, ensure_ascii=False, indent=2)

        try:
            raw_response = glm_service.generate_text(
                messages=[{"role": "user", "content": payload_text}],
                system_prompt=get_user_assessment_prompt(current_app),
                temperature=0.35,
                max_tokens=1000,
            )
        except GLMServiceError as error:
            raise UserAssessmentServiceError(str(error)) from error

        parsed = parse_json_response(raw_response, error_cls=UserAssessmentServiceError)
        mood_summary = clean_text(parsed.get("mood_summary"))
        risk_level = normalize_risk_level(parsed.get("risk_level"))
        trend = clean_text(parsed.get("trend"))
        advice = clean_text(parsed.get("advice"))
        core_issue = clean_text(parsed.get("core_psychological_issue"))
        stress_index = self._normalize_stress_index(parsed.get("stress_index"))

        if questionnaire_score is not None:
            risk_level = questionnaire_score.risk_level
            stress_index = questionnaire_score.stress_index
            context["questionnaire_score"] = {
                "total_score": questionnaire_score.total_score,
                "stress_index": questionnaire_score.stress_index,
                "risk_level": questionnaire_score.risk_level,
                "dimension_scores": questionnaire_score.dimension_scores,
                "basis": questionnaire_score.basis,
                "answer_count": questionnaire_score.answer_count,
            }

        if not mood_summary:
            raise UserAssessmentServiceError("模型未返回有效的状态总结")
        if stress_index is None:
            raise UserAssessmentServiceError("模型未返回有效的压力指数")
        if not risk_level:
            raise UserAssessmentServiceError("模型未返回有效的风险等级")
        if not trend:
            raise UserAssessmentServiceError("模型未返回有效的趋势总结")
        if not advice:
            raise UserAssessmentServiceError("模型未返回有效的建议")

        return UserAssessmentResult(
            mood_summary=mood_summary,
            stress_index=stress_index,
            risk_level=risk_level,
            trend=trend,
            advice=advice,
            core_psychological_issue=core_issue,
            context=context,
            raw_response=raw_response,
        )

    def infer_tag_names(self, result: UserAssessmentResult) -> list[str]:
        combined_text = " ".join(
            [
                result.mood_summary,
                result.trend,
                result.advice,
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

    def _normalize_stress_index(self, value) -> int | None:
        if value is None or value == "":
            return None
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError):
            return None
        return max(0, min(number, 100))

    def _build_local_result(self, context: dict, questionnaire_score: QuestionnaireScoreResult) -> UserAssessmentResult:
        dimension_scores = questionnaire_score.dimension_scores
        dominant_dimension = max(dimension_scores, key=dimension_scores.get) if dimension_scores else ""
        dimension_labels = {
            "sleep": "睡眠受影响",
            "anxiety": "焦虑或担心较明显",
            "mood": "低落情绪较明显",
            "function": "学习或日常功能受影响",
            "support": "支持系统不足",
            "safety": "安全风险需要优先关注",
        }
        dominant_text = dimension_labels.get(dominant_dimension, "近期压力信号")
        risk_text = {
            "low": "整体风险较低",
            "medium": "当前处于中等风险，需要继续观察",
            "high": "当前风险较高，需要尽快获得人工支持",
        }.get(questionnaire_score.risk_level, "当前状态需要继续观察")

        context["questionnaire_score"] = {
            "total_score": questionnaire_score.total_score,
            "stress_index": questionnaire_score.stress_index,
            "risk_level": questionnaire_score.risk_level,
            "dimension_scores": questionnaire_score.dimension_scores,
            "basis": questionnaire_score.basis,
            "answer_count": questionnaire_score.answer_count,
        }

        advice = "先把今天要做的事缩小到一个很小的动作，并尽量和一个可信赖的人说一声当前状态。"
        if questionnaire_score.risk_level == "high":
            advice = "请优先保证安全，尽快联系可信赖的人或线下专业支持；如果有伤害自己的冲动，请立即寻求紧急帮助。"
        elif dominant_dimension == "sleep":
            advice = "今晚先把目标降到休息身体：睡前减少继续复盘成绩，给自己留 10 分钟做放松或简单记录。"
        elif dominant_dimension == "function":
            advice = "先只选一道最基础的题或一个最小任务，目标不是补完，而是重新找回一点掌控感。"

        return UserAssessmentResult(
            mood_summary=f"根据近期对话式问卷采集，{dominant_text}，{risk_text}。",
            stress_index=questionnaire_score.stress_index,
            risk_level=questionnaire_score.risk_level,
            trend="问卷采集显示近期状态存在压力累积，建议结合后续对话继续观察变化。",
            advice=advice,
            core_psychological_issue=f"{dominant_text}正在影响用户的恢复感和掌控感。",
            context=context,
            raw_response=json.dumps(
                {
                    "source": "local_questionnaire_scoring",
                    "questionnaire_score": context["questionnaire_score"],
                },
                ensure_ascii=False,
            ),
        )
