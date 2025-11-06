# shared/db.py
"""
database initialization helpers and uri resolution.
"""
import os
import sqlite3
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Optional
from flask_sqlalchemy import SQLAlchemy


class ConfiguredSQLAlchemy(SQLAlchemy):
    def init_app(self, app):
        uri = resolve_database_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
        app.config["SQLALCHEMY_DATABASE_URI"] = uri
        app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
        super().init_app(app)


db = ConfiguredSQLAlchemy()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_NAME = "feedback.db"


def _sqlite_uri_for(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _ensure_sqlite_writable(path: Path) -> bool:
    """
    attempt to create/open a sqlite database at `path` and perform a small write.
    returns True on success, False if the location is not writable.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[db] warning: cannot create directories for {path}: {exc}")
        return False

    try:
        conn = sqlite3.connect(path.as_posix())
        try:
            conn.execute("PRAGMA user_version = 1;")
            conn.commit()
        finally:
            conn.close()
        return True
    except sqlite3.OperationalError as exc:
        print(f"[db] warning: sqlite path {path} not writable: {exc}")
        with suppress(FileNotFoundError):
            path.unlink()
        return False
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[db] warning: unexpected error validating sqlite path {path}: {exc}")
        with suppress(FileNotFoundError):
            path.unlink()
        return False


def resolve_database_uri(candidate: Optional[str] = None) -> str:
    """
    determine a usable sqlalchemy database uri.

    order of precedence:
      1. explicit `candidate` argument (e.g. from app.config), normalized.
      2. `DATABASE_URL` environment variable, normalized.
      3. project `instance/app.db` if writable.
      4. `tempfile.gettempdir()`/app.db as a last resort.
    """
    uri = candidate or os.getenv("DATABASE_URL")
    if uri:
        if uri.startswith("sqlite:///"):
            raw_path = uri[len("sqlite:///") :]
            path = Path(raw_path)
            if not path.is_absolute():
                path = (_PROJECT_ROOT / path).resolve()
            if _ensure_sqlite_writable(path):
                return _sqlite_uri_for(path)
            print(f"[db] warning: falling back to temporary sqlite storage for {path}")
            tmp_path = (Path(tempfile.gettempdir()) / _DEFAULT_SQLITE_NAME).resolve()
            if not _ensure_sqlite_writable(tmp_path):
                raise RuntimeError("cannot obtain a writable sqlite database location.")
            return _sqlite_uri_for(tmp_path)
        return uri

    instance_path = (_PROJECT_ROOT / "instance" / _DEFAULT_SQLITE_NAME).resolve()
    if _ensure_sqlite_writable(instance_path):
        return _sqlite_uri_for(instance_path)

    tmp_path = (Path(tempfile.gettempdir()) / _DEFAULT_SQLITE_NAME).resolve()
    if not _ensure_sqlite_writable(tmp_path):
        raise RuntimeError("cannot obtain a writable sqlite database location.")
    print(f"[db] using temporary sqlite database at {tmp_path}")
    return _sqlite_uri_for(tmp_path)


def reset_database(app):
    """drop and recreate all tables (for development)."""
    with app.app_context():
        db.drop_all()
        print("[db] database reset complete.")
