#!/usr/bin/env python3
"""helpers for aligning subscriber records with user accounts."""
from __future__ import annotations

from typing import Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from shared.db import db
from .models import User


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def ensure_user_stub(email: str, *, commit: bool = True) -> Tuple[User | None, bool]:
    """
    ensure there is a User row for the email, creating a placeholder account when
    someone subscribes via email-only flows.

    returns (user, created_flag).
    """
    normalized = _normalize_email(email)
    if not normalized:
        return None, False

    existing = User.query.filter(func.lower(User.email) == normalized).first()
    if existing:
        return existing, False

    # blank password_hash signals “needs password set”
    placeholder = User(email=normalized, password_hash="")
    db.session.add(placeholder)

    if commit:
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            placeholder = User.query.filter(func.lower(User.email) == normalized).first()
            return placeholder, False
    else:
        db.session.flush()

    return placeholder, True
