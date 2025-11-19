import os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# load local .env if present
load_dotenv()

_FLASK_APP = None


def _get_flask_app():
    """lazy-load the flask app so CLI sends can log delivery health."""
    global _FLASK_APP
    if _FLASK_APP is False:
        return None
    if _FLASK_APP is None:
        try:
            from webapp import create_app

            _FLASK_APP = create_app()
        except Exception as exc:
            print(f"[mailer] unable to init flask app for delivery logging: {exc}")
            _FLASK_APP = False
    return _FLASK_APP or None


def _log_delivery_event(recipient, subject, status, context="digest", error=None):
    """
    mirror shared.mail logging so per-recipient failures get surfaced in the dashboard.
    """
    app = _get_flask_app()
    if not app:
        return
    try:
        from webapp.models import DeliveryEvent
    except Exception as exc:
        print(f"[mailer] cannot import DeliveryEvent: {exc}")
        return

    clean_recipient = (recipient or "").strip().lower() or "(unknown)"
    clean_subject = (subject or "").strip()
    with app.app_context():
        try:
            DeliveryEvent.log_event(
                recipient=clean_recipient,
                subject=clean_subject,
                status=status,
                context=context,
                provider="smtp",
                error=error,
                auto_commit=True,
            )
        except Exception as exc:
            print(f"[mailer] failed to log delivery event: {exc}")


def send_email(cfg, subject, text_body, html_body, to_override=None, context="digest"):
    """
    send an email using credentials from environment variables
    or config.yaml (via cfg["output"]["email"]).

    the yaml config should define:
      output:
        email:
          from_addr: ...
          to_addrs: [...]
          username: ...
          password_env: "EMAIL_PASS"   # environment variable name
          smtp_host: "smtp.gmail.com"
          smtp_port: 587
          use_starttls: true

    optionally, pass `to_override=["someone@example.com"]`
    to override the configured recipient list.
    """
    em = cfg["output"]["email"]

    # load password
    password = os.getenv(em.get("password_env", "EMAIL_PASS"), "")
    if not password:
        raise RuntimeError(
            f"missing password in environment variable: {em.get('password_env', 'EMAIL_PASS')}"
        )

    recipients = to_override or em.get("to_addrs", [])
    recipients = [(addr or "").strip() for addr in recipients if (addr or "").strip()]
    if not recipients:
        print("[mailer] warning: no recipients found in config.yaml")
        return

    try:
        with smtplib.SMTP(em["smtp_host"], em["smtp_port"]) as s:
            if em.get("use_starttls", True):
                s.starttls()

            try:
                print(
                    "[mailer debug]",
                    {
                        "username": em["username"],
                        "password_length": len(password),
                        "password_preview": password[:4] + "..." if password else None,
                    },
                )
                s.login(em["username"], password)
            except smtplib.SMTPAuthenticationError as e:
                print(
                    "[mailer] gmail rejected credentials -- please recheck EMAIL_FROM / EMAIL_PASS in your .env"
                )
                print(f"[details] {e.smtp_error.decode('utf-8')}")
                for addr in recipients:
                    _log_delivery_event(addr, subject, "failed", context, error="auth")
                return
            except Exception as e:
                print(f"[mailer] unexpected error during login: {e}")
                for addr in recipients:
                    _log_delivery_event(addr, subject, "failed", context, error=str(e))
                return

            for addr in recipients:
                msg = MIMEMultipart("alternative")
                msg["subject"] = subject
                msg["from"] = em["from_addr"]
                msg["to"] = addr
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                try:
                    s.sendmail(em["from_addr"], addr, msg.as_bytes())
                    print(f"[mailer] sent email to {addr}")
                    _log_delivery_event(addr, subject, "sent", context)
                except Exception as e:
                    print(f"[mailer] failed to send email to {addr}: {e}")
                    _log_delivery_event(addr, subject, "failed", context, error=str(e))

    except Exception as e:
        print(f"[mailer] fatal error: {e}")
        for addr in recipients or ["(unknown)"]:
            _log_delivery_event(addr, subject, "failed", context, error=str(e))
