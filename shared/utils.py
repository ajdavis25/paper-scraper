# shared/utils.py
"""
general-purpose helpers for astro-ph digest.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Tuple

import requests
import yaml
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
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$")
_SUBSUP_TOKEN_PATTERN = re.compile(
    r"(?<![\w$])([A-Za-z0-9]+(?:_(?:\{[^}]+\}|[A-Za-z0-9]+)|\^(?:\{[^}]+\}|[A-Za-z0-9]+))+)"
)


def _load_latex_symbols() -> dict[str, str]:
    data_path = Path(__file__).resolve().parent / "latex_symbols.json"
    try:
        with data_path.open("r", encoding="utf-8") as f:
            raw: dict[str, str] = json.load(f)
    except FileNotFoundError:
        print(f"[latex] warning: symbol map {data_path} missing; using minimal fallback.")
        raw = {}

    normalized = {k.replace("\\\\", "\\"): v for k, v in raw.items()}
    normalized.update(
        {
            "\\degree": "°",
            "\\deg": "°",
            "\\textdegree": "°",
        }
    )
    return normalized


LATEX_SYMBOLS = _load_latex_symbols()


_TEXT_MODE_COMMANDS = {"\\cal", "\\rm", "\\bf", "\\it"}


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
        if ch in "{}" and not in_math:
            i += 1
            continue
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
            if cmd in _TEXT_MODE_COMMANDS:
                i = j
                continue
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

        if ch == " ":
            if not out or out[-1].endswith(" "):
                i += 1
                continue
        out.append(ch)
        i += 1

    wrapped = "".join(out)

    segments = wrapped.split("$")
    for idx in range(0, len(segments), 2):
        segments[idx] = _SUBSUP_TOKEN_PATTERN.sub(
            lambda m: f"${m.group(1)}$", segments[idx]
        )

    wrapped = "$".join(segments).replace("$ $", "$")
    return wrapped




def _to_superscript(text: str) -> str:
    if not text:
        return ""

    result = []
    fallback = []
    for ch in text:
        mapped = _SUPERSCRIPT_MAP.get(ch)
        if mapped:
            if fallback:
                result.append("\u207d" + "".join(fallback) + "\u207e")
                fallback = []
            result.append(mapped)
        else:
            fallback.append(ch)
    if fallback:
        result.append("\u207d" + "".join(fallback) + "\u207e")
    return "".join(result)


def _to_subscript(text: str) -> str:
    if not text:
        return ""

    result = []
    fallback = []
    for ch in text:
        mapped = _SUBSCRIPT_MAP.get(ch)
        if mapped:
            if fallback:
                result.append("\u208d" + "".join(fallback) + "\u208e")
                fallback = []
            result.append(mapped)
        else:
            fallback.append(ch)
    if fallback:
        result.append("\u208d" + "".join(fallback) + "\u208e")
    return "".join(result)


EXTRA_LATEX_SYMBOLS = {
    "\\ln": "ln",
    "\\log": "log",
    "\\exp": "exp",
    "\\sin": "sin",
    "\\cos": "cos",
    "\\tan": "tan",
    "\\min": "min",
    "\\max": "max",
    "\\operatorname": "",
}

LATEX_SYMBOLS.update(EXTRA_LATEX_SYMBOLS)

ACCENT_COMBINERS = {
    "dot": "\u0307",
    "ddot": "\u0308",
    "hat": "\u0302",
    "widehat": "\u0302",
    "tilde": "\u0303",
    "widetilde": "\u0303",
    "bar": "\u0304",
    "overline": "\u0305",
    "breve": "\u0306",
    "check": "\u030c",
    "acute": "\u0301",
    "grave": "\u0300",
    "vec": "\u20d7",
    "underline": "\u0332",
}

_SUPERSCRIPT_MAP = {
    "0": "\u2070",
    "1": "\u00b9",
    "2": "\u00b2",
    "3": "\u00b3",
    "4": "\u2074",
    "5": "\u2075",
    "6": "\u2076",
    "7": "\u2077",
    "8": "\u2078",
    "9": "\u2079",
    "+": "\u207a",
    "-": "\u207b",
    "=": "\u207c",
    "(": "\u207d",
    ")": "\u207e",
    "n": "\u207f",
    "i": "\u2071",
    "j": "\u02b2",
    "k": "\u1d4f",
    "m": "\u1d50",
    "a": "\ua731",
    "b": "\u1d47",
    "c": "\u1d9c",
    "d": "\u1d48",
    "e": "\u1d49",
    "f": "\u1da0",
    "g": "\u1d4d",
    "h": "\u02b0",
    "l": "\u02e1",
    "o": "\u1d52",
    "p": "\u1d56",
    "r": "\u02b3",
    "s": "\u02e2",
    "t": "\u1d57",
    "u": "\u1d58",
    "v": "\u1d5b",
    "w": "\u02b7",
    "x": "\u02e3",
    "y": "\u02b8",
    "z": "\u1dbb",
}

_SUBSCRIPT_MAP = {
    "0": "\u2080",
    "1": "\u2081",
    "2": "\u2082",
    "3": "\u2083",
    "4": "\u2084",
    "5": "\u2085",
    "6": "\u2086",
    "7": "\u2087",
    "8": "\u2088",
    "9": "\u2089",
    "+": "\u208a",
    "-": "\u208b",
    "=": "\u208c",
    "(": "\u208d",
    ")": "\u208e",
    "a": "\u2090",
    "e": "\u2091",
    "h": "\u2095",
    "i": "\u1d62",
    "j": "\u2c7c",
    "k": "\u2096",
    "l": "\u2097",
    "m": "\u2098",
    "n": "\u2099",
    "o": "\u2092",
    "p": "\u209a",
    "r": "\u1d63",
    "s": "\u209b",
    "t": "\u209c",
    "u": "\u1d64",
    "v": "\u1d65",
    "x": "\u2093",
}
def _read_group(expr: str, idx: int) -> Tuple[str, int]:
    if idx >= len(expr) or expr[idx] != "{":
        return "", idx
    depth = 0
    buf = []
    while idx < len(expr):
        ch = expr[idx]
        buf.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                idx += 1
                break
        idx += 1
    return "".join(buf)[1:-1], idx


def _apply_accent(cmd: str, content: str) -> str:
    comb = ACCENT_COMBINERS.get(cmd)
    if not comb:
        return content
    return "".join(char + comb for char in content)


def latex_to_plain(expr: str) -> str:
    result = []
    i = 0
    length = len(expr)

    text_commands = {
        "\\mathrm",
        "\\textrm",
        "\\text",
        "\\textbf",
        "\\textit",
        "\\operatorname",
        "\\mathbf",
        "\\mathcal",
        "\\mathbb",
        "\\mathtt",
        "\\mathit",
        "\\rm",
        "\\bf",
        "\\emph",
        "\\cal",
    }

    while i < length:
        ch = expr[i]
        if ch == "\\":
            j = i + 1
            while j < length and expr[j].isalpha():
                j += 1
            cmd = expr[i:j]
            bare_cmd = cmd.strip("\\")

            if cmd in LATEX_SYMBOLS:
                result.append(LATEX_SYMBOLS[cmd])
                i = j
                continue
            if bare_cmd in ACCENT_COMBINERS:
                content, next_idx = _read_group(expr, j)
                if content:
                    result.append(_apply_accent(bare_cmd, latex_to_plain(content)))
                    i = next_idx
                    continue
            if cmd == "\\frac":
                num, after_num = _read_group(expr, j)
                den, after_den = _read_group(expr, after_num)
                if num and den:
                    result.append(f"({latex_to_plain(num)})/({latex_to_plain(den)})")
                    i = after_den
                    continue
            if cmd == "\\sqrt":
                radicand, next_idx = _read_group(expr, j)
                if radicand:
                    result.append(f"√({latex_to_plain(radicand)})")
                    i = next_idx
                    continue
            if cmd == "\\cal":
                i = j
                while i < length and expr[i].isspace():
                    i += 1
                continue
            if cmd in text_commands:
                content, next_idx = _read_group(expr, j)
                if content:
                    result.append(latex_to_plain(content))
                    i = next_idx
                    continue
            if cmd in {"\\left", "\\right"}:
                i = j
                continue
            # unrecognised command: drop backslash and keep text
            result.append(expr[i + 1 : j])
            i = j
            continue
        elif ch == "^":
            if i + 1 < length and expr[i + 1] == "{":
                content, next_idx = _read_group(expr, i + 1)
                result.append(_to_superscript(latex_to_plain(content)))
                i = next_idx
            else:
                j = i + 1
                token = []
                while j < length and (expr[j].isalnum() or expr[j] in {"'", "\\"}):
                    token.append(expr[j])
                    j += 1
                result.append(_to_superscript("".join(token)))
                i = j
            continue
        elif ch == "_":
            if i + 1 < length and expr[i + 1] == "{":
                content, next_idx = _read_group(expr, i + 1)
                result.append(_to_subscript(latex_to_plain(content)))
                i = next_idx
            else:
                j = i + 1
                token = []
                while j < length and (expr[j].isalnum() or expr[j] in {"'", "\\"}):
                    token.append(expr[j])
                    j += 1
                result.append(_to_subscript("".join(token)))
                i = j
            continue
        elif ch in "{}":
            i += 1
            continue
        else:
            result.append(ch)
            i += 1

    return "".join(result)


def render_inline_math_html(text: str) -> Tuple[str, bool]:
    """
    convert inline math ($...$) to KaTeX HTML spans suitable for email clients.
    returns (processed_html, math_found).
    """
    if not text or "$" not in text:
        return text, False

    math_found = False

    def repl(match: re.Match[str]) -> str:
        nonlocal math_found
        expr = match.group(1).strip()
        plain = latex_to_plain(expr)
        if plain:
            math_found = True
            return f"<span class=\"math-inline\">{html.escape(plain)}</span>"
        return match.group(0)

    return _INLINE_MATH_RE.sub(repl, text), math_found


def fetch_arxiv_feed(url):
    """fetch and parse the arXiv API XML feed, returning a list of papers."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }

        entries = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            link = entry.find("atom:id", ns)
            published = entry.find("atom:published", ns)

            author_names = []
            for author in entry.findall("atom:author", ns):
                name_el = author.find("atom:name", ns)
                if name_el is not None and (name_text := (name_el.text or "").strip()):
                    author_names.append(name_text)

            categories = [
                cat.attrib.get("term", "").strip()
                for cat in entry.findall("atom:category", ns)
                if cat.attrib.get("term")
            ]
            primary_el = entry.find("arxiv:primary_category", ns)
            primary_category = (
                (primary_el.attrib.get("term") or "").strip()
                if primary_el is not None
                else (categories[0] if categories else "")
            )

            summary_text = summary.text.strip() if summary is not None else ""
            entries.append(
                {
                    "title": title.text.strip() if title is not None else "(no title)",
                    "summary": wrap_inline_tex(summary_text),
                    "link": link.text.strip() if link is not None else "#",
                    "published": published.text.strip() if published is not None else "",
                    "authors": author_names,
                    "categories": categories,
                    "primary_category": primary_category,
                    "category": primary_category,
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
