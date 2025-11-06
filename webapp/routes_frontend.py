#!/usr/bin/env python3
from flask import Blueprint, render_template, request, jsonify, abort, redirect, url_for, flash, session
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import SignatureExpired, BadSignature

from shared.db import db
from webapp.models import User, Paper, UserPreference, Subscriber, Feedback, PreferenceConfig
from shared.utils import get_user_by_email
from shared.mail import send_reset_email, get_serializer, send_email
import os

frontend = Blueprint("frontend", __name__)


@frontend.route("/")
def index():
    return render_template("index.html", user=current_user)


@frontend.route("/login", methods=["GET", "POST"])
def login():
    """user login (html form or json)."""
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or request.form
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""

            if not email or not password:
                flash("please enter both email and password.", "error")
                return redirect(url_for("frontend.login"))

            user = get_user_by_email(email)
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                session["is_admin"] = bool(user.is_admin)
                flash("logged in successfully.", "success")
                return redirect(url_for("frontend.index"))
            else:
                flash("invalid email or password.", "error")
                return redirect(url_for("frontend.login"))

        return render_template("login.html")
    except Exception as e:
        print(f"[login] error: {e}")
        return jsonify({"error": str(e)}), 500


@frontend.route("/logout")
def logout():
    session.pop("is_admin", None)
    logout_user()
    return redirect("/")


@frontend.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return jsonify({"status": "error", "message": "please enter a valid email."}), 400

        try:
            user_exists = User.query.filter(
                db.func.lower(User.email) == email
            ).first()
            if user_exists:
                return jsonify({"status": "info", "message": "already subscribed!"})

            existing = Subscriber.query.filter(
                db.func.lower(Subscriber.email) == email
            ).first()
            if existing:
                return jsonify({"status": "info", "message": "already subscribed!"})

            new_sub = Subscriber(email=email)
            db.session.add(new_sub)
            db.session.commit()
            return jsonify({"status": "success", "message": "subscribed successfully!"})
        except Exception as e:
            print(f"[subscribe] error: {e}")
            db.session.rollback()
            return jsonify({"status": "error", "message": f"server error: {e}"}), 500

    return render_template("subscribe.html")


@frontend.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return jsonify({"status": "error", "message": "please enter a valid email."}), 400

        try:
            sub = Subscriber.query.filter_by(email=email).first()
            if not sub:
                return jsonify({"status": "info", "message": "email not found — you may already be unsubscribed."})

            db.session.delete(sub)
            db.session.commit()
            print(f"[unsubscribe] removed {email}")
            return jsonify({"status": "success", "message": "you’ve been unsubscribed. farewell!"})
        except Exception as e:
            print(f"[unsubscribe] error: {e}")
            db.session.rollback()
            return jsonify({"status": "error", "message": "server error"}), 500

    return render_template("unsubscribe.html")


@frontend.route("/preferences")
def preferences_page():
    return render_template("preferences.html")


@frontend.route("/dashboard")
@login_required
def dashboard_redirect():
    """redirect /dashboard → /dashboard/<email> if logged in."""
    return redirect(url_for("frontend.dashboard", email=current_user.email))


