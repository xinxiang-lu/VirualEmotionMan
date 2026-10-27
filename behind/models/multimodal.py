from __future__ import annotations

import json

from ..extensions import db
from .base import utcnow


class MultimodalAnalysis(db.Model):
    __tablename__ = "multimodal_analyses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=False, unique=True, index=True)
    analysis_mode = db.Column(db.String(32), nullable=False, default="partial_media")
    selected_candidate = db.Column(db.Integer)
    transcript_text = db.Column(db.Text)
    transcript_confidence = db.Column(db.Float)
    summary_payload_text = db.Column(db.Text)
    prediction_artifact_path = db.Column(db.String(512))
    summary_artifact_path = db.Column(db.String(512))
    has_prediction = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="multimodal_analyses")
    conversation = db.relationship("Conversation", back_populates="multimodal_analyses")
    message = db.relationship("Message", back_populates="multimodal_analysis")

    def set_summary_payload(self, payload: dict | None) -> None:
        self.summary_payload_text = json.dumps(payload or {}, ensure_ascii=False)

    def get_summary_payload(self) -> dict | None:
        if not self.summary_payload_text:
            return None
        try:
            return json.loads(self.summary_payload_text)
        except json.JSONDecodeError:
            return None
