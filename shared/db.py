# shared/db.py
"""
shared/db.py - database initialization and utility functions
"""
from pathlib import Path
import tempfile
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()  # define db here (not imported from webapp)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_NAME = "app.db"


def _default_sqlite_uri() -> str:
    instance_dir = _PROJECT_ROOT / "instance"
    try:
        instance_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(instance_dir / _DEFAULT_SQLITE_NAME).resolve().as_posix()}"
    except OSError:
        tmp_dir = Path(tempfile.gettempdir())
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fallback = (tmp_dir / _DEFAULT_SQLITE_NAME).resolve()
        print(f"[db] falling back to temporary sqlite database at {fallback}")
        return f"sqlite:///{fallback.as_posix()}"


def init_app(app):
    """attach sqlalchemy to the flask app without overriding explicit config."""
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = _default_sqlite_uri()
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    db.init_app(app)


def reset_database(app):
    """drop and recreate all tables (for development)."""
    with app.app_context():
        db.drop_all()
        print("[db] database reset complete.")
