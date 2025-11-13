#!/usr/bin/env python3
"""
purge disposable/test inboxes from the user + subscriber tables.

usage (defaults cover the known throwaway domains):

    python scripts/purge_test_emails.py --yes

add more targets with repeated `--domain foo.com` or `--email someone@foo.com`.
pass `--dry-run` to preview without deleting.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys

root_str = str(PROJECT_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from webapp import create_app
from webapp.models import Subscriber, User
from shared.db import db


DEFAULT_DOMAINS = {"fantastu.com", "wivstore.com", "nyfhk.com"}
DEFAULT_EMAILS = {"test@test.com"}


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _extract_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[1]


def _should_purge(email: str, exact: set[str], domains: set[str]) -> bool:
    normalized = _normalize_email(email)
    if not normalized:
        return False
    if normalized in exact:
        return True
    domain = _extract_domain(normalized)
    return domain in domains


@dataclass
class PurgeResult:
    label: str
    model: type
    matches: Sequence[tuple[int, str]]

    def describe(self) -> str:
        if not self.matches:
            return f"[purge] {self.label}: no matches."
        listing = "\n".join(
            f"    - id={row_id:>4}  {email}"
            for row_id, email in self.matches
        )
        return f"[purge] {self.label}: {len(self.matches)} match(es):\n{listing}"


def collect_targets(exact: set[str], domains: set[str]) -> list[PurgeResult]:
    app = create_app()
    results: list[PurgeResult] = []

    with app.app_context():
        users = [
            (row.id, row.email)
            for row in User.query.all()
            if _should_purge(row.email, exact, domains)
        ]
        subscribers = [
            (row.id, row.email)
            for row in Subscriber.query.all()
            if _should_purge(row.email, exact, domains)
        ]
        results.append(PurgeResult("user", User, users))
        results.append(PurgeResult("subscriber", Subscriber, subscribers))
    return results


def perform_purge(results: Iterable[PurgeResult]) -> int:
    """
    delete the collected rows. returns the number of removed records overall.
    """
    total = 0
    app = create_app()

    with app.app_context():
        for result in results:
            if not result.matches:
                continue
            ids = [row_id for row_id, _ in result.matches]
            rows = result.model.query.filter(result.model.id.in_(ids)).all()
            for row in rows:
                db.session.delete(row)
                total += 1
        if total:
            db.session.commit()
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="delete throwaway/test inboxes from the DB")
    parser.add_argument("--domain", action="append", dest="domains", default=[], help="domain to purge")
    parser.add_argument("--email", action="append", dest="emails", default=[], help="exact email to purge")
    parser.add_argument(
        "--no-defaults",
        action="store_true",
        help="only use values supplied via --domain/--email",
    )
    parser.add_argument("--dry-run", action="store_true", help="list matches without deleting")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive confirmation prompt",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    domains = {d.strip().lstrip("@").lower() for d in args.domains if d and d.strip()}
    emails = {_normalize_email(e) for e in args.emails if e and e.strip()}

    if not args.no_defaults:
        domains.update(DEFAULT_DOMAINS)
        emails.update(DEFAULT_EMAILS)

    if not domains and not emails:
        print("[purge] no domains/emails supplied; nothing to do.")
        return

    print(f"[purge] targeting domains: {sorted(domains)}")
    print(f"[purge] targeting exact emails: {sorted(emails)}")

    results = collect_targets(emails, domains)
    any_matches = False
    for result in results:
        desc = result.describe()
        print(desc)
        if result.matches:
            any_matches = True

    if not any_matches:
        print("[purge] done (no matching rows).")
        return

    if args.dry_run:
        print("[purge] dry run requested; exiting without deleting.")
        return

    if not args.yes:
        try:
            confirmed = input("Delete the rows listed above? type 'yes' to continue: ").strip().lower()
        except KeyboardInterrupt:
            print("\n[purge] aborted.")
            return
        if confirmed != "yes":
            print("[purge] aborted (confirmation mismatch).")
            return

    removed = perform_purge(results)
    print(f"[purge] deleted {removed} record(s).")


if __name__ == "__main__":
    main()
