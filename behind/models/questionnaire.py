from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import utcnow


class QuestionnaireSession(db.Model):
    __tablename__ = "questionnaire_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    scale_id = db.Column(db.String(64), nullable=False, default="")
    scale_name = db.Column(db.String(120), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="active")
    active_dimension = db.Column(db.String(64))
    pending_item_code = db.Column(db.String(64))
    last_question_text = db.Column(db.Text)
    required_item_count = db.Column(db.Integer, nullable=False, default=0)
    answered_item_count = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer)
    risk_level = db.Column(db.String(20))
    summary_json = db.Column(db.JSON)
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class QuestionnaireAnswer(db.Model):
    __tablename__ = "questionnaire_answers"
    __table_args__ = (
        UniqueConstraint("message_id", "item_code", name="uq_questionnaire_answer_message_item"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("questionnaire_sessions.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=False)
    scale_id = db.Column(db.String(64), nullable=False, default="")
    item_code = db.Column(db.String(64), nullable=False)
    dimension = db.Column(db.String(64), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    evidence_text = db.Column(db.Text)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    source = db.Column(db.String(32), nullable=False, default="rules")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class QuestionnaireScore(db.Model):
    __tablename__ = "questionnaire_scores"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("questionnaire_sessions.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    scale_id = db.Column(db.String(64), nullable=False, default="")
    scale_name = db.Column(db.String(120), nullable=False, default="")
    source = db.Column(db.String(32), nullable=False, default="dialogue_questionnaire")
    total_score = db.Column(db.Integer, nullable=False, default=0)
    stress_index = db.Column(db.Integer, nullable=False, default=0)
    risk_level = db.Column(db.String(20), nullable=False, default="low")
    dimension_scores_json = db.Column(db.JSON, nullable=False, default=dict)
    basis_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
