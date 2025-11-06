# test_email.py
import yaml
from shared.mail import send_email

cfg = yaml.safe_load(open("config.yaml"))
send_email(cfg["output"]["email"], "Test", "plain", "<h1>html</h1>")
