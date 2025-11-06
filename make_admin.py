#!/usr/bin/env python3
"""
promote a user to admin status in the configured database.
usage: python make_admin.py user@example.com
"""

import os
import sys

from sqlalchemy import text

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def normalize_url(url: str) -> str:
    if not url:
        return ""

    # handle accidental "DATABASE_URL=" prefix in .env values
    if url.startswith("DATABASE_URL="):
        url = url.split("DATABASE_URL=", 1)[1]

    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]

    if "sslmode=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"

    return url


def main():
    if load_dotenv:
        load_dotenv()

    if len(sys.argv) != 2:
        print("usage: python make_admin.py user@example.com", file=sys.stderr)
        sys.exit(1)

    target_email = sys.argv[1].strip().lower()
    if not target_email:
        print("provide a valid email.", file=sys.stderr)
        sys.exit(1)

    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        print("DATABASE_URL is not set. configure your Neon SQLAlchemy string.", file=sys.stderr)
        sys.exit(1)

    database_url = normalize_url(raw_url)
    if "pooler" not in database_url:
        print("warning: connection string does not include 'pooler'. Neon recommends using the pooled endpoint.")

    try:
        from sqlalchemy import create_engine

        engine = create_engine(database_url, future=True)
    except Exception as exc:  # pragma: no cover
        print(f"failed to create SQLAlchemy engine: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[make_admin] using database: {database_url}")

    stmt = text("UPDATE public.user SET is_admin = TRUE WHERE lower(email) = :email RETURNING email")

    try:
        with engine.begin() as conn:
            result = conn.execute(stmt, {"email": target_email}).fetchone()
            if result:
                print(f"{result.email} is now an admin!")
            else:
                print(f"no user found with email '{target_email}'.")
                sys.exit(1)
    except Exception as exc:  # pragma: no cover
        print(f"failed to update admin flag: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
