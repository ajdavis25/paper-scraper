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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_NAME = "feedback.db"


def _sqlite_uri_for(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _usable_sqlite_path(path: Path) -> Optional[Path]:
    """
    ensure a sqlite database can be created at `path`.
    returns the path on success, otherwise None.
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
        print(f"[db] warning: sqlite path {path} not writable: {exc}")
        with suppress(FileNotFoundError):
            path.unlink()
        return None
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[db] warning: unexpected sqlite error at {path}: {exc}")
        with suppress(FileNotFoundError):
            path.unlink()
        return None


def resolve_database_uri(candidate: Optional[str] = None) -> str:
    """
    determine a usable sqlalchemy database uri, preferring configured values and
    falling back to a writable temporary sqlite file.
    """
    uri = candidate or os.getenv("DATABASE_URL")
    if uri:
        if uri.startswith("sqlite:///"):
            raw_path = uri[len("sqlite:///") :]
            path = Path(raw_path)
            if not path.is_absolute():
                path = (_PROJECT_ROOT / path).resolve()
            usable = _usable_sqlite_path(path)
            if usable:
                return _sqlite_uri_for(usable)
            print(f"[db] warning: falling back to temporary sqlite storage for {path}")
            tmp_path = (Path(tempfile.gettempdir()) / _DEFAULT_SQLITE_NAME).resolve()
            usable_tmp = _usable_sqlite_path(tmp_path)
            if not usable_tmp:
                raise RuntimeError("cannot obtain a writable sqlite database location.")
            return _sqlite_uri_for(usable_tmp)
        return uri

    instance_path = (_PROJECT_ROOT / "instance" / _DEFAULT_SQLITE_NAME).resolve()
    usable_instance = _usable_sqlite_path(instance_path)
    if usable_instance:
        return _sqlite_uri_for(usable_instance)

    tmp_path = (Path(tempfile.gettempdir()) / _DEFAULT_SQLITE_NAME).resolve()
    usable_tmp = _usable_sqlite_path(tmp_path)
    if not usable_tmp:
        raise RuntimeError("cannot obtain a writable sqlite database location.")
    print(f"[db] using temporary sqlite database at {tmp_path}")
    return _sqlite_uri_for(usable_tmp)


class ConfiguredSQLAlchemy(SQLAlchemy):
    def init_app(self, app):
        uri = resolve_database_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
        app.config["SQLALCHEMY_DATABASE_URI"] = uri
        app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
        super().init_app(app)


db = ConfiguredSQLAlchemy()


def init_app(app):
    """compat wrapper in case modules import shared.db.init_app directly."""
    db.init_app(app)


def reset_database(app):
    """drop and recreate all tables (for development)."""
    with app.app_context():
        db.drop_all()
        print("[db] database reset complete.")
