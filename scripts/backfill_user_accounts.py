#!/usr/bin/env python3
"""
Ensure every subscriber has a placeholder User account.

Run once (or as needed) to let legacy email-only subscribers finish signup.
"""
from __future__ import annotations

from webapp import create_app
from webapp.account_utils import ensure_user_stub
from webapp.models import Subscriber
from shared.db import db


def main():
    app = create_app()
    created = 0

    with app.app_context():
        subscribers = Subscriber.query.all()
        for sub in subscribers:
            _, made = ensure_user_stub(sub.email, commit=False)
            if made:
                created += 1
        db.session.commit()

    print(f"[backfill] processed {len(subscribers)} subscribers; created {created} new user stub(s).")


if __name__ == "__main__":
    main()
