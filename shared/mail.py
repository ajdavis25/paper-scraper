# shared/mail.py
from ..mailer import send_email
import yaml

def send_feedback_notification(cfg_path, name, email, message):
    """send a feedback email to the bot's inbox."""
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    subject = f"[astro-ph feedback] new message from {name}"
    text = f"from: {name} <{email}>\n\n{message}"
    html = f"<p><strong>from:</strong> {name} &lt;{email}&gt;</p><p>{message}</p>"

    send_email(cfg, subject, text, html, to_override=[cfg["output"]["email"]["from_addr"]])
