from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    preferences = db.relationship("UserPreference", back_populates="user")


class Paper(db.Model):
    __tablename__ = "paper"
    id = db.Column(db.Integer, primary_key=True)
    arxiv_id = db.Column(db.String, unique=True, nullable=False)
    title = db.Column(db.String)
    abstract = db.Column(db.Text)
    link = db.Column(db.String)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    preferences = db.relationship("UserPreference", back_populates="paper")


class UserPreference(db.Model):
    __tablename__ = "user_preference"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    paper_id = db.Column(db.Integer, db.ForeignKey("paper.id"))
    liked = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="preferences")
    paper = db.relationship("Paper", back_populates="preferences")
