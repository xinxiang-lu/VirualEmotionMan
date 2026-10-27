from ..extensions import db
from .base import utcnow


class UserProfileMemory(db.Model):
    __tablename__ = "user_profile_memories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    template_version = db.Column(db.String(32), nullable=False, default="v1")
    memory_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="profile_memory")
    events = db.relationship("UserProfileMemoryEvent", back_populates="memory", cascade="all, delete-orphan")


class UserProfileMemoryEvent(db.Model):
    __tablename__ = "user_profile_memory_events"

    id = db.Column(db.Integer, primary_key=True)
    memory_id = db.Column(db.Integer, db.ForeignKey("user_profile_memories.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"))
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"))
    field = db.Column(db.String(64), nullable=False)
    operation = db.Column(db.String(20), nullable=False, default="upsert")
    old_value_json = db.Column(db.JSON)
    new_value_json = db.Column(db.JSON)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    evidence_text = db.Column(db.Text)
    source = db.Column(db.String(32), nullable=False, default="rules")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    memory = db.relationship("UserProfileMemory", back_populates="events")

