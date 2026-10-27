from ..extensions import db


class InterventionSession(db.Model):
    __tablename__ = "intervention_sessions"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    trigger_assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"))
    status = db.Column(db.String(20), nullable=False, default="active")
    note = db.Column(db.Text)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ended_at = db.Column(db.DateTime(timezone=True))

    conversation = db.relationship("Conversation", back_populates="intervention_sessions")
    user = db.relationship("User", back_populates="interventions_as_user", foreign_keys=[user_id])
    admin = db.relationship("User", back_populates="interventions_as_admin", foreign_keys=[admin_id])
    trigger_assessment = db.relationship("Assessment", back_populates="intervention_sessions")
    messages = db.relationship("Message", back_populates="intervention_session")
