# shared/utils.py
"""
general-purpose helpers for astro-ph digest.
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
    """safely load YAML into a python object."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[load_yaml] error reading {path}: {e}")
        return {}


def save_yaml(path, data):
    """persist python data to YAML."""
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
    construct an arXiv API query string given keywords.
    example: https://export.arxiv.org/api/query?search_query=all:black+hole&sortBy=submittedDate
    """
    base = "https://export.arxiv.org/api/query?"
    if not keywords:
        return base + "search_query=cat:astro-ph&sortBy=submittedDate&sortOrder=descending"

    query = "+OR+".join(f"all:{kw}" for kw in keywords)
    return (
        f"{base}search_query={query}"
        f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    )


_ARG_FIX_RE = re.compile(
    r"\\(?P<cmd>dot|ddot|hat|bar|tilde|vec|breve|check|acute|grave|widehat|widetilde|overline|underline)"
    r"(?!\s*\{)\s*"
    r"(?P<arg>(?:\\[A-Za-z]+(?:\{[^}]+\})?)|[A-Za-z0-9])"
)


def wrap_inline_tex(text: str) -> str:
    """
    wrap bare TeX commands (e.g. \\dot{M}) in $...$ so MathJax/KaTeX can render them.
    """
    if not text:
        return text

    # normalize a few common TeX shorthands from arXiv summaries
    text = text.replace("\\~", "\\sim ")
    text = re.sub(r"\}(?=[A-Za-z0-9])", "} ", text)

    # ensure commands that require an argument actually receive one
    def _fix_missing_args(match: re.Match[str]) -> str:
        cmd = match.group("cmd")
        arg = match.group("arg").strip()
        return f"\\{cmd}{{{arg}}}"

    text = _ARG_FIX_RE.sub(_fix_missing_args, text)

    out: list[str] = []
    i = 0
    in_math = False
    length = len(text)

    def _consume_braced(src: str, start: int) -> tuple[str, int]:
        """return balanced braced sequence starting at start (which should point to '{')."""
        depth = 0
        idx = start
        buf: list[str] = []
        while idx < length:
            ch = src[idx]
            buf.append(ch)
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    idx += 1
                    break
            idx += 1
        return ("".join(buf), idx)

    while i < length:
        ch = text[i]
        if ch == "$":
            in_math = not in_math
            out.append(ch)
            i += 1
            continue

        if ch == "\\" and not in_math:
            j = i + 1
            while j < length and text[j].isalpha():
                j += 1

            if j == i + 1:
                out.append(ch)
                i += 1
                continue

            cmd = text[i:j]
            if cmd in {"\\n", "\\r"}:
                out.append(cmd)
                i = j
                continue

            expr_parts = [cmd]
            idx = j

            # attach balanced brace groups immediately following command
            while idx < length and text[idx] == "{":
                braced, idx = _consume_braced(text, idx)
                expr_parts.append(braced)

            # attach bare identifiers if present (e.g., \alpha r, \tilde x)
            while idx < length and text[idx].isalnum():
                expr_parts.append(text[idx])
                idx += 1

            # include trailing sub/superscripts
            while idx < length and text[idx] in {"_", "^"}:
                marker = text[idx]
                expr_parts.append(marker)
                idx += 1
                if idx < length and text[idx] == "{":
                    braced, idx = _consume_braced(text, idx)
                    expr_parts.append(braced)
                elif idx < length:
                    expr_parts.append(text[idx])
                    idx += 1

            expr = "".join(expr_parts)
            out.append(f"${expr}$")
            i = idx
            continue

        out.append(ch)
        i += 1

    wrapped = "".join(out).replace("$ $", "$")
    return wrapped


def fetch_arxiv_feed(url):
    """fetch and parse the arXiv API XML feed, returning a list of papers."""
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
# user helper
# ---------------------------------------------------------------------------
def get_user_by_email(email):
    """fetch user by email, or return None."""
    # import here to avoid circular import at module import time
    from webapp.models import User

    if not email:
        return None
    return User.query.filter_by(email=email.lower()).first()
