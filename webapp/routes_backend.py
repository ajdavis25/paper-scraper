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
    """
    render personalized arXiv recommendations using saved preferences,
    capped at 10 total results and showing the category of origin.
    """
    import yaml
    from urllib.parse import quote_plus
    from shared.utils import fetch_arxiv_feed

    prefs_path = os.path.join(os.path.dirname(__file__), "user_prefs.yaml")

    # load preferences
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            prefs = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[recommendations] error reading prefs: {e}")
        prefs = {}

    keywords = prefs.get("keywords", [])
    categories = prefs.get("categories", ["astro-ph"])
    try:
        min_score = float(prefs.get("min_score", 1.0))
    except Exception:
        min_score = 1.0

    if not keywords:
        return render_template(
            "recommendations.html",
            recs=[],
            message="no keywords found in preferences. add some in your dashboard first!",
        )

    # build encoded keywords for search
    encoded_terms = [f'all:"{quote_plus(k.strip())}"' for k in keywords if k.strip()]
    if not encoded_terms:
        return render_template("recommendations.html", recs=[], message="no valid keywords provided.")

    all_recs = []
    for cat in categories:
        cat = cat.strip()
        if not cat:
            continue

        query = "+OR+".join(encoded_terms) + f"+AND+cat:{quote_plus(cat)}"
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query={query}&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending"
        )
        print(f"[recommendations] fetching from {cat}: {url}")

        try:
            recs = fetch_arxiv_feed(url)
            # tag category
            for r in recs:
                r["category"] = cat
            all_recs.extend(recs)
        except Exception as e:
            print(f"[recommendations] error fetching {cat}: {e}")

    # dedup by link
    dedup = {}
    for r in all_recs:
        link = r.get("link") or ""
        if link and link not in dedup:
            dedup[link] = r

    # scoring
    def relevance_score(paper):
        text = f"{paper.get('title','')} {paper.get('summary','')}".lower()
        score = 0
        for kw in keywords:
            kw_clean = kw.strip().lower()
            if kw_clean and kw_clean in text:
                score += 1
        return score

    scored = []
    for r in dedup.values():
        s = relevance_score(r)
        if s >= min_score:
            r["score"] = s
            scored.append(r)

    # sort by score and take only top 10 total
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    scored = scored[:10]

    msg = (
        f"showing {len(scored)} recent papers across {', '.join(categories)} "
        f"with score ≥ {min_score}."
        if scored else
        "no papers met your minimum relevance threshold."
    )

    return render_template("recommendations.html", recs=scored, message=msg)


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
            # ensure backward compatibility
            prefs.setdefault("keywords", [])
            prefs.setdefault("authors", [])
            prefs.setdefault("min_score", 1.0)
            prefs.setdefault("categories", ["astro-ph"])  # default field
            return jsonify(prefs)
        except Exception as e:
            print(f"[api/preferences] error loading prefs: {e}")
            return jsonify({})
    else:
        data = request.get_json(force=True)
        try:
            # normalize missing fields before saving
            prefs = {
                "keywords": data.get("keywords", []),
                "authors": data.get("authors", []),
                "min_score": data.get("min_score", 1.0),
                "categories": data.get("categories", ["astro-ph"])
            }

            with open(prefs_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(prefs, f, sort_keys=False)

            print("[api/preferences] preferences saved:", prefs)
            return jsonify({"status": "ok"})
        except Exception as e:
            print(f"[api/preferences] error saving prefs: {e}")
            return jsonify({"error": str(e)}), 500


# ==========================================================
# feedback viewer route (HTML + JSON modes)
# ==========================================================
@app.route("/feedback", methods=["GET"])
def feedback():
    """show or return all feedback entries (likes/dislikes)."""
    import sqlite3
    from flask import request

    db_path = os.path.join(os.path.dirname(__file__), "feedback.db")

    # if db missing, return empty set
    if not os.path.exists(db_path):
        if "application/json" in request.headers.get("accept", ""):
            return jsonify([])
        return render_template("feedback.html", feedback=[])
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM feedback ORDER BY timestamp DESC").fetchall()
        conn.close()

        entries = [dict(r) for r in rows]
    except Exception as e:
        print(f"[feedback] db error: {e}")
        entries = []

    # return json if requested by js fetch()
    if "application/json" in request.headers.get("accept", ""):
        return jsonify(entries)
    else:
        return render_template("feedback.html", feedback=entries)


# ==========================================================
# main entry (for local run)
# ==========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
