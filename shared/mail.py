# shared/mail.py
"""
shared/mail.py — email sending utility for arXiv digest.
"""
import os, smtplib
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, has_app_context

mail = Mail()

_DELIVERY_APP = None


def _get_delivery_app():
    """obtain or initialize an app for logging when no request context exists."""
    if has_app_context():
        return current_app._get_current_object()

    global _DELIVERY_APP
    if _DELIVERY_APP is False:
        return None
    if _DELIVERY_APP is not None:
        return _DELIVERY_APP

    try:
        from webapp import create_app

        _DELIVERY_APP = create_app()
    except Exception as exc:
        print(f"[mailer] unable to bootstrap app for delivery logging: {exc}")
        _DELIVERY_APP = False
        return None
    return _DELIVERY_APP


def _log_delivery_event(recipient, subject, status, context="transactional", error=None):
    """
    persist delivery metadata. falls back to its own app context when needed.
    """
    app = _get_delivery_app()
    if not app:
        return

    try:
        from webapp.models import DeliveryEvent
    except Exception as exc:
        print(f"[mailer] delivery log skipped (import error): {exc}")
        return

    def _write():
        DeliveryEvent.log_event(
            recipient=recipient or "(unknown)",
            subject=subject,
            status=status,
            context=context,
            provider="smtp",
            error=error,
            auto_commit=True,
        )

    if has_app_context():
        try:
            _write()
        except Exception as exc:
            print(f"[mailer] delivery log skipped: {exc}")
        return

    # create our own context for CLI usage
    try:
        with app.app_context():
            _write()
    except Exception as exc:
        print(f"[mailer] delivery log skipped (ctx): {exc}")


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


def send_email(cfg, subject, text, html=None, *, to_override=None, context="transactional"):
    """
    send email via gmail smtp using config.yaml -> output.email.

    `cfg` may be the full config dict or just the `output.email` section.
    Pass `to_override` (iterable or string) to override the recipient list.
    """
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
        recipients = to_override or mail_cfg.get("to_addrs") or [username]
        if isinstance(recipients, str):
            recipients = [recipients]
        elif recipients is None:
            recipients = [username] if username else []
        recipients = [r for r in recipients if r]

        if not username or not password:
            print("[mailer] missing username or password - printing instead")
            print(f"TO: {recipients}\nSUBJECT: {subject}\n{text}")
            for rec in recipients or ["(unknown)"]:
                _log_delivery_event(rec, subject, "simulated", context)
            return True

        print(f"[mailer] sending real email from {from_addr} to {recipients}")
        print(f"[mailer] subject: {subject}")
        print(f"[mailer] using smtp: {server}:{port} with STARTTLS")

        # compose multipart message
        msg = MIMEMultipart("alternative")
        msg["subject"] = f"{mail_cfg.get('subject_prefix', '')} {subject}".strip()
        msg["from"] = from_addr
        msg["to"] = ", ".join(recipients)

        part1 = MIMEText(text, "plain", "utf-8")
        msg.attach(part1)

        if html:
            part2 = MIMEText(html, "html", "utf-8")
            msg.attach(part2)

        # send email
        with smtplib.SMTP(server, port) as smtp:
            if mail_cfg.get("use_starttls", True):
                smtp.starttls()
            smtp.login(username, password)
            smtp.sendmail(from_addr, recipients, msg.as_bytes())

        print("[mailer] email sent successfully")
        for rec in recipients:
            _log_delivery_event(rec, subject, "sent", context)
        return True

    except Exception as e:
        print(f"[mailer] error: {e}")
        for rec in recipients or ["(unknown)"]:
            _log_delivery_event(rec, subject, "failed", context, error=str(e))
        return False
