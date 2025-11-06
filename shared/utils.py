# shared/utils.py
"""
General-purpose helpers for astro-ph digest.
"""
from __future__ import annotations

import re
import yaml
import requests
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------
def load_yaml(path):
    """Safely load YAML into a Python object."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[load_yaml] error reading {path}: {e}")
        return {}


def save_yaml(path, data):
    """Persist Python data to YAML."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
    except Exception as e:
        print(f"[save_yaml] error writing {path}: {e}")


# ---------------------------------------------------------------------------
# arXiv helpers
# ---------------------------------------------------------------------------
def build_arxiv_query(keywords, max_results=5):
    """
    Construct an arXiv API query string given keywords.
    Example: https://export.arxiv.org/api/query?search_query=all:black+hole&sortBy=submittedDate
    """
    base = "https://export.arxiv.org/api/query?"
    if not keywords:
        return base + "search_query=cat:astro-ph&sortBy=submittedDate&sortOrder=descending"

    query = "+OR+".join(f"all:{kw}" for kw in keywords)
    return (
        f"{base}search_query={query}"
        f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    )


_TEX_INLINE_PATTERN = re.compile(
    r"(?<!\$)(\\[A-Za-z]+(?:[_^]\{[^}]*\})*)(?![A-Za-z0-9]|\$)"
)


def wrap_inline_tex(text: str) -> str:
    """
    Wrap bare TeX commands (e.g. \\dot{M}) in $...$ so MathJax/KaTeX can render them.
    """
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        expr = match.group(1)
        return f"${expr}$"

    return _TEX_INLINE_PATTERN.sub(repl, text)


def fetch_arxiv_feed(url):
    """Fetch and parse the arXiv API XML feed, returning a list of papers."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            link = entry.find("atom:id", ns)

            summary_text = summary.text.strip() if summary is not None else ""
            entries.append(
                {
                    "title": title.text.strip() if title is not None else "(no title)",
                    "summary": wrap_inline_tex(summary_text),
                    "link": link.text.strip() if link is not None else "#",
                }
            )

        print(f"[fetch_arxiv_feed] parsed {len(entries)} entries")
        return entries
    except Exception as e:
        print(f"[fetch_arxiv_feed] error: {e}")
        return []


# ---------------------------------------------------------------------------
# User helper
# ---------------------------------------------------------------------------
def get_user_by_email(email):
    """Fetch user by email, or return None."""
    # import here to avoid circular import at module import time
    from webapp.models import User

    if not email:
        return None
    return User.query.filter_by(email=email.lower()).first()
