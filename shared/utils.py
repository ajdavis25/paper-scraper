# shared/utils.py
import re, yaml, datetime, os

def load_yaml(path):
    """load yaml safely and return {} if missing."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def sanitize_email(address):
    """clean and normalize an email address."""
    return address.strip().lower() if address else ""

def timestamp():
    """return utc timestamp for logs."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def slugify(text):
    """make a string safe for filenames."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_")
