from __future__ import print_function
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from sqlalchemy import func
import os.path, re, base64
from email.mime.text import MIMEText

# gmail scopes for read + send
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send"
]


def get_gmail_service():
    """authenticate gmail API using credentials or github secret."""
    creds = None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    secrets_dir = os.path.join(base_dir, "../secrets")
    token_path = os.path.join(secrets_dir, "token.json")
    cred_path = os.path.join(secrets_dir, "credentials.json")

    os.makedirs(secrets_dir, exist_ok=True)

    # write secrets from github if provided
    if os.getenv("GMAIL_CREDENTIALS_JSON"):
        with open(cred_path, "w", encoding="utf-8") as f:
            f.write(os.getenv("GMAIL_CREDENTIALS_JSON"))

    if os.getenv("GMAIL_TOKEN_JSON"):
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(os.getenv("GMAIL_TOKEN_JSON"))

    # try loading token.json
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            print(f"[gmail] failed to load token.json: {e}")

    # if no valid creds, just try from client secrets (if possible)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("[gmail] WARNING: no valid gmail credentials loaded (headless mode).")
            return None

    return build("gmail", "v1", credentials=creds)


def send_welcome_email(service, to_email):
    """send a welcome message to the new subscriber."""
    message = MIMEText(
        "welcome to the astro-ph digest mailing list!\n\n"
        "you’ll now receive a daily curated selection of the most relevant astro-ph papers.\n"
        "if you ever wish to unsubscribe, simply reply with 'unsubscribe'.\n\n"
        "clear skies,\nthe astro-ph digest bot"
    )
    message["to"] = to_email
    message["subject"] = "welcome to the astro-ph digest!"

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body = {"raw": raw}
    service.users().messages().send(userId="me", body=body).execute()
    print(f"sent welcome email to {to_email}")


def domain_is_stanford(address: str) -> bool:
    """true if address is a stanford email (handles subdomains, case insensitive)."""
    addr = (address or "").lower().strip()
    return addr.endswith("@stanford.edu") or addr.endswith(".stanford.edu")


def send_stanford_reply(service, to_email):
    """send an auto reply to stanford users only."""
    message = MIMEText(
        "bzzbzz verification pending...\n\n"
        "system detected a stanford domain. this may require manual approval "
        "from the committe on gatekeeping.\n\n"
        "please standby for further instructions.\n\n"
        "just kidding, you'll be added shortly.\n\n"
        "clear skies,\nthe astro-ph digest bot"
    )
    message["to"] = to_email
    message["subject"] = "astro-ph digest: gatekeeper verification"

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body = {"raw": raw}
    service.users().messages().send(userId="me", body=body).execute()
    print(f"sent stanford verification joke email to {to_email}")


def check_new_subscribers():
    """look for unread emails with 'subscribe' in subject, update config.yaml, and welcome them."""
    service = get_gmail_service()
    if not service:
        print("[gmail] no service available — skipping subscription check.")
        return

    results = service.users().messages().list(userId="me", q="is:unread subject:subscribe").execute()
    msgs = results.get("messages", [])

    if not msgs:
        print("no new subscription emails.")
        return

    print(f"found {len(msgs)} new message(s).")

    for msg in msgs:
        data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
        sender = headers.get("From", "").strip()

        # extract address from "name <email>"
        match = re.search(r"<(.+?)>", sender)
        email_addr = match.group(1) if match else sender

        if not email_addr:
            print(f"could not parse sender: {sender}")
            mark_as_read(service, msg["id"])
            continue

        if domain_is_stanford(email_addr):
            send_stanford_reply(service, email_addr)

        print(f"subscribing {email_addr}")
        added = add_to_database(email_addr)
        if added:
            send_welcome_email(service, email_addr)

        mark_as_read(service, msg["id"])


def mark_as_read(service, msg_id):
    """mark message as read to avoid re-processing."""
    service.users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def add_to_database(new_email):
    """Insert subscriber into the database if not already present."""
    try:
        from webapp import create_app
        from webapp.models import Subscriber
        from webapp.account_utils import ensure_user_stub
        from shared.db import db
    except Exception as exc:
        print(f"[subscribe] failed to import app/db modules: {exc}")
        return False

    try:
        app = create_app()
    except Exception as exc:
        print(f"[subscribe] failed to initialise app: {exc}")
        return False

    lower_email = (new_email or "").strip().lower()
    if not lower_email:
        print("[subscribe] empty email, skipping.")
        return False

    try:
        with app.app_context():
            existing = (
                Subscriber.query
                .filter(func.lower(Subscriber.email) == lower_email)
                .first()
            )
            if existing:
                print(f"already subscribed: {new_email}")
                return False

            sub = Subscriber(email=lower_email)
            db.session.add(sub)
            ensure_user_stub(lower_email, commit=False)
            db.session.commit()
            print(f"added {new_email} to subscriber table.")
            return True
    except Exception as exc:
        print(f"[subscribe] database error: {exc}")
        db.session.rollback()
        return False


if __name__ == "__main__":
    check_new_subscribers()
