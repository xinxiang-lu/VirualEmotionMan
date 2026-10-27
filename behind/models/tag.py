from sqlalchemy import UniqueConstraint

from ..extensions import db


class TagLibrary(db.Model):
    __tablename__ = "tag_library"
    __table_args__ = (UniqueConstraint("name", "tag_type", name="uq_tag_library_name_type"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    tag_type = db.Column(db.String(32), nullable=False)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    user_profile_goals = db.relationship("UserProfileGoal", back_populates="tag")
    assessment_tags = db.relationship("AssessmentTag", back_populates="tag")
