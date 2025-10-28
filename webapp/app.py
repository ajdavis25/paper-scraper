import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from .models import db, User, Paper, UserPreference
from datetime import datetime

BASE_URL = os.getenv("VERCEL_URL", "http://localhost:5000")

def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///../database.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    CORS(app)
    db.init_app(app)

    @app.route("/")
    def index():
        return jsonify({"status": "astro-ph recommender online"})

    @app.route("/like", methods=["GET", "POST"])
    def like():
        """record a like/dislike click from the email link or JSON request"""
        if request.method == "GET":
            data = request.args
        else:
            data = request.json

        email = data.get("email")
        arxiv_id = data.get("arxiv_id")
        title = data.get("title", "")
        abstract = data.get("abstract", "")
        link = data.get("link", "")
        liked = str(data.get("liked", "true")).lower() in ["1", "true", "yes"]

        if not (email and arxiv_id):
            return jsonify({"error": "missing email or arxiv_id"}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email)
            db.session.add(user)

        paper = Paper.query.filter_by(arxiv_id=arxiv_id).first()
        if not paper:
            paper = Paper(arxiv_id=arxiv_id, title=title, abstract=abstract, link=link)
            db.session.add(paper)

        pref = UserPreference(user=user, paper=paper, liked=liked)
        db.session.add(pref)
        db.session.commit()

        print(f"[LOG] {email} {'liked' if liked else 'disliked'} {arxiv_id}")
        return jsonify({"status": "ok"})

    @app.route("/dashboard")
    def dashboard():
        """simple HTML dashboard showing liked papers"""
        email = request.args.get("email")
        if not email:
            return "Missing ?email= parameter", 400
        user = User.query.filter_by(email=email).first()
        if not user:
            return f"No records for {email}", 404
        prefs = UserPreference.query.filter_by(user_id=user.id, liked=True).join(Paper).all()
        return render_template("dashboard.html", user=user, prefs=prefs)

    return app

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
