#!/usr/bin/env python3
"""
seed_feedback.py
----------------

load a small sample of like/dislike reactions into the local database so
developers can see meaningful rows on /view-feedback. by default it reads
assets/sample_feedback.json, but you can pass --path to point to any JSON file
with entries shaped like:

[
  {
    "email": "alice@example.com",
    "arxiv_id": "2101.12345v1",
    "liked": true,
    "timestamp": "2025-11-19 00:44",
    "source": "recommendations"
  }
]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from webapp import create_app  # noqa: E402
from webapp.account_utils import ensure_user_stub  # noqa: E402
from webapp.models import Feedback  # noqa: E402
from webapp.routes_frontend import _record_recommendation_feedback  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed feedback rows for local dev.")
    parser.add_argument(
        "--path",
        default="assets/sample_feedback.json",
        help="JSON file containing an array of feedback entries.",
    )
    return parser.parse_args()


def load_entries(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path} did not contain a JSON list.")
    return data


def main():
    args = parse_args()
    payload_path = Path(args.path)
    if not payload_path.exists():
        raise SystemExit(f"could not find {payload_path}")

    entries = load_entries(payload_path)
    if not entries:
        print(f"[seed-feedback] no entries in {payload_path}")
        return

    app = create_app()
    with app.app_context():
        inserted = 0
        for entry in entries:
            email = entry.get("email")
            arxiv_id = entry.get("arxiv_id")
            liked = bool(entry.get("liked"))
            source = entry.get("source") or "recommendations"
            ts_raw = entry.get("timestamp")
            if not email or not arxiv_id or not ts_raw:
                print(f"[seed-feedback] skipping malformed entry: {entry}")
                continue

            ensure_user_stub(email, commit=False)
            timestamp = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M")
            existing = (
                Feedback.query.filter_by(
                    email=email,
                    arxiv_id=arxiv_id,
                    type="recommendation",
                )
                .order_by(Feedback.timestamp.desc())
                .first()
            )
            if (
                existing
                and existing.timestamp == timestamp
                and bool(existing.liked) == liked
                and (existing.source or "recommendations") == source
            ):
                continue

            _record_recommendation_feedback(
                email=email,
                arxiv_id=arxiv_id,
                liked=liked,
                source=source,
                timestamp=timestamp,
            )
            inserted += 1

    print(f"[seed-feedback] inserted/updated {inserted} feedback rows from {payload_path}")


if __name__ == "__main__":
    main()
