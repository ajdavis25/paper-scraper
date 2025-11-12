import os, base64, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()


def _ensure_gmail_tokens():
    """
    decode Base64 environment variables on Vercel into local secrets/ files.
    """
    os.makedirs("secrets", exist_ok=True)
    creds_path = "secrets/credentials.json"
    token_path = "secrets/token.json"

    if os.getenv("GMAIL_CREDENTIALS_B64"):
        with open(creds_path, "wb") as f:
            f.write(base64.b64decode(os.getenv("GMAIL_CREDENTIALS_B64")))
    if os.getenv("GMAIL_TOKEN_B64"):
        with open(token_path, "wb") as f:
            f.write(base64.b64decode(os.getenv("GMAIL_TOKEN_B64")))

    return creds_path, token_path


def _get_oauth2_string(username, creds):
    """generate the SASL XOAUTH2 string."""
    auth_str = f"user={username}\1auth=Bearer {creds.token}\1\1"
    return base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")


def send_email(cfg, subject, text_body, html_body, to_override=None):
    em = cfg["output"]["email"]
    recipients = to_override or em.get("to_addrs", [])
    if not recipients:
        print("[mailer] warning: no recipients found")
        return

    creds_path, token_path = _ensure_gmail_tokens()
    creds = Credentials.from_authorized_user_file(token_path)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            auth_string = _get_oauth2_string(em["from_addr"], creds)
            s.docmd("AUTH", "XOAUTH2 " + auth_string)

            for addr in recipients:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = em["from_addr"]
                msg["To"] = addr
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))
                s.sendmail(em["from_addr"], addr, msg.as_bytes())
                print(f"[mailer] sent email to {addr}")

    except Exception as e:
        print(f"[mailer] fatal error: {e}")
