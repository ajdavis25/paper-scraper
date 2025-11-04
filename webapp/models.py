"""
models.py — orm models for astro-ph digest backend.
refactored for clarity, constraints, and convenience methods.
"""
from datetime import datetime
from flask_login import UserMixin
from shared.db import db


# ---------------------------------------------------------------------------
# base mixins
# ---------------------------------------------------------------------------
class TimestampMixin:
    """adds created_at and updated_at columns."""
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# core tables
# ---------------------------------------------------------------------------
class User(db.Model, UserMixin, TimestampMixin):
    """represents a subscriber or feedback submitter."""
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)

    # relationships
    preferences = db.relationship(
        "UserPreference", back_populates="user",
        cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self):
        return f"<User {self.email}>"


class Paper(db.Model, TimestampMixin):
    """represents an arXiv paper entry."""
    __tablename__ = "paper"

    id = db.Column(db.Integer, primary_key=True)
    arxiv_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    title = db.Column(db.String(512))
    abstract = db.Column(db.Text)
    link = db.Column(db.String(512))

    preferences = db.relationship(
        "UserPreference", back_populates="paper",
        cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self):
        return f"<Paper {self.arxiv_id or self.title[:30]}>"


class UserPreference(db.Model, TimestampMixin):
    """join table linking a user to a paper with a like/dislike reaction."""
    __tablename__ = "user_preference"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"))
    paper_id = db.Column(db.Integer, db.ForeignKey("paper.id", ondelete="CASCADE"))
    liked = db.Column(db.Boolean, default=True, nullable=False)

    user = db.relationship("User", back_populates="preferences")
    paper = db.relationship("Paper", back_populates="preferences")

    __table_args__ = (
        db.UniqueConstraint("user_id", "paper_id", name="uq_user_paper"),
    )

    def __repr__(self):
        return f"<UserPreference user={self.user_id} paper={self.paper_id} liked={self.liked}>"
