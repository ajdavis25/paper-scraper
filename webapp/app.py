from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime
from routes_frontend import frontend

app = Flask(__name__)
CORS(app)

# use /tmp — this is the only writable path on vercel
if os.name == "nt":  # windows
    db_path = os.path.join(os.path.dirname(__file__), "feedback.db")
else:  # vercel (Linux)
    db_path = os.path.join("/tmp", "feedback.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

app.register_blueprint(frontend)

# database model
class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255))
    arxiv_id = db.Column(db.String(64))
    liked = db.Column(db.Boolean)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()


# routes
@app.route("/")
def home():
    return "astro-ph digest backend is live!"


@app.route("/like")
def like():
    email = request.args.get("email")
    arxiv_id = request.args.get("arxiv_id")
    liked = request.args.get("liked", "false").lower() == "true"

    if not email or not arxiv_id:
        return jsonify({"error": "missing email or arxiv_id"}), 400

    feedback = Feedback(email=email, arxiv_id=arxiv_id, liked=liked)
    db.session.add(feedback)
    db.session.commit()

    return jsonify({
        "message": f"recorded {'like' if liked else 'dislike'} for {arxiv_id} by {email}"
    })


@app.route("/feedback")
def feedback():
    """display all recorded likes/dislikes as an HTML table."""
    rows = Feedback.query.order_by(Feedback.timestamp.desc()).limit(200).all()

    if not rows:
        return "<h3>no feedback recorded yet</h3>"

    html = ["<h2>astro-ph digest feedback</h2><table border='1' cellpadding='5'>"]
    html.append("<tr><th>email</th><th>arXiv ID</th><th>Liked?</th><th>timestamp (UTC)</th></tr>")

    for row in rows:
        html.append(
            f"<tr><td>{row.email}</td>"
            f"<td><a href='https://arxiv.org/abs/{row.arxiv_id}'>{row.arxiv_id}</a></td>"
            f"<td>{'👍' if row.liked else '👎'}</td>"
            f"<td>{row.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>"
        )

    html.append("</table>")
    return "\n".join(html)


@app.route("/recommend")
def recommend():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "missing email"}), 400
    return jsonify({
        "message": f"recommendations for {email} coming soon!"
    })


@app.route("/view-feedback")
def view_feedback():
    email = request.args.get("email")

    # if an email is provided, only show that user's feedback
    if email:
        feedback_entries = Feedback.query.filter_by(email=email).order_by(Feedback.timestamp.desc()).all()
    else:
        feedback_entries = Feedback.query.order_by(Feedback.timestamp.desc()).all()

    results = []
    for entry in feedback_entries:
        results.append({
            "id": entry.id,
            "email": entry.email,
            "arxiv_id": entry.arxiv_id,
            "liked": entry.liked,
            "timestamp": entry.timestamp.isoformat()
        })

    return jsonify({
        "count": len(results),
        "feedback": results
    })


@app.route("/dashboard/<email>")
def dashboard(email):
    feedback_entries = Feedback.query.filter_by(email=email, liked=True).order_by(Feedback.timestamp.desc()).all()
    prefs = [
        {"paper": {"title": f"arXiv:{entry.arxiv_id}", "link": f"https://arxiv.org/abs/{entry.arxiv_id}", "arxiv_id": entry.arxiv_id}}
        for entry in feedback_entries
    ]
    user = {"email": email}
    return render_template("dashboard.html", user=user, prefs=prefs)


# run locally
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
