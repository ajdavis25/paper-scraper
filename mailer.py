import os, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# load local .env if present
load_dotenv()


def send_email(cfg, subject, text_body, html_body, to_override=None):
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
    if not recipients:
        print("[mailer] warning: no recipients found in config.yaml")
        return

    try:
        with smtplib.SMTP(em["smtp_host"], em["smtp_port"]) as s:
            if em.get("use_starttls", True):
                s.starttls()

            try:
                print("[mailer debug]", {
                "username": em["username"],
                "password_length": len(password),
                "password_preview": password[:4] + "..." if password else None
            })
                s.login(em["username"], password)
            except smtplib.SMTPAuthenticationError as e:
                print("[mailer] gmail rejected credentials — please recheck EMAIL_FROM / EMAIL_PASS in your .env")
                print(f"[details] {e.smtp_error.decode('utf-8')}")
                return
            except Exception as e:
                print(f"[mailer] unexpected error during login: {e}")
                return

            for addr in (to_override or em["to_addrs"]):
                msg = MIMEMultipart("alternative")
                msg["subject"] = subject
                msg["from"] = em["from_addr"]
                msg["to"] = addr
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                try:
                    s.sendmail(em["from_addr"], addr, msg.as_string())
                    print(f"[mailer] sent email to {addr}")
                except Exception as e:
                    print(f"[mailer] failed to send email to {addr}: {e}")

    except Exception as e:
        print(f"[mailer] fatal error: {e}")
