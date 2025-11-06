from flask import Flask
from flask_login import LoginManager
import os, sys, tempfile
from contextlib import suppress
from pathlib import Path

# ensure the project root (containing `webapp` and `shared`) is importable
_here = Path(__file__).resolve()
_project_root = _here.parent.parent
_root_str = str(_project_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

from shared.db import db
from shared.mail import mail

_app_instance = None
_DEFAULT_SQLITE_NAME = "app.db"


def _directory_is_writable(directory: Path) -> bool:
    """return True if we can create and remove a sentinel file in `directory`."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[db] could not ensure directory {directory}: {exc}")
        return False

    probe = directory / ".write_check"
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        probe.unlink()
        return True
    except OSError as exc:
        print(f"[db] directory {directory} is not writable: {exc}")
        with suppress(FileNotFoundError):
            probe.unlink()
        return False


def _sqlite_uri_for(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _resolve_database_uri() -> str:
    env_uri = os.getenv("DATABASE_URL")
    if env_uri:
        if env_uri.startswith("sqlite:///"):
            raw_path = env_uri[len("sqlite:///") :]
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = (_project_root / candidate).resolve()

            if _directory_is_writable(candidate.parent):
                return _sqlite_uri_for(candidate)

            print(f"[db] configured sqlite path {candidate} is not writable; falling back to tmp storage.")
        else:
            return env_uri

    instance_dir = _project_root / "instance"
    if _directory_is_writable(instance_dir):
        return _sqlite_uri_for((instance_dir / _DEFAULT_SQLITE_NAME).resolve())

    tmp_dir = Path(tempfile.gettempdir())
    if _directory_is_writable(tmp_dir):
        fallback = (tmp_dir / _DEFAULT_SQLITE_NAME).resolve()
        print(f"[db] using temporary sqlite database at {fallback}")
        return _sqlite_uri_for(fallback)

    raise RuntimeError("no writable location available for sqlite database.")


def create_app():
    global _app_instance
    if _app_instance is not None:
        return _app_instance

    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()

    db.init_app(app)
    mail.init_app(app)

    from .models import User, Paper, UserPreference, Subscriber, Feedback

    login_manager = LoginManager()
    login_manager.login_view = "frontend.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_email):
        return User.query.filter_by(email=user_email).first()

    from .routes_frontend import frontend
    from .routes_backend import backend
    app.register_blueprint(frontend)
    app.register_blueprint(backend, url_prefix="/api")

    with app.app_context():
        db.create_all()

    _app_instance = app
    return app
