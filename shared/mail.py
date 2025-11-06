# shared/mail.py
"""
shared/mail.py — email sending utility for astro-ph digest.
"""
import os, smtplib
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

mail = Mail()


def get_serializer():
    secret = current_app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY not set in environment or app config.")
    return URLSafeTimedSerializer(secret)


def generate_reset_token(email):
    return get_serializer().dumps(email, salt="password-reset")


def verify_reset_token(token, max_age=3600):
    try:
        email = get_serializer().loads(token, salt="password-reset", max_age=max_age)
    except Exception:
        return None
    return email


def send_reset_email(email, link):    
    msg = Message(
        subject="reset your password",
        recipients=[email],
        body=(
            f"hello,\n\n"
            f"click the link below to reset your password:\n\n{link}\n\n"
            f"if you didn’t request this, you can ignore this message."
        ),
        html=(
            f"<p>hello,</p>"
            f"<p>click the link below to reset your password:</p>"
            f"<p><a href='{link}'>{link}</a></p>"
            f"<p>if you didn’t request this, you can ignore this message.</p>"
        )
    )

    mail.send(msg)


def send_email(cfg, subject, text, html=None):
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
        from_addr = mail_cfg.get("from_addr", username)
        to_addrs = mail_cfg.get("to_addrs") or [username]

        if not username or not password:
            print("[mailer] missing username or password — printing instead")
            print(f"TO: {to_addrs}\nSUBJECT: {subject}\n{text}")
            return True

        print(f"[mailer] sending real email from {from_addr} to {to_addrs}")
        print(f"[mailer] subject: {subject}")
        print(f"[mailer] using smtp: {server}:{port} with STARTTLS")

        # compose multipart message
        msg = MIMEMultipart("alternative")
        msg["subject"] = f"{mail_cfg.get('subject_prefix', '')} {subject}".strip()
        msg["from"] = from_addr
        msg["to"] = ", ".join(to_addrs)

        part1 = MIMEText(text, "plain")
        msg.attach(part1)

        if html:
            part2 = MIMEText(html, "html")
            msg.attach(part2)

        # send email
        with smtplib.SMTP(server, port) as smtp:
            if mail_cfg.get("use_starttls", True):
                smtp.starttls()
            smtp.login(username, password)
            smtp.sendmail(from_addr, to_addrs, msg.as_string())

        print("[mailer] email sent successfully")
        return True

    except Exception as e:
        print(f"[mailer] error: {e}")
        return False
