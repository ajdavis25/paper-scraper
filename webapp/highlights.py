#!/usr/bin/env python3
"""helpers for trending highlight emails and dashboard feeds."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable, Sequence
import xml.etree.ElementTree as ET

import requests
from sqlalchemy import func

from shared.db import db
from webapp.models import Feedback, Paper, PreferenceConfig, User

_TITLE_BATCH_SIZE = 20
_HIGHLIGHT_FETCH_LIMIT = 1500
_DEFAULT_CATEGORY_CACHE: tuple[str, ...] | None = None


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_categories(values: Iterable[str] | None) -> set[str]:
    normalized: set[str] = set()
    if not values:
        return normalized
    for raw in values:
        clean = (str(raw) if raw is not None else "").strip()
        if not clean:
            continue
        normalized.add(clean.lower())
    return normalized


def _has_category_overlap(source: set[str], targets: set[str]) -> bool:
    if not source or not targets:
        return False
    for src in source:
        for tgt in targets:
            if (
                src == tgt
                or src.startswith(f"{tgt}.")
                or tgt.startswith(f"{src}.")
            ):
                return True
    return False


def _default_categories() -> list[str]:
    """return cached default categories (user_id NULL row)."""
    global _DEFAULT_CATEGORY_CACHE
    if _DEFAULT_CATEGORY_CACHE is not None:
        return list(_DEFAULT_CATEGORY_CACHE)

    cfg = PreferenceConfig.query.filter_by(user_id=None).first()
    cats = [c for c in (cfg.categories if cfg else []) or [] if c]
    if not cats:
        cats = ["astro-ph"]
    _DEFAULT_CATEGORY_CACHE = tuple(cats)
    return list(_DEFAULT_CATEGORY_CACHE)


def _load_category_map(emails: set[str]) -> dict[str, set[str]]:
    """load normalized category sets for given normalized emails."""
    if not emails:
        return {}
    rows = (
        db.session.query(
            func.lower(User.email).label("email"),
            PreferenceConfig.categories,
        )
        .outerjoin(PreferenceConfig, PreferenceConfig.user_id == User.id)
        .filter(func.lower(User.email).in_(list(emails)))
        .all()
    )
    default_norm = _normalize_categories(_default_categories())
    mapping: dict[str, set[str]] = {}
    for row in rows:
        email = (row.email or "").strip()
        cats = _normalize_categories(row.categories or []) or set(default_norm)
        mapping[email] = cats
    return mapping


def get_user_interest_categories(user: User | None) -> list[str]:
    """fetch persisted categories for a user, falling back to defaults."""
    if not user:
        return []
    pref = PreferenceConfig.query.filter_by(user_id=user.id).first()
    if pref and pref.categories:
        return list(pref.categories)
    return _default_categories()


def fetch_arxiv_titles(arxiv_ids: Sequence[str]) -> dict[str, str]:
    """fetch title metadata for arXiv ids that lack local metadata."""
    ids = [aid for aid in (arxiv_ids or []) if aid]
    if not ids:
        return {}

    titles: dict[str, str] = {}
    base_url = "https://export.arxiv.org/api/query"
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for i in range(0, len(ids), _TITLE_BATCH_SIZE):
        chunk = ids[i : i + _TITLE_BATCH_SIZE]
        params = {"id_list": ",".join(chunk)}
        try:
            resp = requests.get(base_url, params=params, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            for entry in root.findall("atom:entry", ns):
                entry_id = entry.find("atom:id", ns)
                raw_id = (entry_id.text or "").strip() if entry_id is not None else ""
                arxiv_id = raw_id.split("/abs/")[-1] if raw_id else ""
                title_el = entry.find("atom:title", ns)
                title_text = (
                    (title_el.text or "").strip() if title_el is not None else ""
                )
                if arxiv_id and title_text:
                    titles[arxiv_id] = title_text
        except Exception as exc:
            print(f"[highlights] failed to fetch arxiv titles: {exc}")

    return titles


def _hydrate_missing_titles(paper_map: dict[str, Paper]) -> None:
    missing = [
        arxiv_id
        for arxiv_id, paper in paper_map.items()
        if not (paper.title or "").strip()
    ]
    if not missing:
        return

    fetched = fetch_arxiv_titles(missing)
    if not fetched:
        return

    updated = False
    for arxiv_id, title in fetched.items():
        paper = paper_map.get(arxiv_id)
        if paper:
            paper.title = title
            updated = True
        else:
            paper = Paper(
                arxiv_id=arxiv_id,
                title=title,
                link=f"https://arxiv.org/abs/{arxiv_id}",
            )
            db.session.add(paper)
            paper_map[arxiv_id] = paper
            updated = True

    if updated:
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"[highlights] failed to persist fetched titles: {exc}")


def _aggregate_feedback_rows(
    rows,
    *,
    category_map: dict[str, set[str]],
    target_categories: set[str] | None,
    exclude_emails: set[str],
) -> dict[str, dict]:
    stats: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "last_ts": None, "emails": set()}
    )
    for arxiv_id, timestamp, email in rows:
        clean_id = (arxiv_id or "").strip()
        if not clean_id:
            continue
        normalized_email = _normalize_email(email)
        if normalized_email in exclude_emails:
            continue

        if target_categories:
            user_cats = category_map.get(normalized_email)
            if not user_cats or not _has_category_overlap(user_cats, target_categories):
                continue

        entry = stats[clean_id]
        entry["count"] += 1
        entry["emails"].add(normalized_email)
        ts = timestamp if isinstance(timestamp, datetime) else None
        if ts and (entry["last_ts"] is None or ts > entry["last_ts"]):
            entry["last_ts"] = ts
    return stats


def _select_top_ids(stats_map: dict[str, dict], limit: int, min_likes: int) -> list[str]:
    filtered = [
        (aid, data)
        for aid, data in stats_map.items()
        if data["count"] >= min_likes
    ]
    if not filtered and min_likes > 1:
        filtered = [
            (aid, data) for aid, data in stats_map.items() if data["count"] >= 1
        ]
    filtered.sort(
        key=lambda item: (
            item[1]["count"],
            item[1]["last_ts"] or datetime.min,
        ),
        reverse=True,
    )
    return [aid for aid, _ in filtered[:limit]]


def compute_recent_highlights(
    *,
    target_categories: Sequence[str] | None,
    window_days: int = 7,
    limit: int = 5,
    exclude_emails: Iterable[str] | None = None,
    include_global_fallback: bool = True,
    min_likes: int = 2,
) -> list[dict]:
    """
    return anonymized highlight entries filtered by overlapping categories.
    falls back to global trending entries when no similar-user likes exist.
    """
    cutoff = datetime.utcnow() - timedelta(days=max(window_days, 1))
    limit = max(1, min(limit, 15))
    normalized_targets = _normalize_categories(target_categories or [])
    exclude_set = {_normalize_email(e) for e in (exclude_emails or []) if e}

    rows = (
        db.session.query(
            Feedback.arxiv_id,
            Feedback.timestamp,
            Feedback.email,
        )
        .filter(
            Feedback.type == "recommendation",
            Feedback.liked.is_(True),
            Feedback.timestamp >= cutoff,
        )
        .order_by(Feedback.timestamp.desc())
        .limit(min(limit * 80, _HIGHLIGHT_FETCH_LIMIT))
        .all()
    )
    if not rows:
        return []

    email_keys = {_normalize_email(email) for _, _, email in rows if email}
    category_map = _load_category_map(email_keys)

    targeted_stats = _aggregate_feedback_rows(
        rows,
        category_map=category_map,
        target_categories=normalized_targets if normalized_targets else None,
        exclude_emails=exclude_set,
    )

    stats_map = targeted_stats
    if (not stats_map or not _select_top_ids(stats_map, limit, min_likes)) and include_global_fallback:
        stats_map = _aggregate_feedback_rows(
            rows,
            category_map=category_map,
            target_categories=None,
            exclude_emails=exclude_set,
        )
        # relax minimum likes when falling back so we always show something.
        min_likes = min(min_likes, 2)

    selected_ids = _select_top_ids(stats_map, limit, min_likes)
    if not selected_ids:
        return []

    paper_rows = (
        Paper.query.filter(Paper.arxiv_id.in_(selected_ids)).all()
    )
    paper_map = {paper.arxiv_id: paper for paper in paper_rows}
    for arxiv_id in selected_ids:
        if arxiv_id not in paper_map:
            paper_map[arxiv_id] = Paper(
                arxiv_id=arxiv_id,
                link=f"https://arxiv.org/abs/{arxiv_id}",
            )
            db.session.add(paper_map[arxiv_id])

    _hydrate_missing_titles(paper_map)

    entries: list[dict] = []
    for arxiv_id in selected_ids:
        stats = stats_map.get(arxiv_id)
        if not stats:
            continue
        paper = paper_map.get(arxiv_id)
        title = (paper.title or "").strip() if paper else ""
        link = (paper.link or "").strip() if paper else ""
        if not link:
            link = f"https://arxiv.org/abs/{arxiv_id}"
        entries.append(
            {
                "arxiv_id": arxiv_id,
                "title": title or f"arXiv:{arxiv_id}",
                "link": link,
                "like_count": stats["count"],
                "unique_fans": len(stats["emails"]),
                "last_liked_at": stats["last_ts"],
                "window_days": window_days,
            }
        )
    return entries

