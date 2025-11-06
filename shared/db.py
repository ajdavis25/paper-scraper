# shared/db.py
"""
shared/db.py — database initialization and utility functions
"""
import os
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()  # define db here (not imported from webapp)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "feedback.db")


def init_app(app):
    """attach sqlalchemy to a flask app."""
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)


def reset_database(app):
    """drop and recreate all tables (for development)."""
    with app.app_context():
        db.drop_all()
        print("[db] database reset complete.")
