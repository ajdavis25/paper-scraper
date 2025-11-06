# init_db.py
from webapp import create_app
from shared.db import db

app = create_app()

with app.app_context():
    db.create_all()
    print("database tables created.")
