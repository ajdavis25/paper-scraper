#!/usr/bin/env python3
"""models.py — ORM models for astro-ph digest backend."""
from datetime import datetime
from flask_login import UserMixin
from shared.db import db

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


class PreferenceConfig(db.Model):
    __tablename__ = "preference_config"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    keywords = db.Column(db.JSON, default=list)
    authors = db.Column(db.JSON, default=list)
    categories = db.Column(db.JSON, default=list)
    min_score = db.Column(db.Float, default=1.0)

    user = db.relationship(
        "User",
        backref=db.backref(
            "preference_config",
            uselist=False,
            cascade="all, delete-orphan",
        ),
    )

    def as_dict(self):
        return {
            "keywords": list(self.keywords or []),
            "authors": list(self.authors or []),
            "categories": list(self.categories or ["astro-ph"]),
            "min_score": self.min_score if self.min_score is not None else 1.0,
        }

    @classmethod
    def get_or_create_for_user(cls, user, *, commit=True):
        """
        fetch the preference config for a specific user, cloning the global
        defaults (user_id NULL) when necessary.
        """
        if not user:
            return None

        existing = cls.query.filter_by(user_id=user.id).first()
        if existing:
            return existing

        defaults = cls.query.filter_by(user_id=None).first()
        config = cls(
            user_id=user.id,
            keywords=list((defaults.keywords if defaults else []) or []),
            authors=list((defaults.authors if defaults else []) or []),
            categories=list((defaults.categories if defaults else []) or ["astro-ph"]),
            min_score=defaults.min_score if defaults and defaults.min_score is not None else 1.0,
        )
        db.session.add(config)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return config


def ensure_preference_config_schema():
    """
    ensure the preference_config table has a user_id column so we can store
    per-user preferences. if the column already exists, nothing happens.
    """
    from sqlalchemy import inspect, text

    engine = db.engine
    inspector = inspect(engine)
    if not inspector.has_table("preference_config"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("preference_config")}
    if "user_id" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE preference_config ADD COLUMN user_id INTEGER"))
            if engine.dialect.name == "postgresql":
                try:
                    conn.execute(
                        text(
                            'ALTER TABLE preference_config ADD CONSTRAINT '
                            'preference_config_user_id_fkey FOREIGN KEY (user_id) '
                            'REFERENCES "user"(id) ON DELETE CASCADE'
                        )
                    )
                except Exception as exc:  # constraint may already exist
                    print(f"[migrate] warning adding FK preference_config_user_id_fkey: {exc}")
            try:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS preference_config_user_id_idx "
                        "ON preference_config(user_id)"
                    )
                )
            except Exception as exc:
                print(f"[migrate] warning creating preference_config_user_id_idx: {exc}")

    # ensure a default/global config row exists for cloning new users
    if not PreferenceConfig.query.filter_by(user_id=None).first():
        db.session.add(PreferenceConfig())
        db.session.commit()
