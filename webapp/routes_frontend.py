from flask import Blueprint, Flask, render_template, request, jsonify
from flask_login import current_user
from .models import db, User, Paper, UserPreference
from shared.db import init_app

app = Flask(__name__)
init_app(app)

frontend = Blueprint("frontend", __name__)


# ----------------------------------------------------------
# homepage
# ----------------------------------------------------------
@frontend.route("/")
def index():
    return render_template("index.html", user=current_user)


# ----------------------------------------------------------
# subscribe
# ----------------------------------------------------------
@frontend.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    """handles user subscription to the daily digest."""
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return jsonify({"status": "error", "message": "please enter a valid email."}), 400

        try:
            existing = User.query.filter_by(email=email).first()
            if existing:
                return jsonify({"status": "info", "message": "already subscribed!"})
            new_user = User(email=email)
            db.session.add(new_user)
            db.session.commit()
            return jsonify({"status": "success", "message": "subscribed successfully!"})
        except Exception as e:
            print(f"[subscribe] error: {e}")
            db.session.rollback()
            return jsonify({"status": "error", "message": f"server error: {e}"}), 500

    return render_template("subscribe.html")


# ----------------------------------------------------------
# unsubscribe
# ----------------------------------------------------------
@frontend.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    """removes a user from the digest mailing list."""
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return jsonify({"status": "error", "message": "please enter a valid email."}), 400

        try:
            user = User.query.filter_by(email=email).first()
            if not user:
                return jsonify({"status": "info", "message": "email not found — you may already be unsubscribed."})

            db.session.delete(user)
            db.session.commit()
            print(f"[unsubscribe] removed {email}")
            return jsonify({"status": "success", "message": "you’ve been unsubscribed. farewell!"})
        except Exception as e:
            print(f"[unsubscribe] error: {e}")
            db.session.rollback()
            return jsonify({"status": "error", "message": "server error"}), 500

    return render_template("unsubscribe.html")


# ----------------------------------------------------------
# preferences (ui only)
# ----------------------------------------------------------
@frontend.route("/preferences")
def preferences_page():
    return render_template("preferences.html")


# ----------------------------------------------------------
# dashboard pages
# ----------------------------------------------------------
@frontend.route("/dashboard")
def dashboard_no_email():
    return render_template(
        "dashboard.html",
        user={"email": "unknown"},
        prefs=[],
        message="no email provided — please log in or subscribe first.",
    )


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

    message = "no liked papers yet — go like some in your digests!" if not prefs else None
    return render_template("dashboard.html", user={"email": email}, prefs=prefs, message=message)


# ----------------------------------------------------------
# feedback viewer (frontend)
# ----------------------------------------------------------
@frontend.route("/view-feedback")
def view_feedback_page():
    return render_template("feedback.html")
