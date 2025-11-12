# shared/db.py
"""
database helper utilities for resolving a usable SQLAlchemy connection URI.

the goals:
  * respect an explicitly configured `DATABASE_URL`.
  * normalize Neon/Postgres URLs so SQLAlchemy uses the `psycopg` driver and
    enforces SSL (Neon requires it).
  * when the URL points at SQLite, make sure the target location is writable,
    falling back to `/tmp/feedback.db` on read-only deployments.
  * maintain backwards compatibility with the previous `init_app(app)` call
    pattern used by `webapp/__init__.py`.
"""

from __future__ import annotations

import os, sqlite3, tempfile
from contextlib import suppress
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from flask_sqlalchemy import SQLAlchemy


class ConfiguredSQLAlchemy(SQLAlchemy):
    def init_app(self, app):
        resolved = resolve_database_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
        app.config["SQLALCHEMY_DATABASE_URI"] = resolved
        app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

        # ensure long-lived (serverless) deployments gracefully recover when Neon/PG
        # closes idle connections. pre_ping tests connections before use; recycle
        # forces a reconnect periodically; timeout keeps failures fast.
        engine_opts = app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
        engine_opts.setdefault("pool_pre_ping", True)
        engine_opts.setdefault("pool_recycle", 300)
        engine_opts.setdefault("pool_timeout", 10)

        super().init_app(app)


db = ConfiguredSQLAlchemy()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_NAME = "feedback.db"
_SQLITE_PREFIX = "sqlite:///"
_POSTGRES_SCHEMES = {"postgresql", "postgres", "postgresql+psycopg"}


def _sqlite_uri_for(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _ensure_sqlite_path(path: Path) -> Optional[Path]:
    """
    attempt to create a SQLite file (or at least its parent directory).
    return the resolved path on success, or None if we cannot write there.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[db] warning: cannot create directory {path.parent}: {exc}")
        return None

    try:
        conn = sqlite3.connect(path.as_posix())
        try:
            conn.execute("PRAGMA user_version = 1;")
            conn.commit()
        finally:
            conn.close()
        return path
    except sqlite3.OperationalError as exc:
        print(f"[db] warning: SQLite path {path} not writable: {exc}")
        with suppress(FileNotFoundError):
            path.unlink()
    except Exception as exc:  # pragma: no cover - defensive guard
        print(f"[db] warning: unexpected SQLite error at {path}: {exc}")
        with suppress(FileNotFoundError):
            path.unlink()
    return None


def _fallback_sqlite_uri() -> str:
    tmp_path = (Path(tempfile.gettempdir()) / _DEFAULT_SQLITE_NAME).resolve()
    usable = _ensure_sqlite_path(tmp_path)
    if not usable:
        raise RuntimeError("cannot obtain a writable SQLite database location.")
    print(f"[db] using temporary sqlite database at {usable}")
    return _sqlite_uri_for(usable)


def _normalize_postgres_uri(uri: str) -> str:
    """
    convert postgres:// URIs to the SQLAlchemy preferred form:
      - ensure scheme is `postgresql+psycopg`
      - ensure `sslmode=require` is present (Neon mandates TLS)
    """
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme not in _POSTGRES_SCHEMES:
        return uri

    new_scheme = "postgresql+psycopg"
    query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_pairs.setdefault("sslmode", "require")
    new_query = urlencode(query_pairs)

    normalized = urlunparse(
        (
            new_scheme,
            parsed.netloc,
            parsed.path or "",
            "",  # params (deprecated in URLs, unused here)
            new_query,
            parsed.fragment or "",
        )
    )
    return normalized


def resolve_database_uri(candidate: Optional[str] = None) -> str:
    """
    decide on the best database URI to use.
    """
    uri = candidate or os.getenv("DATABASE_URL")
    if uri:
        if uri.startswith(_SQLITE_PREFIX):
            raw_path = uri[len(_SQLITE_PREFIX) :]
            path = Path(raw_path)
            if not path.is_absolute():
                path = (_PROJECT_ROOT / path).resolve()
            usable = _ensure_sqlite_path(path)
            if usable:
                return _sqlite_uri_for(usable)
            print(f"[db] warning: falling back to temporary sqlite storage for {path}")
            return _fallback_sqlite_uri()

        # normalize postgres URIs (Neon etc.)
        parsed_scheme = urlparse(uri).scheme.lower()
        if parsed_scheme in _POSTGRES_SCHEMES:
            return _normalize_postgres_uri(uri)

        # non-sqlite DBs (MySQL, etc.) are returned as-is.
        return uri

    # no DATABASE_URL provided – mimic the legacy behaviour.
    instance_path = (_PROJECT_ROOT / "instance" / _DEFAULT_SQLITE_NAME).resolve()
    usable_instance = _ensure_sqlite_path(instance_path)
    if usable_instance:
        return _sqlite_uri_for(usable_instance)

    return _fallback_sqlite_uri()


def init_app(app):
    """attach SQLAlchemy to the flask app, supplying a usable URI."""
    db.init_app(app)


def reset_database(app):
    """drop and recreate all tables (for development)."""
    with app.app_context():
        db.drop_all()
        print("[db] database reset complete.")
