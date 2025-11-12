#!/usr/bin/env python3
"""
utility script to (re)issue a gmail users.watch call and store the resulting historyId.
"""
from __future__ import annotations

import argparse, os, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
from shared.gmail_push import fetch_access_token, start_watch, GmailPushError  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Gmail push watch configuration.")
    parser.add_argument(
        "--topic",
        default=os.getenv("GMAIL_WATCH_TOPIC"),
        help="Pub/Sub topic name (projects/.../topics/...). Defaults to GMAIL_WATCH_TOPIC env var.",
    )
    parser.add_argument(
        "--label",
        default=os.getenv("GMAIL_WATCH_LABEL"),
        help="Optional Gmail label ID to filter on (e.g., Label_123). Defaults to GMAIL_WATCH_LABEL env var.",
    )
    args = parser.parse_args()

    if not args.topic:
        print("error: topic is required (pass --topic or set GMAIL_WATCH_TOPIC)", file=sys.stderr)
        return 1

    try:
        token = fetch_access_token()
        payload = start_watch(token, topic=args.topic, label_ids=[args.label] if args.label else None)
    except GmailPushError as exc:
        print(f"[gmail-watch] failed to start watch: {exc}", file=sys.stderr)
        return 2

    history_id = payload.get("historyId")
    expiration = payload.get("expiration")
    print(f"[gmail-watch] watch registered. historyId={history_id} expiration={expiration}")

    try:
        from webapp import create_app
        from webapp.models import GmailWatchState
        from shared.db import db  # noqa: F401
    except Exception as exc:
        print(f"[gmail-watch] warning: unable to persist history id (imports failed: {exc})")
        return 0

    app = create_app()
    with app.app_context():
        GmailWatchState.update_history(history_id, label_id=args.label)
        print("[gmail-watch] stored latest history id in database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