@frontend.route("/dashboard/<email>")
def dashboard(email):
    user = User.query.filter_by(email=email.lower()).first()
    if not user:
        return render_template("dashboard.html", user={"email": email}, prefs=[], message="no user found.")

    liked_prefs = (
        UserPreference.query.filter_by(user_id=user.id, liked=True)
        .join(Paper)
        .order_by(UserPreference.created_at.desc())
        .all()
    )

    prefs = [
        {
            "paper": {
                "title": p.paper.title or f"arXiv:{p.paper.arxiv_id}",
                "link": p.paper.link or f"https://arxiv.org/abs/{p.paper.arxiv_id}",
                "arxiv_id": p.paper.arxiv_id,
            },
            "timestamp": p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for p in liked_prefs
    ]

    message = "read anything super yet?" if not prefs else None
    return render_template("dashboard.html", user={"email": email}, prefs=prefs, message=message)


@frontend.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        # check if user already exists
        if User.query.filter_by(email=email).first():
            flash("user already exists. try logging in instead.")
            return redirect(url_for("frontend.login"))

        # hash and store the password
        hashed_pw = generate_password_hash(password)
        new_user = User(email=email, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()

        flash("signup successful! you can now log in.")
        return redirect(url_for("frontend.login"))

    return render_template("signup.html")


@frontend.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = get_user_by_email(email)

        if user:
            token = get_serializer().dumps(email, salt="password-reset")
            reset_url = url_for("frontend.reset_password", token=token, _external=True)
            send_reset_email(user.email, reset_url)
            flash("reset link sent to your email.")
        else:
            flash("no account found with that email.")
        return redirect(url_for("frontend.login"))

    return render_template("forgot_password.html")


@frontend.route("/forgot-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = get_serializer().loads(token, salt="password-reset", max_age=3600)
    except SignatureExpired:
        flash("reset link expired.")
        return redirect(url_for("frontend.forgot_password"))
    except BadSignature:
        flash("invalid reset token.")
        return redirect(url_for("frontend.forgot_password"))

    user = get_user_by_email(email)
    if not user:
        flash("user not found.")
        return redirect(url_for("frontend.forgot_password"))

    if request.method == "POST":
        new_password = request.form["password"]
        hashed_pw = generate_password_hash(new_password)

        user.password_hash = hashed_pw
        db.session.commit()

        flash("password reset successful. you can now log in.")
        return redirect(url_for("frontend.login"))

    return render_template("reset_password.html", email=email)


# ----------------------------------------------------------
# send feedback (contact form)
# ----------------------------------------------------------
@frontend.route("/send-feedback", methods=["GET", "POST"])
def user_feedback():
    """receives user feedback, stores it in the database, and emails it to the bot."""
    import yaml

    if request.method == "GET":
        return render_template("feedback_form.html")

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400

    name = (data.get("name") or "anonymous").strip()
    email = (data.get("email") or "anonymous@local").strip()
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message cannot be empty"}), 400

    # save to db first
    fb = Feedback(name=name, email=email, message=message, type="contact")
    try:
        db.session.add(fb)
        db.session.commit()
        print(f"[feedback] stored feedback from {email}")
    except Exception as e:
        print(f"[feedback] db save error: {e}")
        db.session.rollback()

    # try to load mail config
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[send-feedback] yaml error: {e}")
        cfg = {}

    # compose email
    subject = f"[astro-ph feedback] from {name}"
    text = f"{name} <{email}> wrote:\n\n{message}"
    html = f"<p><strong>{name}</strong> &lt;{email}&gt;</p><p>{message}</p>"

    # send mail
    if not send_email(cfg, subject, text, html):
        print("[send-feedback] mail send failed")
        # still return success since it was saved in db
        return jsonify({"message": "feedback stored but email failed"}), 202

    print(f"[send-feedback] feedback email sent from {email}")
    return jsonify({"message": "feedback sent!"}), 200


# ----------------------------------------------------------
# recommendations page
# ----------------------------------------------------------
@frontend.route("/recommendations")
def recommendations():
    """
    render personalized arXiv recommendations using saved preferences,
    capped at 10 total results and showing the category of origin.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from urllib.parse import quote_plus
    from shared.utils import fetch_arxiv_feed

    # load preferences
    try:
        config = PreferenceConfig.query.first()
        if config is None:
            config = PreferenceConfig()
            db.session.add(config)
            db.session.commit()
        prefs = config.as_dict()
    except SQLAlchemyError as e:
        print(f"[recommendations] db error loading prefs: {e}")
        prefs = {"keywords": [], "categories": ["astro-ph"], "min_score": 1.0}

    keywords = prefs.get("keywords") or []
    categories = prefs.get("categories") or ["astro-ph"]
    min_score = prefs.get("min_score", 1.0) or 1.0

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


# ----------------------------------------------------------
# record recommendation feedback (like/dislike)
# ----------------------------------------------------------
@frontend.route("/api/recommendation-feedback", methods=["POST"])
def recommendation_feedback():
    """store recommendation reactions directly in the database."""
    from datetime import datetime

    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    link = (data.get("link") or "").strip()
    liked = bool(data.get("reaction", True))

    if not email or not link:
        return jsonify({"error": "missing email or link"}), 400

    # normalize arxiv id
    arxiv_id = link.split("arxiv.org/abs/")[-1].strip()

    # find or create user
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, password_hash="")
        db.session.add(user)
        db.session.commit()

    # find or create paper
    paper = Paper.query.filter_by(arxiv_id=arxiv_id).first()
    if not paper:
        paper = Paper(arxiv_id=arxiv_id, title="", link=f"https://arxiv.org/abs/{arxiv_id}")
        db.session.add(paper)
        db.session.commit()

    # update or insert preference
    pref = UserPreference.query.filter_by(user_id=user.id, paper_id=paper.id).first()
    if not pref:
        pref = UserPreference(user_id=user.id, paper_id=paper.id, liked=liked)
        db.session.add(pref)
    else:
        pref.liked = liked

    db.session.commit()
    print(f"[recommendation-feedback] saved like={liked} for {arxiv_id} ({email})")

    # also store in feedback table for admin viewing
    try:
        fb_entry = Feedback(
            name="system",
            email=email,
            message=f"reaction {'like' if liked else 'dislike'} for {arxiv_id}",
            type="recommendation"
        )
        db.session.add(fb_entry)
        db.session.commit()
    except Exception as e:
        print(f"[recommendation-feedback] failed to log in feedback: {e}")
        db.session.rollback()

    return jsonify({"status": "ok"})


# ----------------------------------------------------------
# view feedback (admin-only page)
# ----------------------------------------------------------
@frontend.route("/view-feedback", methods=["GET"])
@login_required
def view_feedback_page():
    """show recorded likes/dislikes from UserPreference joined with paper & user."""
    if not current_user.is_admin:
        abort(403)

    # pull from the canonical source of truth: UserPreference <=> Paper <=> User
    rows = (
        db.session.query(
            User.email.label("email"),
            Paper.arxiv_id.label("arxiv_id"),
            UserPreference.liked.label("liked"),
            UserPreference.created_at.label("timestamp"),
        )
        .join(UserPreference, UserPreference.user_id == User.id)
        .join(Paper, UserPreference.paper_id == Paper.id)
        .order_by(UserPreference.created_at.desc())
        .limit(200)
        .all()
    )

    feedback = [
        {
            "email": r.email,
            "arxiv_id": r.arxiv_id,                                 # now a real id like "0812.0365v1"
            "liked": bool(r.liked),                                 # True/False -> ✓/✗ in template
            "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M"),
            "source": "recommendations",
        }
        for r in rows
    ]

    return render_template("feedback.html", feedback=feedback)


# ----------------------------------------------------------
# info page
# ----------------------------------------------------------
@frontend.route("/info")
def info_page():
    """show information about the digest and usage."""
    sample_digest = [
        {
            "title": "probing dark matter substructure with lensed quasars",
            "category": "astro-ph.CO",
            "summary": "concise analysis of strong-lensing flux anomalies as subhalo probes.",
        },
        {
            "title": "machine-learning forecasts for gravitational-wave events",
            "category": "astro-ph.IM",
            "summary": "overview of a random-forest pipeline that predicts merger rates from detector telemetry.",
        },
        {
            "title": "turbulence-regulated star formation in molecular clouds",
            "category": "astro-ph.GA",
            "summary": "simulation-driven insight into how feedback preserves Larson-like scaling.",
        },
    ]
    return render_template("info.html", sample_digest=sample_digest)
