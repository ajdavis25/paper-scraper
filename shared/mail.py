# shared/mail.py
import os, smtplib
from email.mime.text import MIMEText

def send_email(cfg, subject, text, html):
    """send email via gmail smtp using config.yaml -> output.email"""
    try:
        mail_cfg = (
            cfg.get("mail")
            or cfg.get("output", {}).get("email")
            or cfg
        )
        if not isinstance(mail_cfg, dict):
            print(f"[mailer] malformed mail_cfg: {mail_cfg}")
            return False

        server = mail_cfg.get("smtp_host", "smtp.gmail.com")
        port = int(mail_cfg.get("smtp_port", 587))
        username = mail_cfg.get("username")
        password = os.getenv(mail_cfg.get("password_env", "EMAIL_PASS"))
        recipient = mail_cfg.get("from_addr") or mail_cfg.get("to_addrs", [username])[0]

        if not username or not password:
            print("[mailer] missing username or password — printing instead")
            print(f"TO: {recipient}\nSUBJECT: {subject}\n{text}")
            return True

        msg = MIMEText(html, "html")
        msg["subject"] = subject
        msg["from"] = username
        msg["to"] = recipient

        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)

        print(f"[mailer] sent email successfully to {recipient}")
        return True

    except Exception as e:
        print(f"[mailer] error: {e}")
        return False
