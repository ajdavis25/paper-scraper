from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os, yaml

from .models import db, User, Paper, UserPreference
from .routes_frontend import frontend
from ..mailer import send_email

app = Flask(__name__)
CORS(app)

# ==========================================================
# database configuration
# ==========================================================
if os.name == "nt":  # windows local
    db_path = os.path.join(os.path.dirname(__file__), "feedback.db")
else:  # linux (vercel)
    db_path = os.path.join("/tmp", "feedback.db")

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "supersecret"  # required for flask-wtf csrf protection

db.init_app(app)
app.register_blueprint(frontend)

with app.app_context():
    db.create_all()

# ==========================================================
# routes
# ==========================================================

@app.route("/")
def home():
    return "astro-ph digest backend is live!"


# ----------------------------------------------------------
# record like/dislike (called from digest links later)
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
# feedback summary (for quick debugging)
# ----------------------------------------------------------
@app.route("/feedback")
def feedback():
    prefs = UserPreference.query.order_by(UserPreference.created_at.desc()).limit(100).all()

    if not prefs:
        return "<h3>no feedback recorded yet.</h3>"

    html = ["<h2>astro-ph digest feedback</h2><table border='1' cellpadding='5'>"]
    html.append("<tr><th>email</th><th>arXiv id</th><th>liked?</th><th>timestamp</th></tr>")

    for pref in prefs:
        html.append(
            f"<tr><td>{pref.user.email}</td>"
            f"<td><a href='https://arxiv.org/abs/{pref.paper.arxiv_id}'>{pref.paper.arxiv_id}</a></td>"
            f"<td>{'👍' if pref.liked else '👎'}</td>"
            f"<td>{pref.created_at.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>"
        )

    html.append("</table>")
    return "\n".join(html)


@app.route("/view-feedback")
def view_feedback_page():
    """renders the feedback.html frontend (table is populated by JS)."""
    return render_template("feedback.html")


# ----------------------------------------------------------
# preferences page + rest api
# ----------------------------------------------------------
@app.route("/preferences", methods=["GET"])
def preferences_page():
    """render the preferences page (static JS handles submission)."""
    return render_template("preferences.html")


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


@app.route("/send-feedback", methods=["GET", "POST"])
def user_feedback():
    """allow users to submit freeform feedback messages."""
    if request.method == "POST":
        print("[debug] received post /feedback")
        data = request.get_json(force=True)
        name = data.get("name", "Anonymous")
        email = data.get("email", "")
        message = data.get("message", "")

        if not message.strip():
            return jsonify({"error": "message cannot be empty"}), 400

        # save locally
        log_path = os.path.join(os.path.dirname(__file__), "user_feedback.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow()}] {name} <{email}>: {message}\n")

        print(f"[astro-ph bot] received user feedback from {name}: {message}")

        # send email notification using existing mailer config
        try:
            # load yaml config (reuse config.yaml at project root)
            cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            subject = f"[astro-ph feedback] new message from {name}"
            text_body = f"from: {name} <{email}>\n\n{message}"
            html_body = f"<p><strong>from:</strong> {name} &lt;{email}&gt;</p><p>{message}</p>"

            send_email(cfg, subject, text_body, html_body)
            print("[mailer] feedback notification sent")
        except Exception as e:
            print(f"[mailer] error sending feedback email: {e}")

        return jsonify({"message": "thank you for your feedback!"})

    # fender form
    return render_template("feedback_form.html")



# ----------------------------------------------------------
# dashboard (shows all liked papers for a given email)
# ----------------------------------------------------------
@app.route("/dashboard/<email>")
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

    if not prefs:
        message = "no liked papers yet — go like some in your digests!"
        return render_template("dashboard.html", user={"email": email}, prefs=[], message=message)

    return render_template("dashboard.html", user={"email": email}, prefs=prefs)


# ----------------------------------------------------------
# recommend (placeholder)
# ----------------------------------------------------------
@app.route("/recommend")
def recommend():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "missing email"}), 400
    return jsonify({"message": f"recommendations for {email} coming soon!"})


# ==========================================================
# run locally
# ==========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
