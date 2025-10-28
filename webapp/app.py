from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# use /tmp — this is the only writable path on vercel
db_path = os.path.join("/tmp", "feedback.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255))
    arxiv_id = db.Column(db.String(64))
    liked = db.Column(db.Boolean)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

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

@app.route("/recommend")
def recommend():
    email = request.args.get("email")
    return jsonify({
        "message": f"recommendations for {email} coming soon!"
    })

if __name__ == "__main__":
    app.run()
