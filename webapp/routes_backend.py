from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime
from flask_login import LoginManager, login_user, logout_user, login_required
import os, yaml, feedparser, urllib.parse
from dotenv import load_dotenv

# load .env from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from .models import db, User, Paper, UserPreference
from .routes_frontend import frontend
from ..mailer import send_email

# ==========================================================
# flask app initialization
# ==========================================================
app = Flask(__name__)
CORS(app)

# database configuration
if os.name == "nt":  # windows local
    db_path = os.path.join(os.path.dirname(__file__), "feedback.db")
else:  # linux (vercel, render, etc.)
    db_path = os.path.join("/tmp", "feedback.db")

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "supersecret"

db.init_app(app)
app.register_blueprint(frontend)

with app.app_context():
    db.create_all()

# ==========================================================
# flask login setup
# ==========================================================
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==========================================================
# backend / api routes
# ==========================================================

# ----------------------------------------------------------
# status / health check
# ----------------------------------------------------------
@app.route("/status")
def status():
    """health check endpoint for uptime and monitoring."""
    return jsonify({"status": "ok", "message": "astro-ph digest backend is live!"})


# ----------------------------------------------------------
# login / logout (simple demo placeholder)
# ----------------------------------------------------------
@app.route("/login")
def login():
    """temporary login endpoint (auto logs in first user)."""
    user = User.query.first()
    if not user:
        user = User(email="ajdavis25@gmail.com")
        db.session.add(user)
        db.session.commit()
    login_user(user)
    return jsonify({"status": "success", "message": f"logged in as {user.email}"})


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"status": "success", "message": "logged out"})


# ----------------------------------------------------------
# record like/dislike for papers
# ----------------------------------------------------------
@app.route("/like", methods=["POST"])
def like():
    data = request.get_json(force=True)
    email = data.get("email")
    arxiv_id = data.get("arxiv_id")
    liked = data.get("liked", True)

    if not email or not arxiv_id:
        return jsonify({"error": "missing email or arxiv_id"}), 400

    user = User.query.filter_by(email=email.lower()).first()
    if not user:
        user = User(email=email.lower())
        db.session.add(user)
        db.session.commit()

    paper = Paper.query.filter_by(arxiv_id=arxiv_id).first()
    if not paper:
        paper = Paper(arxiv_id=arxiv_id, link=f"https://arxiv.org/abs/{arxiv_id}")
        db.session.add(paper)
        db.session.commit()

    pref = UserPreference.query.filter_by(user_id=user.id, paper_id=paper.id).first()
    if pref:
        pref.liked = liked
        pref.created_at = datetime.utcnow()
    else:
        pref = UserPreference(user_id=user.id, paper_id=paper.id, liked=liked)
        db.session.add(pref)

    db.session.commit()
    return jsonify({"message": f"recorded {'like' if liked else 'dislike'} for {arxiv_id} by {email}"})


# ----------------------------------------------------------
# api: save / load preferences (yaml)
# ----------------------------------------------------------
@app.route("/api/preferences", methods=["POST"])
def save_preferences():
    data = request.get_json(force=True)
    prefs_path = os.path.join(os.path.dirname(__file__), "user_prefs.yaml")

    try:
        with open(prefs_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        print("[astro-ph bot] saved preferences:", data)
        return jsonify({"message": "preferences saved successfully!"})
    except Exception as e:
        print(f"[astro-ph bot] error saving preferences: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/preferences", methods=["GET"])
def get_preferences():
    prefs_path = os.path.join(os.path.dirname(__file__), "user_prefs.yaml")

    if not os.path.exists(prefs_path):
        return jsonify({"exists": False})

    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return jsonify({"exists": True, "data": data})
    except Exception as e:
        print(f"[astro-ph bot] error loading preferences: {e}")
        return jsonify({"exists": False, "error": str(e)}), 500


# ----------------------------------------------------------
# user feedback (json -> email + text log)
# ----------------------------------------------------------
@app.route("/send-feedback", methods=["GET", "POST"])
def user_feedback():
    """display feedback form (get) and handle feedback submission (post)."""
    if request.method == "GET":
        return render_template("feedback_form.html")

    # --- post: handle submission ---
    data = request.get_json(force=True)
    name = data.get("name", "Anonymous")
    email = data.get("email", "")
    message = data.get("message", "")

    if not message.strip():
        return jsonify({"status": "error", "message": "message cannot be empty"}), 400

    # save locally
    log_path = os.path.join(os.path.dirname(__file__), "user_feedback.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.utcnow()}] {name} <{email}>: {message}\n")

    print(f"[astro-ph bot] feedback from {name}: {message}")

    # send notification email (using your config + mailer.py)
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        subject = f"[astro-ph feedback] new message from {name}"
        text_body = f"from: {name} <{email}>\n\n{message}"
        html_body = f"<p><strong>from:</strong> {name} &lt;{email}&gt;</p><p>{message}</p>"

        send_email(
            cfg,
            subject,
            text_body,
            html_body,
            to_override=[cfg["output"]["email"]["from_addr"]]  # force send feedback only to bot
        )
        print("[mailer] feedback notification sent")

        return jsonify({"status": "success", "message": "thank you for your feedback!"})

    except Exception as e:
        print(f"[mailer] error sending feedback email: {e}")
        return jsonify({"status": "error", "message": f"error sending feedback: {e}"})


# ----------------------------------------------------------
# recommendations api (live arXiv fetch)
# ----------------------------------------------------------
@app.route("/recommendations")
def recommendations():
    """fetch related arXiv papers based on saved keywords."""
    prefs_path = os.path.join(os.path.dirname(__file__), "user_prefs.yaml")
    if not os.path.exists(prefs_path):
        return render_template("recommendations.html", recs=[], message="no preferences found yet.")

    with open(prefs_path, "r", encoding="utf-8") as f:
        prefs = yaml.safe_load(f) or {}

    keywords = prefs.get("keywords", [])
    if not keywords:
        return render_template("recommendations.html", recs=[], message="no keywords set in preferences.")

    # build query safely with proper url encoding
    encoded_terms = [urllib.parse.quote_plus(kw.strip()) for kw in keywords if kw.strip()]
    query = " OR ".join([f"all:{term}" for term in encoded_terms])

    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": "5",
    }

    url = f"https://export.arxiv.org/api/query?{urllib.parse.urlencode(params)}"
    print("[recommendations] fetching:", url)

    try:
        feed = feedparser.parse(url)
        recs = [
            {
                "title": entry.title,
                "link": entry.link,
                "summary": entry.summary,
                "published": entry.published,
            }
            for entry in feed.entries[:5]
        ]
    except Exception as e:
        print("[recommendations] error:", e)
        recs = []

    message = (
        "no new papers found matching your preferences."
        if not recs
        else f"showing {len(recs)} latest papers matching your interests."
    )
    return render_template("recommendations.html", recs=recs, message=message)


# ----------------------------------------------------------
# recommendation feedback api
# ----------------------------------------------------------
@app.route("/api/recommendation-feedback", methods=["POST"])
def recommendation_feedback():
    """record like/dislike feedback for recommended papers."""
    data = request.get_json(force=True)
    title = data.get("title")
    reaction = data.get("reaction")

    if not title or reaction not in ["like", "dislike"]:
        return jsonify({"error": "invalid input"}), 400

    log_path = os.path.join(os.path.dirname(__file__), "recommendation_feedback.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.utcnow()}] {reaction.upper()} — {title}\n")

    print(f"[recommendation-feedback] {reaction} recorded for '{title}'")
    return jsonify({"message": f"recorded {reaction} for {title}"})


# ==========================================================
# run locally
# ==========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
