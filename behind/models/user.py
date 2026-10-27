from sqlalchemy import UniqueConstraint

from ..extensions import db
from .base import utcnow


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(32), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    last_login_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    profile = db.relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    profile_memory = db.relationship(
        "UserProfileMemory",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    settings = db.relationship("UserSetting", back_populates="user", uselist=False, cascade="all, delete-orphan")
    conversations = db.relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    profile_goals = db.relationship("UserProfileGoal", back_populates="user", cascade="all, delete-orphan")
    assessments = db.relationship("Assessment", back_populates="user")
    multimodal_analyses = db.relationship("MultimodalAnalysis", back_populates="user", cascade="all, delete-orphan")
    sent_messages = db.relationship("Message", back_populates="sender_user", foreign_keys="Message.sender_user_id")
    interventions_as_user = db.relationship(
        "InterventionSession",
        back_populates="user",
        foreign_keys="InterventionSession.user_id",
    )
    interventions_as_admin = db.relationship(
        "InterventionSession",
        back_populates="admin",
        foreign_keys="InterventionSession.admin_id",
    )


class UserProfile(db.Model):
    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    nickname = db.Column(db.String(64))
    gender = db.Column(db.String(16))
    age = db.Column(db.Integer)
    occupation = db.Column(db.String(64))
    avatar_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="profile")


class UserSetting(db.Model):
    __tablename__ = "user_settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    custom_prompt = db.Column(db.Text)
    digital_human_code = db.Column(db.String(64))
    voice_speed = db.Column(db.Float, nullable=False, default=1.0)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="settings")


class UserProfileGoal(db.Model):
    __tablename__ = "user_profile_goals"
    __table_args__ = (UniqueConstraint("user_id", "tag_id", name="uq_user_profile_goal_user_tag"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey("tag_library.id"), nullable=False)

    user = db.relationship("User", back_populates="profile_goals")
    tag = db.relationship("TagLibrary", back_populates="user_profile_goals")
