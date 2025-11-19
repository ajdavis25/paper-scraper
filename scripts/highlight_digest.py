#!/usr/bin/env python3
"""
highlight_digest.py
-------------------

send daily/weekly highlight recaps showcasing "top liked papers from users like you".
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import sys
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bot
from bot import (
    _normalize_email,
    _standardize_preferences,
    load_config,
    load_db_recipients,
)
from curator import merge_preferences
from mailer import send_email
from webapp import create_app
from webapp.highlights import compute_recent_highlights


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="send highlight recap emails.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="path to config.yaml (defaults to ./config.yaml)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="max highlight entries per section (default: 5)",
    )
    parser.add_argument(
        "--frequency",
        choices=["daily", "weekly", "both"],
        default="both",
        help="which highlight windows to include",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print emails instead of sending",
    )
    return parser.parse_args()


def _build_fallback_prefs(cfg: dict) -> dict:
    merged = merge_preferences(cfg.get("preferences", {}))
    fallback = _standardize_preferences(merged)
    if not fallback.get("categories"):
        fallback["categories"] = (
            cfg.get("arxiv", {}).get("categories")
            or fallback.get("categories")
            or ["astro-ph"]
        )
    return fallback


def _extend_with_manual_recipients(cfg: dict, profiles: dict, fallback: dict) -> dict:
    email_cfg = cfg.setdefault("output", {}).setdefault("email", {})
    manual_addrs = [
        addr.strip()
        for addr in email_cfg.get("to_addrs", [])
        if addr and addr.strip()
    ]
    for addr in manual_addrs:
        normalized = _normalize_email(addr)
        if not normalized:
            continue
        if normalized in profiles:
            profiles[normalized].setdefault("send_to", addr)
            continue
        fallback_clone = _standardize_preferences(fallback)
        profiles[normalized] = {
            "prefs": fallback_clone,
            "categories": fallback_clone.get("categories") or [],
            "send_to": addr,
            "feedback_weights": {},
        }
    return profiles


def _window_defs(kind: str) -> list[tuple[str, int]]:
    windows: list[tuple[str, int]] = []
    if kind in {"daily", "both"}:
        windows.append(("daily", 1))
    if kind in {"weekly", "both"}:
        windows.append(("weekly", 7))
    return windows


def _render_section(label: str, days: int, entries: list[dict]) -> tuple[str, str]:
    heading = f"{label.capitalize()} highlights (last {days} day{'s' if days != 1 else ''})"
    text_lines = [heading]
    html_parts = [f"<h3>{heading}</h3>"]
    if not entries:
        text_lines.append("  - no highlights yet. keep the likes coming!")
        html_parts.append('<p style="color:#777;">no highlights yet -- keep the likes coming!</p>')
        return "\n".join(text_lines), "".join(html_parts)

    text_lines.append("")
    html_parts.append("<ol>")
    for item in entries:
        title = item.get("title") or f"arXiv:{item.get('arxiv_id')}"
        like_count = item.get("like_count", 0)
        fans = item.get("unique_fans", 0)
        when = item.get("last_liked_at")
        when_str = when.strftime("%Y-%m-%d %H:%M") if when else "recently"
        link = item.get("link")
        text_lines.append(
            f"  - {title} ({like_count} likes, {fans} reader{'s' if fans != 1 else ''}, last liked {when_str})"
        )
        html_parts.append(
            "<li>"
            f'<a href="{link}" target="_blank">{title}</a>'
            f'<div style="font-size:0.9rem;color:#666;">'
            f"{like_count} like{'s' if like_count != 1 else ''} &middot; "
            f"{fans} reader{'s' if fans != 1 else ''} &middot; "
            f"last liked {when_str}"
            "</div>"
            "</li>"
        )
    html_parts.append("</ol>")
    return "\n".join(text_lines), "".join(html_parts)


def _build_email_body(recipient: str, sections: list[tuple[str, int, list[dict]]]) -> tuple[str, str]:
    greeting = f"hi {recipient},"
    intro = (
        "here's what other subscribers with similar interests liked recently."
    )
    outro = (
        "want to see more? peek at your dashboard for fresh recs."
    )
    text_blocks = [greeting, "", intro, ""]
    html_parts = [
        f"<p>{greeting}</p>",
        f"<p>{intro}</p>",
    ]
    for label, days, entries in sections:
        section_text, section_html = _render_section(label, days, entries)
        text_blocks.append(section_text)
        text_blocks.append("")
        html_parts.append(section_html)
    html_parts.append(f"<p>{outro}</p>")
    text_blocks.append(outro)
    return "\n".join(text_blocks).strip(), "".join(html_parts)


def main():
    args = parse_args()
    cfg = load_config(args.config)
    fallback = _build_fallback_prefs(cfg)
    app = create_app()
    bot._FLASK_APP = app
    profiles = load_db_recipients(fallback)
    profiles = _extend_with_manual_recipients(cfg, profiles, fallback)
    if not profiles:
        print("[highlight-digest] no subscriber profiles found; aborting.")
        return

    email_cfg = cfg.setdefault("output", {}).setdefault("email", {})
    subject_prefix = email_cfg.get("subject_prefix", "[arxiv digest]").strip()
    subject_suffix = dt.datetime.utcnow().strftime("%b %d")
    windows = _window_defs(args.frequency)
    dashboard_base = email_cfg.get(
        "dashboard_base", "https://paperscraper-one.vercel.app/dashboard"
    )

    sent = 0
    with app.app_context():
        for key in sorted(profiles):
            profile = profiles[key]
            actual_email = (profile.get("send_to") or key).strip()
            if not actual_email:
                continue
            sections: list[tuple[str, int, list[dict]]] = []
            for label, days in windows:
                highlights = compute_recent_highlights(
                    target_categories=profile.get("categories"),
                    window_days=days,
                    limit=args.limit,
                    exclude_emails=[actual_email],
                )
                sections.append((label, days, highlights))

            if all(len(entries) == 0 for _, _, entries in sections):
                print(f"[highlight-digest] skipping {actual_email} (no highlights yet)")
                continue

            text_body, html_body = _build_email_body(actual_email, sections)
            dashboard_url = f"{dashboard_base}/{quote_plus(actual_email)}"
            text_body += f"\n\ndashboard -> {dashboard_url}"
            html_body += (
                f'<p><a href="{dashboard_url}" target="_blank">'
                "open your dashboard</a></p>"
            )

            subject = f"{subject_prefix} highlights from readers like you ({subject_suffix})".strip()
            if args.dry_run:
                print("=" * 60)
                print(f"[dry-run] to={actual_email}")
                print(text_body)
                continue

            ok = send_email(
                cfg,
                subject,
                text_body,
                html_body,
                to_override=[actual_email],
                context="highlights-digest",
            )
            if ok:
                sent += 1
                print(f"[highlight-digest] sent highlights to {actual_email}")
            else:
                print(f"[highlight-digest] FAILED to send highlights to {actual_email}")

    if not args.dry_run:
        print(f"[highlight-digest] finished: sent {sent} email(s).")


if __name__ == "__main__":
    main()
