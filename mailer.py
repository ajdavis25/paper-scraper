import os, base64, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()


def _ensure_gmail_tokens():
    """
    decode Base64 environment variables on vercel into local secrets/files.
    """
    os.makedirs("secrets", exist_ok=True)
    creds_path = "secrets/credentials.json"
    token_path = "secrets/token.json"

    # decode credentials.json if provided
    if os.getenv("GMAIL_CREDENTIALS_B64"):
        with open(creds_path, "wb") as f:
            f.write(base64.b64decode(os.getenv("GMAIL_CREDENTIALS_B64")))

    # decode token.json if provided
    if os.getenv("GMAIL_TOKEN_B64"):
        with open(token_path, "wb") as f:
            f.write(base64.b64decode(os.getenv("GMAIL_TOKEN_B64")))

    return creds_path, token_path


def _get_oauth2_string(username, access_token):
    """generate the SASL XOAUTH2 string."""
    auth_str = f"user={username}\1auth=Bearer {access_token}\1\1"
    return base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")


def _load_gmail_credentials(creds_path, token_path):
    """
    load Gmail OAuth2 credentials from token.json or environment variables.
    if token.json is missing or invalid, rebuild from refresh token + client info.
    """
    creds = None

    # try to load existing token.json first
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path)
        except Exception:
            creds = None

    # fallback if no valid creds
    if not creds or not creds.valid:
        refresh_token = os.getenv("GMAIL_PUSH_REFRESH_TOKEN")
        client_id = os.getenv("GMAIL_PUSH_CLIENT_ID")
        client_secret = os.getenv("GMAIL_PUSH_CLIENT_SECRET")

        if not all([refresh_token, client_id, client_secret]):
            raise RuntimeError(
                "[mailer] Missing one or more of GMAIL_PUSH_REFRESH_TOKEN / CLIENT_ID / CLIENT_SECRET"
            )

        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )

    # refresh if expired
    if creds and (not creds.valid or creds.expired):
        creds.refresh(Request())
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def send_email(cfg, subject, text_body, html_body, to_override=None):
    em = cfg["output"]["email"]
    recipients = to_override or em.get("to_addrs", [])
    if not recipients:
        print("[mailer] warning: no recipients found")
        return

    creds_path, token_path = _ensure_gmail_tokens()
    creds = _load_gmail_credentials(creds_path, token_path)
    access_token = creds.token

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            auth_string = _get_oauth2_string(em["from_addr"], access_token)
            code, response = s.docmd("AUTH", "XOAUTH2 " + auth_string)
            if code != 235:
                raise Exception(f"AUTH failed: {code} {response}")

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
