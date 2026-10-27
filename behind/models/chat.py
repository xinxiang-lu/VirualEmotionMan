from ..extensions import db
from .base import utcnow


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="active")
    latest_message_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="conversations")
    messages = db.relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    multimodal_analyses = db.relationship("MultimodalAnalysis", back_populates="conversation", cascade="all, delete-orphan")
    assessments = db.relationship("Assessment", back_populates="conversation")
    intervention_sessions = db.relationship(
        "InterventionSession",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    intervention_session_id = db.Column(db.Integer, db.ForeignKey("intervention_sessions.id"))
    content_type = db.Column(db.String(20), nullable=False, default="text")
    content_text = db.Column(db.Text)
    audio_url = db.Column(db.String(255))
    video_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    conversation = db.relationship("Conversation", back_populates="messages")
    sender_user = db.relationship("User", back_populates="sent_messages", foreign_keys=[sender_user_id])
    intervention_session = db.relationship("InterventionSession", back_populates="messages")
    multimodal_analysis = db.relationship(
        "MultimodalAnalysis",
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )
