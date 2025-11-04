from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from .models import db, User

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
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return jsonify({"status": "error", "message": "please enter a valid email."})

        existing = User.query.filter_by(email=email).first()
        if existing:
            return jsonify({"status": "info", "message": "you're already subscribed!"})

        new_user = User(email=email)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"status": "success", "message": "successfully subscribed! welcome to the daily digest."})

    return render_template("subscribe.html")


# ----------------------------------------------------------
# unsubscribe
# ----------------------------------------------------------
@frontend.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return jsonify({"status": "error", "message": "please enter a valid email."})

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"status": "info", "message": "email not found — you may already be unsubscribed."})

        db.session.delete(user)
        db.session.commit()
        return jsonify({"status": "success", "message": "you’ve been unsubscribed. farewell!"})

    return render_template("unsubscribe.html")
