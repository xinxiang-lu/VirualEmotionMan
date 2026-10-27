from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect, text

from ..config import DATA_DIR
from ..extensions import db
from ..models import (
    Assessment,
    AssessmentTag,
    Conversation,
    InterventionSession,
    Message,
    MultimodalAnalysis,
    QuestionnaireAnswer,
    QuestionnaireScore,
    QuestionnaireSession,
    TagLibrary,
    User,
    UserProfile,
    UserProfileGoal,
    UserProfileMemory,
    UserProfileMemoryEvent,
    UserSetting,
)
from ..services.system_settings import save_system_settings
from ..utils.auth import store_password
from ..utils.voice_preferences import VOICE_SPEED_DEFAULT


CHAT_MEDIA_ROOT = Path(DATA_DIR) / "chat_media"
MULTIMODAL_ANALYSIS_ROOT = Path(DATA_DIR) / "multimodal_analysis"


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).replace(tzinfo=None)


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def clear_demo_data() -> None:
    existing_tables = set(inspect(db.engine).get_table_names())

    for table_name in ("resource_tags", "resources"):
        if table_name in existing_tables:
            db.session.execute(text(f"DELETE FROM {table_name}"))

    for model in [
        QuestionnaireScore,
        QuestionnaireAnswer,
        QuestionnaireSession,
        UserProfileMemoryEvent,
        UserProfileMemory,
        MultimodalAnalysis,
        Message,
        InterventionSession,
        AssessmentTag,
        Assessment,
        Conversation,
        UserProfileGoal,
        UserSetting,
        UserProfile,
        User,
        TagLibrary,
    ]:
        db.session.query(model).delete()

    if "sqlite_sequence" in existing_tables:
        db.session.execute(text("DELETE FROM sqlite_sequence"))

    db.session.commit()
    _reset_directory(CHAT_MEDIA_ROOT)
    _reset_directory(MULTIMODAL_ANALYSIS_ROOT)


