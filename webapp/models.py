#!/usr/bin/env python3
"""models.py — ORM models for astro-ph digest backend."""
from datetime import datetime
from flask_login import UserMixin
from astroph_bot.shared.db import db

# ---------------------------------------------------------------------------
# mixins
# ---------------------------------------------------------------------------
class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow,
        onupdate=datetime.utcnow, nullable=False
    )

# ---------------------------------------------------------------------------
# core tables
# ---------------------------------------------------------------------------
class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False, default="")
    is_admin = db.Column(db.Boolean, default=False)

    preferences = db.relationship(
        "UserPreference",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def get_id(self):
        return self.email


class Subscriber(db.Model):
    __tablename__ = "subscriber"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Paper(db.Model, TimestampMixin):
    __tablename__ = "paper"

    id = db.Column(db.Integer, primary_key=True)
    arxiv_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    title = db.Column(db.String(512))
    abstract = db.Column(db.Text)
    link = db.Column(db.String(512))

    preferences = db.relationship(
        "UserPreference",
        back_populates="paper",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(50), default="contact")
    arxiv_id = db.Column(db.String(50), nullable=True)
    liked = db.Column(db.Boolean, nullable=True)
    source = db.Column(db.String(50), default="recommendations", nullable=True)


class UserPreference(db.Model, TimestampMixin):
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
