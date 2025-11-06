# shared/db.py
"""
database initialization helpers and uri resolution.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_NAME = "app.db"


def _sqlite_uri_for(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def resolve_database_uri(candidate: Optional[str] = None) -> str:
    """
    determine a usable sqlalchemy database uri.

    Order of precedence:
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
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(f"[db] warning: cannot prepare sqlite directory {path.parent}: {exc}; using tmp storage.")
                tmp_path = (Path(tempfile.gettempdir()) / _DEFAULT_SQLITE_NAME).resolve()
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                return _sqlite_uri_for(tmp_path)
            return _sqlite_uri_for(path)
        return uri

    instance_path = (_PROJECT_ROOT / "instance" / _DEFAULT_SQLITE_NAME).resolve()
    try:
        instance_path.parent.mkdir(parents=True, exist_ok=True)
        return _sqlite_uri_for(instance_path)
    except OSError as exc:
        print(f"[db] warning: cannot write to instance directory ({instance_path.parent}): {exc}")
        tmp_path = (Path(tempfile.gettempdir()) / _DEFAULT_SQLITE_NAME).resolve()
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[db] using temporary sqlite database at {tmp_path}")
        return _sqlite_uri_for(tmp_path)


def init_app(app):
    """attach sqlalchemy to the flask app, supplying a writable uri when needed."""
    resolved = resolve_database_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
    app.config["SQLALCHEMY_DATABASE_URI"] = resolved
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    db.init_app(app)


def reset_database(app):
    """drop and recreate all tables (for development)."""
    with app.app_context():
        db.drop_all()
        print("[db] database reset complete.")
