from flask import Flask
from flask_login import LoginManager
import os, sys
from pathlib import Path

# ensure the parent directory that holds the ``astroph_bot`` package is importable
_here = Path(__file__).resolve()
_package_root = _here.parents[1]          # .../astroph_bot
_package_parent = _package_root.parent    # directory that contains /astroph_bot

candidate = str(_package_parent)
if candidate not in sys.path:
    sys.path.insert(0, candidate)

from astroph_bot.shared.db import db
from astroph_bot.shared.mail import mail

_app_instance = None


def create_app():
    global _app_instance
    if _app_instance is not None:
        return _app_instance

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # initialize extensions first
    db.init_app(app)
    mail.init_app(app)

    # import models after initializing db
    from astroph_bot.webapp.models import User, Paper, UserPreference, Subscriber, Feedback

    login_manager = LoginManager()
    login_manager.login_view = "frontend.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_email):
        return User.query.filter_by(email=user_email).first()

    # register blueprints after models are imported
    from astroph_bot.webapp.routes_frontend import frontend
    from astroph_bot.webapp.routes_backend import backend
    app.register_blueprint(frontend)
    app.register_blueprint(backend, url_prefix="/api")

    with app.app_context():
        db.create_all()

    _app_instance = app
    return app
