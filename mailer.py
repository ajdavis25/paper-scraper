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

    # determine recipients
    to_addrs = to_override or em.get("to_addrs", [])
    if not to_addrs:
        raise ValueError("no recipients specified.")

    # build MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = em["from_addr"]
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # load password securely
    pw_env = em.get("password_env", "EMAIL_PASS")
    password = os.getenv(pw_env, "")
    if not password:
        raise RuntimeError(f"missing password in environment variable: {pw_env}")

    # connect and send
    try:
        with smtplib.SMTP(em["smtp_host"], em["smtp_port"], timeout=20) as s:
            if em.get("use_starttls", True):
                s.starttls()
            s.login(em["username"], password)
            s.sendmail(em["from_addr"], to_addrs, msg.as_string())
            print(f"[mailer] email sent to {', '.join(to_addrs)}")
    except Exception as e:
        print(f"[mailer] ERROR sending to {', '.join(to_addrs)}: {e}")
