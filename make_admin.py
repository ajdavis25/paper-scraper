from astroph_bot.webapp import create_app
from astroph_bot.webapp.models import db, User

app = create_app()

with app.app_context():
    user = User.query.filter_by(email="ajd96@proton.me").first()
    if user:
        user.is_admin = True
        db.session.commit()
        print(f"{user.email} is now an admin!")
    else:
        print("no user found with that email.")
