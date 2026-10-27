from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import utcnow


class Assessment(db.Model):
    __tablename__ = "assessments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    source = db.Column(db.String(32), nullable=False)
    mood_summary = db.Column(db.Text)
    stress_index = db.Column(db.Integer)
    risk_level = db.Column(db.String(20))
    advice = db.Column(db.Text)
    raw_result_json = db.Column(db.JSON)
    evaluated_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="assessments")
    conversation = db.relationship("Conversation", back_populates="assessments")
    tags = db.relationship("AssessmentTag", back_populates="assessment", cascade="all, delete-orphan")
    intervention_sessions = db.relationship("InterventionSession", back_populates="trigger_assessment")


class AssessmentTag(db.Model):
    __tablename__ = "assessment_tags"
    __table_args__ = (UniqueConstraint("assessment_id", "tag_id", name="uq_assessment_tag_assessment_tag"),)

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey("tag_library.id"), nullable=False)

    assessment = db.relationship("Assessment", back_populates="tags")
    tag = db.relationship("TagLibrary", back_populates="assessment_tags")
