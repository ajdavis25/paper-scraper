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


def send_unsub_confirm(service, to_email):
    """send a polite goodbye email."""
    message = MIMEText(
        "what? did you get accepted to stanford or something?\n\n"
        "whatever major loser, we didn't want you here anyways!\n\n"
        "you’ve been removed from the astro-ph digest mailing list.\n\n"
        "if you’d like to rejoin later, just send an email with the subject 'subscribe'.\n\n"
        "clear skies,\nthe astro-ph digest bot"
    )
    message["to"] = to_email
    message["subject"] = "astro-ph digest: unsubscription confirmed"

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    body = {"raw": raw}
    try:
        service.users().messages().send(userId="me", body=body).execute()
        print(f"sent unsubscribe confirmation to {to_email}")
    except Exception as e:
        print(f"[gmail] FAILED to send farewell email to {to_email}: {e}")


def check_unsubscribers():
    """look for unread 'unsubscribe' emails and remove them from config.yaml."""
    service = get_gmail_service()
    if not service:
        print("[gmail] no service available — skipping subscription check.")
        return
    
    results = service.users().messages().list(userId="me", q="is:unread subject:unsubscribe").execute()
    msgs = results.get("messages", [])

    if not msgs:
        print("no new unsubscribe requests.")
        return

    print(f"found {len(msgs)} unsubscribe message(s).")

    for msg in msgs:
        data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
        sender = headers.get("From", "").strip()

        match = re.search(r"<(.+?)>", sender)
        email_addr = match.group(1) if match else sender

        if email_addr:
            print(f"removing {email_addr} from mailing list")
            removed = remove_from_database(email_addr)
            if removed:
                send_unsub_confirm(service, email_addr)  # always send farewell email
            mark_as_read(service, msg["id"])
        else:
            print(f"could not parse sender: {sender}")


def mark_as_read(service, msg_id):
    """mark gmail message as read."""
    service.users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def remove_from_database(email_addr):
    """remove an email from the subscriber table."""
    try:
        from webapp import create_app
        from webapp.models import Subscriber
        from shared.db import db
    except Exception as exc:
        print(f"[unsubscribe] failed to import app/db modules: {exc}")
        return False

    try:
        app = create_app()
    except Exception as exc:
        print(f"[unsubscribe] failed to initialise app: {exc}")
        return False

    lower_email = (email_addr or "").strip().lower()
    if not lower_email:
        return False

    try:
        with app.app_context():
            existing = (
                Subscriber.query
                .filter(func.lower(Subscriber.email) == lower_email)
                .first()
            )
            if not existing:
                print(f"address not found in database: {email_addr}")
                return False

            db.session.delete(existing)
            db.session.commit()
            print(f"removed {email_addr} from subscriber table.")
            return True
    except Exception as exc:
        print(f"[unsubscribe] database error: {exc}")
        db.session.rollback()
        return False


if __name__ == "__main__":
    check_unsubscribers()
