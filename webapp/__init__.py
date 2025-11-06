from flask import Flask
from flask_login import LoginManager
import os, sys
from pathlib import Path

# ensure the project root (containing `webapp` and `shared`) is importable
_here = Path(__file__).resolve()
_project_root = _here.parent.parent
_root_str = str(_project_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

from shared.db import db, init_app as init_db
from shared.mail import mail

_app_instance = None


def create_app():
    global _app_instance
    if _app_instance is not None:
        return _app_instance

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    # allow explicit configuration while letting shared.db supply safe defaults
    app.config.setdefault("SQLALCHEMY_DATABASE_URI", os.getenv("DATABASE_URL"))
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    init_db(app)
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
