from __future__ import print_function
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path, re, yaml, base64
from email.mime.text import MIMEText

# full gmail access for read + send
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]


def get_gmail_service():
    """authenticate and return a Gmail API service object."""
    creds = None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(base_dir, "../secrets/token.json")
    cred_path = os.path.join(base_dir, "../secrets/credentials.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

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


def check_new_subscribers():
    """look for unread emails with 'subscribe' in subject, update config.yaml, and welcome them."""
    service = get_gmail_service()
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

        # extract address from "Name <email>"
        match = re.search(r"<(.+?)>", sender)
        email_addr = match.group(1) if match else sender

        if email_addr:
            print(f"subscribing {email_addr}")
            added = add_to_mailing_list(email_addr)
            if added:
                send_welcome_email(service, email_addr)
            mark_as_read(service, msg["id"])
        else:
            print(f"could not parse sender: {sender}")


def mark_as_read(service, msg_id):
    """mark message as read to avoid re-processing."""
    service.users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def add_to_mailing_list(new_email):
    """append new email to output.email.to_addrs if not already present."""
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../config.yaml")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    to_addrs = cfg["output"]["email"]["to_addrs"]

    if new_email not in to_addrs:
        to_addrs.append(new_email)
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)
        print(f"added {new_email} to mailing list.")
        return True
    else:
        print(f"already subscribed: {new_email}")
        return False


if __name__ == "__main__":
    check_new_subscribers()
