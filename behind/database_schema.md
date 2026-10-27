# 数据库结构

当前后端按 Flask + SQLAlchemy 设计，第一版核心表如下。

## users

- `id`
- `username`
- `email`
- `phone`
- `password`
- `role`
- `last_login_at`
- `created_at`
- `updated_at`

说明：

- 当前 `password` 按需求先保留明文，后续建议改回哈希。

## user_profiles

- `id`
- `user_id`
- `nickname`
- `gender`
- `birth_date`
- `occupation`
- `avatar_url`
- `created_at`
- `updated_at`

## user_settings

- `id`
- `user_id`
- `custom_prompt`
- `digital_human_code`
- `voice_speed`
- `updated_at`

## tag_library

- `id`
- `name`
- `tag_type`
- `description`
- `sort_order`
- `is_active`

说明：

- `tag_type`：`risk / emotion / resource / usage_goal`

## user_profile_goals

- `id`
- `user_id`
- `tag_id`

说明：

- 支持注册页“使用目的”多选。

## conversations

- `id`
- `user_id`
- `title`
- `summary`
- `status`
- `latest_message_at`
- `created_at`
- `updated_at`

## messages

- `id`
- `conversation_id`
- `sender_type`
- `sender_user_id`
- `intervention_session_id`
- `content_type`
- `content_text`
- `audio_url`
- `video_url`
- `created_at`

## assessments

- `id`
- `user_id`
- `conversation_id`
- `source`
- `mood_summary`
- `stress_index`
- `risk_level`
- `advice`
- `raw_result_json`
- `evaluated_at`
- `created_at`

## assessment_tags

- `id`
- `assessment_id`
- `tag_id`

## intervention_sessions

- `id`
- `conversation_id`
- `user_id`
- `admin_id`
- `trigger_assessment_id`
- `status`
- `note`
- `started_at`
- `ended_at`

说明：

- 当前按需求移除了 `created_at`，只保留 `started_at`。
