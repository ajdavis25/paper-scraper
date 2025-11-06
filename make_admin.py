#!/usr/bin/env python3
"""
promote a user to admin status in the current database.

usage:
    python make_admin.py user@example.com
    python make_admin.py user@example.com --database-url postgresql+psycopg://...
"""
import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import func

from webapp import create_app
from webapp.models import User
from shared.db import db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote an existing user to admin.")
    parser.add_argument("email", help="Email address of the user to promote")
    parser.add_argument(
        "--database-url",
        help="Override DATABASE_URL for this run (defaults to environment/.env)",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    target_email = args.email.strip().lower()
    if not target_email:
        print("please provide a valid email address.", file=sys.stderr)
        sys.exit(1)

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    app = create_app()

    with app.app_context():
        print(f"[make_admin] using database: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
        user = User.query.filter(func.lower(User.email) == target_email).first()

        if not user:
            print(f"no user found with email '{target_email}'.")
            sys.exit(1)

        if user.is_admin:
            print(f"{user.email} is already an admin.")
            return

        try:
            user.is_admin = True
            db.session.commit()
            print(f"{user.email} is now an admin!")
        except Exception as exc:  # pragma: no cover
            db.session.rollback()
            print(f"failed to update admin status: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
