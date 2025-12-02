#!/usr/bin/env python3
"""models.py — ORM models for arxiv digest backend."""
from datetime import datetime
from flask_login import UserMixin
from shared.db import db
from shared.preferences import WEIGHT_DEFAULTS as PREF_WEIGHT_DEFAULTS

# mixins
class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow,
        onupdate=datetime.utcnow, nullable=False
    )

# core tables
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

    WEIGHT_DEFAULTS = PREF_WEIGHT_DEFAULTS.copy()

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    keywords = db.Column(db.JSON, default=list)
    excluded_keywords = db.Column(db.JSON, default=list)
    authors = db.Column(db.JSON, default=list)
    categories = db.Column(db.JSON, default=list)
    min_score = db.Column(db.Float, default=1.0)
    keyword_weight = db.Column(db.Float, default=WEIGHT_DEFAULTS["keyword_weight"])
    author_weight = db.Column(db.Float, default=WEIGHT_DEFAULTS["author_weight"])
    exclude_penalty = db.Column(db.Float, default=WEIGHT_DEFAULTS["exclude_penalty"])
    all_bonus = db.Column(db.Float, default=WEIGHT_DEFAULTS["all_bonus"])

    user = db.relationship(
        "User",
        backref=db.backref(
            "preference_config",
            uselist=False,
            cascade="all, delete-orphan",
        ),
    )

    def as_dict(self):
        payload = {
            "keywords": list(self.keywords or []),
            "excluded_keywords": list(self.excluded_keywords or []),
            "authors": list(self.authors or []),
            "categories": list(self.categories or ["astro-ph"]),
            "min_score": self.min_score if self.min_score is not None else 1.0,
        }
        for field, default in self.WEIGHT_DEFAULTS.items():
            value = getattr(self, field, None)
            payload[field] = value if value is not None else default
        return payload

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
        weight_defaults = defaults.as_dict() if defaults else {}
        config = cls(
            user_id=user.id,
            keywords=list((defaults.keywords if defaults else []) or []),
            excluded_keywords=list((defaults.excluded_keywords if defaults else []) or []),
            authors=list((defaults.authors if defaults else []) or []),
            categories=list((defaults.categories if defaults else []) or ["astro-ph"]),
            min_score=defaults.min_score if defaults and defaults.min_score is not None else 1.0,
            keyword_weight=weight_defaults.get("keyword_weight", cls.WEIGHT_DEFAULTS["keyword_weight"]),
            author_weight=weight_defaults.get("author_weight", cls.WEIGHT_DEFAULTS["author_weight"]),
            exclude_penalty=weight_defaults.get("exclude_penalty", cls.WEIGHT_DEFAULTS["exclude_penalty"]),
            all_bonus=weight_defaults.get("all_bonus", cls.WEIGHT_DEFAULTS["all_bonus"]),
        )
        db.session.add(config)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return config


class RecommendationSnapshot(db.Model, TimestampMixin):
    __tablename__ = "recommendation_snapshot"
    __table_args__ = (
        db.UniqueConstraint("user_id", "arxiv_id", name="uq_snapshot_user_paper"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    arxiv_id = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(512))
    link = db.Column(db.String(512))
    score = db.Column(db.Float, nullable=True)
    matched_keywords = db.Column(db.JSON, default=list)
    matched_authors = db.Column(db.JSON, default=list)
    details = db.Column(db.JSON, default=dict)
    feedback = db.Column(db.Boolean, nullable=True)


class GmailWatchState(db.Model, TimestampMixin):
    __tablename__ = "gmail_watch_state"

    id = db.Column(db.Integer, primary_key=True)
    history_id = db.Column(db.String(128), nullable=True)
    label_id = db.Column(db.String(128), nullable=True)

    @classmethod
    def get_state(cls) -> "GmailWatchState":
        """return the singleton state row (creates it with null history if missing)."""
        state = cls.query.first()
        if not state:
            state = cls()
            db.session.add(state)
            db.session.commit()
        return state

    @classmethod
    def update_history(cls, history_id: str | None, label_id: str | None = None):
        """persist the most recent Gmail history id (and optional label)."""
        state = cls.get_state()
        if history_id:
            state.history_id = str(history_id)
        if label_id:
            state.label_id = label_id
        db.session.commit()


class DeliveryEvent(db.Model, TimestampMixin):
    __tablename__ = "delivery_event"

    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(255), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="sent", index=True)
    context = db.Column(db.String(64), nullable=True)
    provider = db.Column(db.String(64), nullable=True)
    error = db.Column(db.Text, nullable=True)

    @staticmethod
    def _clean_subject(subject: str | None) -> str:
        trimmed = (subject or "").strip()
        return trimmed[:255]

    @classmethod
    def log_event(
        cls,
        *,
        recipient: str,
        subject: str | None,
        status: str,
        context: str | None = None,
        provider: str | None = None,
        error: str | None = None,
        auto_commit: bool = True,
    ):
        """record a delivery attempt for operator insight."""
        normalized_recipient = (recipient or "").strip().lower() or "(unknown)"
        event = cls(
            recipient=normalized_recipient,
            subject=cls._clean_subject(subject),
            status=(status or "unknown").strip().lower(),
            context=(context or None),
            provider=(provider or None),
            error=(error or None),
        )
        db.session.add(event)
        if not auto_commit:
            return event
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"[delivery-event] failed to commit log entry: {exc}")
        return event


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

    if "excluded_keywords" not in existing_columns:
        with engine.begin() as conn:
            try:
                conn.execute(text("ALTER TABLE preference_config ADD COLUMN excluded_keywords JSON"))
            except Exception as exc:
                print(f"[migrate] warning adding excluded_keywords column: {exc}")

    # ensure scoring weight columns exist (keyword_weight, author_weight, etc.)
    for field, default in PreferenceConfig.WEIGHT_DEFAULTS.items():
        if field in existing_columns:
            continue
        column_type = "REAL"
        alter_sql = f"ALTER TABLE preference_config ADD COLUMN {field} {column_type} DEFAULT {default}"
        with engine.begin() as conn:
            try:
                conn.execute(text(alter_sql))
            except Exception as exc:
                print(f"[migrate] warning adding {field} column: {exc}")

    # ensure a default/global config row exists for cloning new users
    if not PreferenceConfig.query.filter_by(user_id=None).first():
        db.session.add(PreferenceConfig())
        db.session.commit()