def seed_demo_data(force: bool = False) -> dict:
    if force:
        clear_demo_data()

    if User.query.first() is not None:
        return {"seeded": False, "message": "数据库中已有数据，已跳过演示数据初始化。"}

    tags: dict[tuple[str, str], TagLibrary] = {}

    def create_tag(name: str, tag_type: str, description: str = "", sort_order: int = 0) -> TagLibrary:
        tag = TagLibrary(
            name=name,
            tag_type=tag_type,
            description=description,
            sort_order=sort_order,
            is_active=True,
        )
        db.session.add(tag)
        db.session.flush()
        tags[(tag_type, name)] = tag
        return tag

    def create_user(
        *,
        phone: str,
        password: str,
        role: str,
        nickname: str,
        gender: str,
        age: int | None,
        occupation: str,
        last_login_at: datetime,
        custom_prompt: str = "",
        digital_human_code: str = "haru",
        voice_speed: float = VOICE_SPEED_DEFAULT,
        goals: list[str] | None = None,
    ) -> User:
        user = User(
            phone=phone,
            password=store_password(password),
            role=role,
            last_login_at=last_login_at,
        )
        db.session.add(user)
        db.session.flush()

        db.session.add(
            UserProfile(
                user_id=user.id,
                nickname=nickname,
                gender=gender,
                age=age,
                occupation=occupation,
                avatar_url="",
            )
        )
        db.session.add(
            UserSetting(
                user_id=user.id,
                custom_prompt=custom_prompt,
                digital_human_code=digital_human_code,
                voice_speed=voice_speed,
            )
        )

        for goal_name in goals or []:
            db.session.add(UserProfileGoal(user_id=user.id, tag_id=tags[("usage_goal", goal_name)].id))

        return user

    def create_conversation(
        *,
        user: User,
        title: str,
        summary: str,
        messages: list[tuple[str, str, datetime, User | None]],
        status: str = "active",
    ) -> Conversation:
        created_at = messages[0][2] - timedelta(minutes=2)
        latest_message_at = messages[-1][2]
        conversation = Conversation(
            user_id=user.id,
            title=title,
            summary=summary,
            status=status,
            created_at=created_at,
            updated_at=latest_message_at,
            latest_message_at=latest_message_at,
        )
        db.session.add(conversation)
        db.session.flush()

        for sender_type, content_text, created_time, sender_user in messages:
            db.session.add(
                Message(
                    conversation_id=conversation.id,
                    sender_type=sender_type,
                    sender_user_id=sender_user.id if sender_user is not None else None,
                    content_type="text",
                    content_text=content_text,
                    created_at=created_time,
                )
            )

        return conversation

    def create_assessment(
        *,
        user: User,
        conversation: Conversation | None,
        source: str,
        mood_summary: str,
        stress_index: int | None,
        risk_level: str | None,
        advice: str,
        trend: str,
        tag_names: list[str],
        evaluated_at: datetime,
        risk_reason: str = "",
        core_psychological_issue: str = "",
    ) -> Assessment:
        raw_result = {"trend": trend}
        if risk_reason:
            raw_result["risk_reason"] = risk_reason
        if core_psychological_issue:
            raw_result["core_psychological_issue"] = core_psychological_issue

        assessment = Assessment(
            user_id=user.id,
            conversation_id=conversation.id if conversation is not None else None,
            source=source,
            mood_summary=mood_summary,
            stress_index=stress_index,
            risk_level=risk_level,
            advice=advice,
            raw_result_json=raw_result,
            evaluated_at=evaluated_at,
            created_at=evaluated_at,
        )
        db.session.add(assessment)
        db.session.flush()

        for tag_name in tag_names:
            db.session.add(AssessmentTag(assessment_id=assessment.id, tag_id=tags[("risk", tag_name)].id))

        return assessment

    def latest_user_message(conversation: Conversation) -> Message:
        message = (
            Message.query.filter_by(conversation_id=conversation.id, sender_type="user")
            .order_by(Message.created_at.desc(), Message.id.desc())
            .first()
        )
        if message is None:
            raise RuntimeError("演示对话缺少用户消息，无法生成画像和问卷示例。")
        return message

    def create_profile_memory(*, user: User, memory_json: dict) -> None:
        db.session.add(
            UserProfileMemory(
                user_id=user.id,
                template_version="v1",
                memory_json=memory_json,
            )
        )

    def create_questionnaire_snapshot(
        *,
        user: User,
        conversation: Conversation,
        message: Message,
        answers: list[dict],
        total_score: int,
        stress_index: int,
        risk_level: str,
        dimension_scores: dict,
        redline: bool = False,
    ) -> None:
        for answer in answers:
            db.session.add(
                QuestionnaireAnswer(
                    user_id=user.id,
                    conversation_id=conversation.id,
                    message_id=message.id,
                    item_code=answer["item_code"],
                    dimension=answer["dimension"],
                    score=answer["score"],
                    evidence_text=answer.get("evidence") or message.content_text,
                    confidence=answer.get("confidence", 0.8),
                )
            )
        db.session.add(
            QuestionnaireScore(
                user_id=user.id,
                conversation_id=conversation.id,
                total_score=total_score,
                stress_index=stress_index,
                risk_level=risk_level,
                dimension_scores_json=dimension_scores,
                basis_json={
                    "method": "dialogue_questionnaire_scoring",
                    "answer_count": len(answers),
                    "evidence_message_ids": [message.id],
                    "redline": redline,
                    "stress_index": {
                        "method": "observed_item_burden_with_coverage_adjustment",
                        "note": "压力指数是系统换算指数，非 PHQ-9/GAD-7/ISI/PSS-10/C-SSRS 的官方原始分。",
                    },
                },
            )
        )

    create_tag("焦虑倾向", "risk", "持续担忧、紧张和反复思虑。", 1)
    create_tag("低落情绪", "risk", "挫败感、无力感和明显情绪低落。", 2)
    create_tag("睡眠问题", "risk", "入睡困难、夜间反复清醒或睡眠质量下降。", 3)
    create_tag("学业压力", "risk", "课程、考试和成绩带来的持续压力。", 4)
    create_tag("社交退缩", "risk", "回避交流、不愿表达和明显疏离感。", 5)
    create_tag("状态稳定", "risk", "整体状态平稳，波动较小。", 6)

    create_tag("情绪倾诉", "usage_goal", "希望有人承接情绪、陪自己说说话。", 1)
    create_tag("压力缓解", "usage_goal", "想缓解当前学习或生活压力。", 2)
    create_tag("学业支持", "usage_goal", "围绕课程、考试和学习压力获得支持。", 3)
    create_tag("日常陪伴", "usage_goal", "日常交流与轻量陪伴。", 4)
    create_tag("心理支持", "usage_goal", "希望获得更持续的情绪理解与支持。", 5)

    admin = create_user(
        phone="DEMO_ADMIN",
        password="DEMO_PASSWORD",
        role="admin",
        nickname="心陪陪管理员",
        gender="女",
        age=None,
        occupation="管理员",
        last_login_at=_dt("2026-04-15 09:20"),
        custom_prompt="",
        digital_human_code="haru",
        goals=[],
    )

    users = {
        "demo_user_001": create_user(
            phone="DEMO_USER_001",
            password="DEMO_PASSWORD",
            role="user",
            nickname="示例用户 A",
            gender="女",
            age=20,
            occupation="大二学生",
            last_login_at=_dt("2026-04-15 09:08"),
            custom_prompt="希望你先理解我的情绪，再慢慢陪我把问题拆开，不要一上来就讲大道理。",
            digital_human_code="haru",
            voice_speed=0.9,
            goals=["学业支持", "压力缓解", "心理支持"],
        ),
        "demo_user_002": create_user(
            phone="DEMO_USER_002",
            password="DEMO_PASSWORD",
            role="user",
            nickname="示例用户 B",
            gender="男",
            age=21,
            occupation="大三学生",
            last_login_at=_dt("2026-04-14 20:40"),
            custom_prompt="如果我表达得很乱，请先帮我整理重点，再给建议。",
            digital_human_code="hiyori",
            voice_speed=1.0,
            goals=["压力缓解", "情绪倾诉"],
        ),
        "demo_user_003": create_user(
            phone="DEMO_USER_003",
            password="DEMO_PASSWORD",
            role="user",
            nickname="示例用户 C",
            gender="女",
            age=22,
            occupation="考研学生",
            last_login_at=_dt("2026-04-15 08:26"),
            custom_prompt="我更喜欢温和简洁一点的表达方式。",
            digital_human_code="haru",
            voice_speed=1.0,
            goals=["日常陪伴", "压力缓解"],
        ),
        "demo_user_004": create_user(
            phone="DEMO_USER_004",
            password="DEMO_PASSWORD",
            role="user",
            nickname="示例用户 D",
            gender="男",
            age=19,
            occupation="大一学生",
            last_login_at=_dt("2026-04-15 19:10"),
            custom_prompt="先陪我聊聊，不用太快进入分析。",
            digital_human_code="hiyori",
            voice_speed=1.0,
            goals=["日常陪伴", "情绪倾诉"],
        ),
    }

    conversations = {
        "demo_001_history": create_conversation(
            user=users["demo_user_001"],
            title="开学后一直有点紧绷",
            summary="最近课程难度上来后，整个人一直处在紧绷状态。",
            messages=[
                ("user", "这学期开学之后，我总觉得自己一直在赶进度。", _dt("2026-04-10 21:03"), users["demo_user_001"]),
                ("assistant", "一直绷着走，会让人连休息的时候也放不下来。", _dt("2026-04-10 21:04"), None),
                ("user", "是的，明明没出什么大事，但我就是很难松下来。", _dt("2026-04-10 21:06"), users["demo_user_001"]),
                ("assistant", "这说明你的压力已经持续了一段时间，我们可以先从最常出现的压力源开始看。", _dt("2026-04-10 21:07"), None),
            ],
        ),
        "demo_001_exam": create_conversation(
            user=users["demo_user_001"],
            title="数学考试之后我有点撑不住了",
            summary="数学考试失利后，开始持续失眠、自责，学习效率明显下降。",
            messages=[
                ("user", "这次数学考试又没考好，我现在看到成绩就会发慌。", _dt("2026-04-11 21:10"), users["demo_user_001"]),
                ("assistant", "这次考试对你的打击很大，难受并不夸张。", _dt("2026-04-11 21:11"), None),
                ("user", "我原本以为自己至少能及格，结果差得有点多。", _dt("2026-04-11 21:13"), users["demo_user_001"]),
                ("assistant", "当期待和结果落差很大时，挫败感会一下子压上来。", _dt("2026-04-11 21:14"), None),
                ("user", "这两天一到晚上就一直想这件事，常常两三点才睡。", _dt("2026-04-13 22:05"), users["demo_user_001"]),
                ("assistant", "白天努力撑住，到了夜里反而更容易被焦虑追上。", _dt("2026-04-13 22:06"), None),
                ("user", "我现在最怕的是后面越来越学不进去。", _dt("2026-04-15 09:02"), users["demo_user_001"]),
                ("assistant", "我们先不急着逼自己立刻振作，可以先把眼前最难受的那一块拆出来。", _dt("2026-04-15 09:04"), None),
            ],
        ),
        "zhou_intern": create_conversation(
            user=users["demo_user_002"],
            title="实习和课程撞在一起了",
            summary="担心实习与课程安排冲突，近期焦虑明显。",
            messages=[
                ("user", "这周实习和课程都堆在一起，我每天都在担心顾不过来。", _dt("2026-04-12 20:12"), users["demo_user_002"]),
                ("assistant", "当任务同时压过来时，人会一直处在被追着跑的感觉里。", _dt("2026-04-12 20:13"), None),
                ("user", "而且我越忙越怕自己两边都做不好。", _dt("2026-04-14 20:35"), users["demo_user_002"]),
                ("assistant", "先把最容易失控的一件事找出来，通常会比同时扛住所有事情更有效。", _dt("2026-04-14 20:36"), None),
            ],
        ),
        "chen_stable": create_conversation(
            user=users["demo_user_003"],
            title="最近状态在慢慢回稳",
            summary="整体状态比较平稳，主要想做日常陪伴。",
            messages=[
                ("user", "这周虽然也忙，但我感觉自己比前段时间稳定一些。", _dt("2026-04-11 08:30"), users["demo_user_003"]),
                ("assistant", "能感觉到你在慢慢把节奏找回来，这很不容易。", _dt("2026-04-11 08:31"), None),
                ("user", "嗯，至少最近晚上不会一直胡思乱想了。", _dt("2026-04-15 08:20"), users["demo_user_003"]),
                ("assistant", "那我们就继续保持这份节律，把状态稳稳接住。", _dt("2026-04-15 08:21"), None),
            ],
        ),
        "shen_daily": create_conversation(
            user=users["demo_user_004"],
            title="想先找个人聊聊天",
            summary="刚开始使用系统，暂时没有形成完整评估。",
            messages=[
                ("user", "今天有点烦，但我其实也说不上来具体为什么。", _dt("2026-04-15 19:00"), users["demo_user_004"]),
                ("assistant", "没关系，先随便说一点也可以，我们慢慢来。", _dt("2026-04-15 19:01"), None),
            ],
        ),
    }
    db.session.flush()

    lin_latest_message = latest_user_message(conversations["demo_001_exam"])
    zhou_latest_message = latest_user_message(conversations["zhou_intern"])
    chen_latest_message = latest_user_message(conversations["chen_stable"])

    create_profile_memory(
        user=users["demo_user_001"],
        memory_json={
            "academic_status": "近期数学考试失利后，对成绩和后续学习产生明显担心，出现学不进去的感受。",
            "sleep_status": "考试后夜间反复想成绩，近几天常常到两三点才睡。",
            "emotion_pattern": "主要情绪为挫败、自责、焦虑和低落，夜间更容易被反刍拖住。",
            "support_system": "",
            "coping_style": "倾向于反复复盘成绩，需要先恢复睡眠和最小学习步。",
            "stressors": ["数学考试失利", "学业补救压力", "担心后续越来越学不进去"],
            "risk_signals": ["睡眠受损", "持续自责", "学习效率下降"],
            "stable_preferences": ["希望先被理解情绪，再慢慢拆解问题"],
            "recent_context": [
                "数学考试没有达到预期，用户把结果和自我能力联系在一起。",
                "最近夜间反复想考试，睡眠明显变差。",
            ],
        },
    )
    create_questionnaire_snapshot(
        user=users["demo_user_001"],
        conversation=conversations["demo_001_exam"],
        message=lin_latest_message,
        answers=[
            {
                "item_code": "isi_sleep_onset",
                "dimension": "sleep",
                "score": 3,
                "evidence": "这两天一到晚上就一直想这件事，常常两三点才睡。",
                "confidence": 0.86,
            },
            {
                "item_code": "phq_low_mood",
                "dimension": "mood",
                "score": 3,
                "evidence": "这次数学考试又没考好，我现在看到成绩就会发慌。",
                "confidence": 0.82,
            },
            {
                "item_code": "function_impairment",
                "dimension": "function",
                "score": 2,
                "evidence": "我现在最怕的是后面越来越学不进去。",
                "confidence": 0.78,
            },
            {
                "item_code": "gad_control",
                "dimension": "anxiety",
                "score": 3,
                "evidence": "这两天一到晚上就一直想这件事。",
                "confidence": 0.8,
            },
        ],
        total_score=11,
        stress_index=75,
        risk_level="medium",
        dimension_scores={"sleep": 3, "mood": 3, "function": 2, "anxiety": 3},
    )

    create_profile_memory(
        user=users["demo_user_002"],
        memory_json={
            "academic_status": "课程与实习任务叠加，对近期安排产生持续担忧。",
            "sleep_status": "",
            "emotion_pattern": "主要表现为紧张、担心两边都做不好，但能聚焦具体任务。",
            "support_system": "",
            "coping_style": "适合通过任务拆分和优先级排序恢复掌控感。",
            "stressors": ["实习和课程冲突", "多任务时间压力"],
            "risk_signals": ["持续紧张"],
            "stable_preferences": ["希望先整理重点，再给建议"],
            "recent_context": ["近期主要压力来自实习和课程撞期。"],
        },
    )
    create_questionnaire_snapshot(
        user=users["demo_user_002"],
        conversation=conversations["zhou_intern"],
        message=zhou_latest_message,
        answers=[
            {
                "item_code": "gad_worry",
                "dimension": "anxiety",
                "score": 3,
                "evidence": "这周实习和课程都堆在一起，我每天都在担心顾不过来。",
                "confidence": 0.8,
            },
            {
                "item_code": "function_impairment",
                "dimension": "function",
                "score": 2,
                "evidence": "而且我越忙越怕自己两边都做不好。",
                "confidence": 0.76,
            },
        ],
        total_score=5,
        stress_index=55,
        risk_level="medium",
        dimension_scores={"anxiety": 3, "function": 2},
    )

    create_profile_memory(
        user=users["demo_user_003"],
        memory_json={
            "academic_status": "考研阶段仍有压力，但近期节律和状态有所回稳。",
            "sleep_status": "最近晚上不会一直胡思乱想，睡眠较前期稳定。",
            "emotion_pattern": "整体情绪较稳定，能觉察自己比前段时间好一些。",
            "support_system": "",
            "coping_style": "通过保持作息和轻量表达维持状态。",
            "stressors": ["考研备考压力"],
            "risk_signals": [],
            "stable_preferences": ["偏好温和简洁的表达方式"],
            "recent_context": ["近期自评状态比前段时间稳定。"],
        },
    )
    create_questionnaire_snapshot(
        user=users["demo_user_003"],
        conversation=conversations["chen_stable"],
        message=chen_latest_message,
        answers=[
            {
                "item_code": "isi_sleep_impact",
                "dimension": "sleep",
                "score": 0,
                "evidence": "至少最近晚上不会一直胡思乱想了。",
                "confidence": 0.72,
            }
        ],
        total_score=0,
        stress_index=0,
        risk_level="low",
        dimension_scores={"sleep": 0},
    )

    create_assessment(
        user=users["demo_user_001"],
        conversation=conversations["demo_001_exam"],
        source="chat_analysis",
        mood_summary="数学考试失利后的挫败感明显，夜间开始出现反复担忧。",
        stress_index=58,
        risk_level="medium",
        advice="建议先把睡前一小时的学习和刷分行为停下来，给大脑一个缓冲区，再逐步拆分补救计划。",
        trend="从偶发紧张转为持续反刍，负面情绪在夜间更明显。",
        tag_names=["学业压力", "睡眠问题"],
        evaluated_at=_dt("2026-04-11 21:20"),
        risk_reason="近期对话显示考试失利后存在持续自责和夜间反复思考，但仍能维持基本学习安排。",
        core_psychological_issue="把一次考试失利快速内化为对自我能力的否定。",
    )
    create_assessment(
        user=users["demo_user_001"],
        conversation=conversations["demo_001_exam"],
        source="chat_analysis",
        mood_summary="睡眠问题加重，焦虑和自责同时上升，学习效率明显下降。",
        stress_index=72,
        risk_level="medium",
        advice="建议减少夜间独自复盘成绩的时间，把补救任务拆成更小的步骤，并优先恢复睡眠节律。",
        trend="近几天从单纯挫败感发展为持续焦虑，状态波动开始放大。",
        tag_names=["焦虑倾向", "睡眠问题", "学业压力"],
        evaluated_at=_dt("2026-04-13 22:20"),
        risk_reason="对话中多次提到夜间失眠、反复回想成绩和明显的学不进去，负向状态持续扩大。",
        core_psychological_issue="对失败的反刍正在挤占休息和恢复空间。",
    )
    create_assessment(
        user=users["demo_user_001"],
        conversation=conversations["demo_001_exam"],
        source="chat_analysis",
        mood_summary="近期呈现高压与低落叠加状态，存在明显的学业压力和睡眠受损。",
        stress_index=75,
        risk_level="medium",
        advice="建议优先稳定作息与睡眠，减少夜间反刍；若低落、失眠或安全风险信号继续加重，应尽快结合人工关注。",
        trend="从考试后的短期挫败，发展为连续几天的失眠、自责和无力感，风险明显上升。",
        tag_names=["低落情绪", "睡眠问题", "学业压力"],
        evaluated_at=_dt("2026-04-15 09:08"),
        risk_reason="近期对话反复出现考试失利后的失眠、持续自责、学习效率下降和焦虑反刍，属于需要重点关注的中风险；目前未见明确自伤意图、计划或急性安全红线。",
        core_psychological_issue="把数学考试失利等同于对自我价值的全面否定，导致焦虑和低落不断放大。",
    )

    create_assessment(
        user=users["demo_user_002"],
        conversation=conversations["zhou_intern"],
        source="chat_analysis",
        mood_summary="课程与实习冲突带来的压力较明显，存在持续紧张和担忧。",
        stress_index=64,
        risk_level="medium",
        advice="建议先明确近期最关键的两项任务，避免同时处理所有待办带来的失控感。",
        trend="近几天压力持续但相对稳定，主要来自时间安排和自我要求过高。",
        tag_names=["焦虑倾向", "学业压力"],
        evaluated_at=_dt("2026-04-12 20:20"),
        risk_reason="对话中明确提到任务堆积、害怕两边都做不好，焦虑来源较清晰但尚未出现明显崩溃信号。",
        core_psychological_issue="对多任务失控的担忧，正在放大自我要求和紧张感。",
    )
    create_assessment(
        user=users["demo_user_002"],
        conversation=conversations["zhou_intern"],
        source="chat_analysis",
        mood_summary="近期依旧偏紧张，但已能识别主要压力来源，状态较前几天略有收束。",
        stress_index=55,
        risk_level="medium",
        advice="建议继续维持任务拆分和节奏控制，避免把短期忙碌解释为长期失控。",
        trend="整体仍处于中等压力区间，但比前期更能聚焦问题本身。",
        tag_names=["焦虑倾向", "学业压力"],
        evaluated_at=_dt("2026-04-15 11:10"),
        risk_reason="虽然仍有明显焦虑，但已开始聚焦具体安排问题，风险未见进一步升级。",
        core_psychological_issue="对时间安排失控的担忧依然存在，但已开始恢复秩序感。",
    )

    create_assessment(
        user=users["demo_user_003"],
        conversation=conversations["chen_stable"],
        source="chat_analysis",
        mood_summary="整体状态较为平稳，偶有压力，但情绪恢复能力较好。",
        stress_index=34,
        risk_level="low",
        advice="建议维持当前节律，继续保留稳定作息与轻量表达的习惯。",
        trend="近一周状态比较稳定，未见明显恶化信号。",
        tag_names=["状态稳定"],
        evaluated_at=_dt("2026-04-11 08:40"),
        risk_reason="对话中主要表现为轻度压力和正常波动，未见持续性低落或明显功能受损。",
        core_psychological_issue="当前以日常压力调节为主，整体恢复力较好。",
    )
    create_assessment(
        user=users["demo_user_003"],
        conversation=conversations["chen_stable"],
        source="chat_analysis",
        mood_summary="近期节律持续稳定，情绪波动较小。",
        stress_index=26,
        risk_level="low",
        advice="建议保持现有作息与表达习惯，继续通过日常陪伴巩固稳定状态。",
        trend="相较前几天更稳定，睡眠与情绪均无明显异常。",
        tag_names=["状态稳定"],
        evaluated_at=_dt("2026-04-15 08:24"),
        risk_reason="近期表达偏平稳，能主动觉察和描述自己的状态变化，未见显著风险信号。",
        core_psychological_issue="当前更多是保持稳定，而非处理明显风险。",
    )

    intervention = InterventionSession(
        conversation_id=conversations["zhou_intern"].id,
        user_id=users["demo_user_002"].id,
        admin_id=admin.id,
        trigger_assessment_id=Assessment.query.filter_by(user_id=users["demo_user_002"].id)
        .order_by(Assessment.evaluated_at.desc(), Assessment.id.desc())
        .first()
        .id,
        status="ended",
        note="用户在课程与实习冲突阶段出现持续紧张，曾进行一次人工承接与任务拆分指导。",
        started_at=_dt("2026-04-14 20:50"),
        ended_at=_dt("2026-04-14 21:18"),
    )
    db.session.add(intervention)
    db.session.flush()

    db.session.add_all(
        [
            Message(
                conversation_id=conversations["zhou_intern"].id,
                sender_type="human",
                sender_user_id=admin.id,
                intervention_session_id=intervention.id,
                content_type="text",
                content_text="我先陪你把最紧的两件事排出来，不需要今晚一下子把所有安排都想明白。",
                created_at=_dt("2026-04-14 20:56"),
            ),
            Message(
                conversation_id=conversations["zhou_intern"].id,
                sender_type="human",
                sender_user_id=admin.id,
                intervention_session_id=intervention.id,
                content_type="text",
                content_text="这两天先保住课程截止和实习签到，其余任务我们再往后拆，不必同时证明自己两边都完美。",
                created_at=_dt("2026-04-14 21:05"),
            ),
        ]
    )
    conversations["zhou_intern"].summary = "曾进行一次人工承接与任务拆分指导，当前压力较前期略有收束。"
    conversations["zhou_intern"].latest_message_at = _dt("2026-04-14 21:05")
    conversations["zhou_intern"].updated_at = _dt("2026-04-14 21:05")

    save_system_settings(
        {
            "defaultDigitalHuman": {
                "activeCode": "haru",
                "options": [
                    {
                        "code": "haru",
                        "label": "Haru",
                        "description": "温柔、安静，适合作为默认陪伴角色。",
                    },
                    {
                        "code": "hiyori",
                        "label": "Hiyori Momose",
                        "description": "更明亮、轻快，适合偏积极的陪伴风格。",
                    },
                ],
            },
            "promptTemplate": (
                "你是“心陪陪”，一个面向大学生心理支持场景的温和、耐心、克制的陪伴助手。"
                "请优先承接用户情绪，避免诊断式表达和空泛说教，给出贴近当下、可执行的小建议。"
            ),
        }
    )

    db.session.commit()
    return {
        "seeded": True,
        "message": "视频演示数据初始化完成。",
        "accounts": {
            "admin": {"phone": "DEMO_ADMIN", "password": "DEMO_PASSWORD"},
            "main_user": {"phone": "DEMO_USER_001", "password": "DEMO_PASSWORD"},
            "other_users": [
                {"phone": "DEMO_USER_002", "password": "DEMO_PASSWORD"},
                {"phone": "DEMO_USER_003", "password": "DEMO_PASSWORD"},
                {"phone": "DEMO_USER_004", "password": "DEMO_PASSWORD"},
            ],
        },
    }

