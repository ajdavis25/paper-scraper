import os

import pytest
from werkzeug.security import check_password_hash

os.environ.setdefault("SECRET_KEY", "test-secret-key")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """spin up the flask app backed by a temp sqlite db."""
    db_path = tmp_path_factory.mktemp("db") / "magic_link.sqlite"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from webapp import create_app

    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture(autouse=True)
def clean_db(app):
    """reset database state before each test so flows start fresh."""
    from shared.db import db
    from webapp.models import ensure_preference_config_schema

    with app.app_context():
        db.drop_all()
        db.create_all()
        ensure_preference_config_schema()
    yield
    with app.app_context():
        db.session.remove()


def test_email_magic_link_claim_flow(app, monkeypatch):
    """full flow: subscribe email-only, receive magic link, claim + log in."""
    from shared.mail import get_serializer
    from shared.db import db
    from webapp.models import User, Subscriber

    sent_emails = []

    def fake_send(to_email, kind, **kwargs):
        sent_emails.append({"email": to_email, "kind": kind, "meta": kwargs})
        return True

    monkeypatch.setattr("webapp.routes_frontend._send_subscription_email", fake_send)

    client = app.test_client()
    email = "magic-link@example.com"

    resp = client.post("/subscribe", json={"email": email})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "success"
    assert "check your email" in payload["message"]

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user is not None
        assert user.password_hash == ""
        assert Subscriber.query.filter_by(email=email).count() == 1
        token = get_serializer().dumps(email, salt="claim-account")

    assert sent_emails and sent_emails[0]["kind"] == "welcome"

    # GET the claim page to ensure the token is accepted.
    page = client.get(f"/claim-account/{token}")
    assert page.status_code == 200
    assert email in page.get_data(as_text=True)

    # POST a new password via the magic link.
    resp = client.post(
        f"/claim-account/{token}", data={"password": "super-secret"}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert user is not None
        assert user.password_hash
        assert check_password_hash(user.password_hash, "super-secret")

    # logout to prove the password now works through the standard form
    client.get("/logout")
    login_resp = client.post(
        "/login",
        data={"email": email, "password": "super-secret"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302
    assert login_resp.headers["Location"] == "/"
