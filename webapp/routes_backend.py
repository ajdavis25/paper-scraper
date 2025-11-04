#!/usr/bin/env python3
"""
routes_backend.py — backend routes for astro-ph digest
"""
import os, sys
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_login import LoginManager
from dotenv import load_dotenv

# make project root importable
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from shared.db import db, init_app
from shared.mail import send_email
from webapp.models import User
from webapp.routes_frontend import frontend

app = Flask(__name__)
CORS(app)
init_app(app)
with app.app_context():
    db.create_all()
app.register_blueprint(frontend)

# flask-login setup
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==========================================================
# home
# ==========================================================
@app.route("/")
def index():
    return render_template("index.html")


# ==========================================================
# send feedback (contact form)
# ==========================================================
@app.route("/send-feedback", methods=["GET", "POST"])
def user_feedback():
    """receives user feedback and emails it to the bot address."""
    if request.method == "GET":
        return render_template("feedback_form.html")

    import yaml
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400

    name = (data.get("name") or "anonymous").strip()
    email = (data.get("email") or "anonymous@local").strip()
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message cannot be empty"}), 400

    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[send-feedback] yaml error: {e}")
        cfg = {}

    subject = f"[astro-ph feedback] from {name}"
    text = f"{name} <{email}> wrote:\n\n{message}"
    html = f"<p><strong>{name}</strong> &lt;{email}&gt;</p><p>{message}</p>"

    if not send_email(cfg, subject, text, html):
        print("[send-feedback] mail send failed")
        return jsonify({"error": "mail failed"}), 500

    print(f"[send-feedback] feedback email sent from {email}")
    return jsonify({"message": "feedback sent!"})


# ==========================================================
# recommendations page
# ==========================================================
@app.route("/recommendations")
def recommendations():
    """render recommendations using saved keywords."""
    import yaml
    from shared.utils import build_arxiv_query, fetch_arxiv_feed

    prefs_path = os.path.join(os.path.dirname(__file__), "user_prefs.yaml")
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            prefs = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[recommendations] error reading prefs: {e}")
        prefs = {}

    keywords = prefs.get("keywords") or []
    if not keywords:
        return render_template("recommendations.html", recs=[], message="no keywords found in preferences.")

    url = build_arxiv_query(keywords, max_results=5)
    print(f"[recommendations] fetching: {url}")

    try:
        recs = fetch_arxiv_feed(url)
        msg = f"showing {len(recs)} recent papers matching your interests."
    except Exception as e:
        print(f"[recommendations] error fetching arxiv: {e}")
        recs, msg = [], "error fetching arXiv feed."

    return render_template("recommendations.html", recs=recs, message=msg)


# ==========================================================
# record recommendation feedback (like/dislike)
# ==========================================================
@app.route("/api/recommendation-feedback", methods=["POST"])
def recommendation_feedback():
    """store user reaction to a recommendation."""
    import json, time
    data = request.get_json(force=True)
    link = data.get("link", "").strip()
    # normalize: remove arxiv.org prefix if present
    if "arxiv.org" in link:
        link = link.split("arxiv.org/abs/")[-1].strip("/")
    record = {
        "email": "anonymous",
        "arxiv_id": link,
        "liked": data.get("reaction"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "source": "recommendations"
    }

    feedback_path = os.path.join(os.path.dirname(__file__), "feedback.json")
    try:
        # append to existing list
        if os.path.exists(feedback_path):
            with open(feedback_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        else:
            entries = []
        entries.insert(0, record)
        with open(feedback_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
    except Exception as e:
        print(f"[recommendation-feedback] error saving feedback: {e}")

    return jsonify({"status": "ok"})


# ==========================================================
# user preferences api (for dashboard)
# ==========================================================
@app.route("/api/preferences", methods=["GET", "POST"])
def api_preferences():
    """get or save user preferences."""
    import yaml
    prefs_path = os.path.join(os.path.dirname(__file__), "user_prefs.yaml")

    if request.method == "GET":
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = yaml.safe_load(f) or {}
            return jsonify(prefs)
        except Exception as e:
            print(f"[api/preferences] error loading prefs: {e}")
            return jsonify({})
    else:
        data = request.get_json(force=True)
        try:
            with open(prefs_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False)
            print("[api/preferences] preferences saved:", data)
            return jsonify({"status": "ok"})
        except Exception as e:
            print(f"[api/preferences] error saving prefs: {e}")
            return jsonify({"error": str(e)}), 500


# ==========================================================
# feedback viewer (admin)
# ==========================================================
@app.route("/feedback", methods=["GET"])
def feedback_entries():
    """
    return recent like/dislike feedback as json for the user feedback table.
    works even if database missing — will fall back to empty list.
    """
    try:
        # if you’re using a db:
        # entries = Feedback.query.order_by(Feedback.timestamp.desc()).limit(100).all()
        # data = [e.as_dict() for e in entries]

        # fallback: check for local feedback.json file
        import json, os
        feedback_path = os.path.join(os.path.dirname(__file__), "feedback.json")
        if os.path.exists(feedback_path):
            with open(feedback_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []

        return jsonify(data)
    except Exception as e:
        print(f"[feedback] error loading entries: {e}")
        return jsonify([])


# ==========================================================
# main entry (for local run)
# ==========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
