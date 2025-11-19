import re, os, yaml, feedparser, requests, copy, time, tempfile, datetime as dt, argparse, gzip, math
from flask import json
from markupsafe import Markup
import json as pyjson  # stdlib json for caching
from filters import score_paper, match_category, _normalize as _normalize_pref_term
from mailer import send_email
from curator import merge_preferences
from sqlalchemy import func
from shared.db import db
from shared.utils import (
    wrap_inline_tex,
    render_inline_math_html,
    inline_math_to_plain,
    decode_unicode_escapes,
)

print(f"[arxiv bot] running: {__file__} SHA={os.environ.get('GITHUB_SHA', 'local')}")

# arXiv id pattern and canonical link helper
_ARXIV_ID_RE = re.compile(r'(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(v\d+)?', re.I)

# simple on-disk cache to avoid hammering arXiv during tests
CACHE_FILE = "cached_arxiv.json"
_CACHE_MAX_AGE = 4 * 3600
_CACHE_MIN_ITEMS = 10

_LAST_FETCH = 0
_MIN_INTERVAL = 3.0  # seconds between requests
_FEEDBACK_KEYWORD_WEIGHT = 0.3
_FEEDBACK_AUTHOR_WEIGHT = 0.5
_FLASK_APP = None


def _get_flask_app():
    global _FLASK_APP
    if _FLASK_APP is False:
        return None
    if _FLASK_APP is None:
        try:
            from webapp import create_app

            _FLASK_APP = create_app()
        except Exception as exc:
            print(f"[arxiv bot] unable to init flask app: {exc}")
            _FLASK_APP = False
    return _FLASK_APP or None


def _empty_feedback_weights():
    return {"keywords": {}, "authors": {}}


def _compute_feedback_weights(user, RecommendationSnapshot):
    """build keyword/author weight maps from prior feedback."""
    weights = _empty_feedback_weights()
    if not user:
        return weights

    snapshots = RecommendationSnapshot.query.filter(
        RecommendationSnapshot.user_id == user.id,
        RecommendationSnapshot.feedback.isnot(None),
    ).all()

    for snap in snapshots:
        delta = 1.0 if snap.feedback else -1.0
        for keyword in snap.matched_keywords or []:
            normalized = _normalize_pref_term(keyword)
            if not normalized:
                continue
            weights["keywords"][normalized] = (
                weights["keywords"].get(normalized, 0.0) + delta
            )
        for author in snap.matched_authors or []:
            normalized = _normalize_pref_term(author)
            if not normalized:
                continue
            weights["authors"][normalized] = (
                weights["authors"].get(normalized, 0.0) + delta
            )
    return weights


def _feedback_adjustment(details, keyword_bias, author_bias):
    bonus = 0.0
    matched_keywords = details.get("matched_any_keywords") or []
    matched_authors = details.get("matched_authors") or []
    for keyword in matched_keywords:
        normalized = _normalize_pref_term(keyword)
        if not normalized:
            continue
        bonus += keyword_bias.get(normalized, 0.0) * _FEEDBACK_KEYWORD_WEIGHT
    for author in matched_authors:
        normalized = _normalize_pref_term(author)
        if not normalized:
            continue
        bonus += author_bias.get(normalized, 0.0) * _FEEDBACK_AUTHOR_WEIGHT
    return bonus


def canon_abs_url(paper):
    """return canonical https://arxiv.org/abs/<id> for dict or arxiv.Result."""
    if isinstance(paper, dict):
        candidates = [paper.get("url"), paper.get("link"), paper.get("id")]
    else:
        candidates = [
            getattr(paper, "entry_id", None),
            getattr(paper, "link", None),
            getattr(paper, "id", None),
        ]

    for u in candidates:
        if not u:
            continue
        m = _ARXIV_ID_RE.search(str(u))
        if m:
            arxid = m.group(1) + (m.group(2) or "")
            return f"https://arxiv.org/abs/{arxid}"

    if isinstance(paper, dict) and paper.get("arxiv_id"):
        return f"https://arxiv.org/abs/{paper['arxiv_id']}"
    return ""

def _dedupe_preserve_order(items):
    seen = set()
    result = []
    for item in items or []:
        if item is None:
            continue
        key = item.lower() if isinstance(item, str) else item
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

def _clone_preferences(prefs):
    cloned = {}
    for key, value in (prefs or {}).items():
        if isinstance(value, list):
            cloned[key] = list(value)
        elif isinstance(value, dict):
            cloned[key] = copy.deepcopy(value)
        else:
            cloned[key] = value
    return cloned

def _combine_preferences(base, overrides):
    merged = {}
    base = base or {}
    overrides = overrides or {}
    for key in set(base) | set(overrides):
        base_val = base.get(key)
        override_val = overrides.get(key)
        if isinstance(override_val, list):
            if override_val:
                merged[key] = _dedupe_preserve_order(list(override_val))
            elif isinstance(base_val, list):
                merged[key] = _dedupe_preserve_order(list(base_val))
            else:
                merged[key] = []
        elif override_val not in (None, ""):
            merged[key] = override_val
        elif isinstance(base_val, list):
            merged[key] = _dedupe_preserve_order(list(base_val))
        else:
            merged[key] = base_val
    return merged

def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()

def load_config(path=None):
    """
    load yaml config, automatically detecting path from cli or repo layout.
    works both locally and in github actions.
    """

    # default fallbacks
    candidates = []
    if path:
        candidates.append(path)
    candidates += [
        "config.yaml",
        "./config.yaml",
        os.path.join(os.path.dirname(__file__), "config.yaml"),
        os.path.join(os.path.dirname(__file__), "astroph-bot", "config.yaml"),
        os.path.join(os.getcwd(), "astroph-bot", "config.yaml"),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            print(f"[arxiv bot] using config: {candidate}")
            with open(candidate, "r", encoding="utf-8") as f:
                raw = f.read()
            expanded = re.sub(r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), ""), raw)
            return yaml.safe_load(expanded)

    raise FileNotFoundError(f"config.yaml not found in any of {candidates}")


def build_search_query(cfg):
    cats = set(cfg["arxiv"].get("categories", []))
    # properly join categories
    if not cats:
        return "cat:astro-ph"
    if len(cats) > 1:
        cat_query = " OR ".join([f"cat:{c}" for c in cats])
    else:
        cat_query = f"cat:{list(cats)[0]}"
    return cat_query


def _format_submitted_date(dt_obj: dt.datetime) -> str:
    """arXiv API expects YYYYMMDDHHMM in UTC for submittedDate filters."""
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
    else:
        dt_obj = dt_obj.astimezone(dt.timezone.utc)
    return dt_obj.strftime("%Y%m%d%H%M")


def _download_arxiv_feed(url, headers, timeout):
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        print(f"error: could not fetch from arXiv: {e}")
        raise

    content = resp.content
    if resp.headers.get("Content-Encoding") == "gzip":
        try:
            content = gzip.decompress(content)
            data = content.decode("utf-8", errors="ignore")
            print("[arxiv bot] decompressed gzip response")
        except Exception:
            data = resp.text
    else:
        data = resp.text

    if "Rate exceeded" in data:
        raise RuntimeError("Rate exceeded")

    if "<entry>" not in data:
        print("[arxiv bot] warning: no <entry> tags in feed XML!")
        print(data[:500])
    return data


def fetch_recent(cfg):
    import urllib.parse

    arxiv_cfg = cfg.get("arxiv", {})
    max_results = arxiv_cfg.get("max_results", 50)
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 50
    if max_results <= 0:
        max_results = 50

    raw_chunk_size = arxiv_cfg.get("chunk_size") or arxiv_cfg.get("request_chunk_size")
    default_chunk = min(50, max_results)
    try:
        chunk_size = int(raw_chunk_size) if raw_chunk_size is not None else default_chunk
    except (TypeError, ValueError):
        chunk_size = default_chunk
    if chunk_size <= 0:
        chunk_size = default_chunk
    chunk_size = min(chunk_size, max_results)

    chunk_delay = arxiv_cfg.get("chunk_delay")
    if chunk_delay is None:
        chunk_delay = _MIN_INTERVAL if chunk_size < max_results else 0.0
    try:
        chunk_delay = float(chunk_delay)
    except (TypeError, ValueError):
        chunk_delay = _MIN_INTERVAL if chunk_size < max_results else 0.0
    chunk_delay = max(0.0, chunk_delay)

    read_timeout = arxiv_cfg.get("read_timeout") or arxiv_cfg.get("request_timeout") or 45.0
    connect_timeout = arxiv_cfg.get("connect_timeout") or arxiv_cfg.get("timeout_connect") or 8.0
    try:
        read_timeout = float(read_timeout)
    except (TypeError, ValueError):
        read_timeout = 45.0
    try:
        connect_timeout = float(connect_timeout)
    except (TypeError, ValueError):
        connect_timeout = 8.0
    read_timeout = max(5.0, read_timeout)
    connect_timeout = max(1.0, min(connect_timeout, read_timeout))
    timeout = (connect_timeout, read_timeout)

    now = dt.datetime.now(dt.timezone.utc)
    raw_days_back = arxiv_cfg.get("days_back", 1)
    try:
        days_back = float(raw_days_back)
    except (TypeError, ValueError):
        days_back = 1.0
    lookback_days = max(1, int(math.ceil(days_back)))
    range_start = (now - dt.timedelta(days=lookback_days)).replace(hour=0, minute=0, second=0, microsecond=0)

    raw_days_forward = arxiv_cfg.get("days_forward", 0)
    try:
        days_forward = float(raw_days_forward)
    except (TypeError, ValueError):
        days_forward = 0.0
    range_end = (now + dt.timedelta(days=max(0.0, days_forward))).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    if range_end <= range_start:
        range_end = range_start + dt.timedelta(days=1, hours=12)

    fmt_start = _format_submitted_date(range_start)
    fmt_end = _format_submitted_date(range_end)
    print(
        f"[arxiv bot] submittedDate window: {range_start:%Y-%m-%d %H:%M}Z -> "
        f"{range_end:%Y-%m-%d %H:%M}Z"
    )

    cat_query = build_search_query(cfg)
    date_clause = f"submittedDate:[{fmt_start} TO {fmt_end}]"
    if cat_query:
        query = f"({cat_query}) AND {date_clause}"
    else:
        query = date_clause
    since = range_start

    base = "https://export.arxiv.org/api/query"
    encoded_query = urllib.parse.quote(query, safe="+:()[]")
    headers = {"User-Agent": "arxiv-digest-bot/1.0 (mailto:ajd96@proton.me)"}

    aggregated_entries = []
    chunk_index = 0
    for start in range(0, max_results, chunk_size):
        page_size = min(chunk_size, max_results - start)
        url = (
            f"{base}?search_query={encoded_query}&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={page_size}&start={start}"
        )
        if chunk_index == 0:
            print(
                f"[arxiv bot] query URL: {url} (chunk_size={page_size}, timeout={timeout[1]:.0f}s)"
            )
        else:
            print(f"[arxiv bot] chunk {chunk_index + 1}: start={start}, size={page_size}")

        data = _download_arxiv_feed(url, headers, timeout)
        feed = feedparser.parse(data)
        print(
            f"[arxiv bot] feedparser found {len(feed.entries)} entries (chunk {chunk_index + 1})"
        )
        aggregated_entries.extend(feed.entries)
        chunk_index += 1

        if len(feed.entries) < page_size:
            break
        if start + page_size >= max_results:
            break
        if chunk_size < max_results and chunk_delay > 0:
            time.sleep(chunk_delay)

    results = []
    seen_ids = set()

    for entry in aggregated_entries:
        # choose updated date if available (more accurate for new versions)
        try:
            if getattr(entry, "updated_parsed", None):
                pub = dt.datetime.fromtimestamp(time.mktime(entry.updated_parsed)).astimezone(dt.timezone.utc)
            else:
                pub = dt.datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
        except Exception:
            pub = dt.datetime.now(dt.timezone.utc)

        entry_id = getattr(entry, "id", "")
        m = _ARXIV_ID_RE.search(entry_id) or _ARXIV_ID_RE.search(getattr(entry, "link", ""))
        arxiv_id = (m.group(1) + (m.group(2) or "")) if m else ""
        if arxiv_id and arxiv_id in seen_ids:
            continue
        if arxiv_id:
            seen_ids.add(arxiv_id)

        summary_text = decode_unicode_escapes(entry.summary.strip())
        summary_text = wrap_inline_tex(summary_text)

        categories = []
        primary_category = ""
        for tag in getattr(entry, "tags", []) or []:
            term = getattr(tag, "term", "") or (tag.get("term") if isinstance(tag, dict) else "")
            if term:
                categories.append(term)
        if getattr(entry, "arxiv_primary_category", None):
            primary_category = getattr(entry.arxiv_primary_category, "term", "") or ""
        if not primary_category and categories:
            primary_category = categories[0]

        record = {
            "title": entry.title.strip(),
            "summary": summary_text,
            "published": pub,
            "link": getattr(entry, "link", ""),
            "id": entry_id,
            "arxiv_id": arxiv_id,
            "authors": [a.name for a in getattr(entry, "authors", [])],
            "categories": categories,
            "primary_category": primary_category,
        }

        if pub >= since:
            results.append(record)

    if not results:
        print(
            "[arxiv bot] no entries satisfied the strict "
            f"{days_back}-day window ending {since.date()} - returning zero results."
        )

    print(
        f"[arxiv bot] fetched {len(results)} papers (newer than {since.date()}, max {max_results})"
    )
    return results


def safe_fetch_recent(*args, **kwargs):
    global _LAST_FETCH
    now = time.time()
    if now - _LAST_FETCH < _MIN_INTERVAL:
        delay = _MIN_INTERVAL - (now - _LAST_FETCH)
        print(f"[arxiv bot] waiting {delay:.1f}s to respect rate limit...")
        time.sleep(delay)

    _LAST_FETCH = time.time()
    # existing logic below
    for attempt in range(3):
        try:
            return fetch_recent(*args, **kwargs)
        except requests.exceptions.ReadTimeout:
            print(f"[warn] arXiv timeout, retrying ({attempt+1}/3)...")
            time.sleep(5)
        except Exception as e:
            # handle "Rate exceeded" explicitly
            if "Rate exceeded" in str(e):
                print("[warn] arXiv rate limit hit, sleeping for 60s...")
                time.sleep(60)
                continue
            # surface other errors
            raise
    print("[error] fetch_recent failed after retries")
    return []


def _write_cache_safely(results):
    """
    write the arXiv results to cache atomically with a timestamp.
    the file is only replaced if the write fully succeeds.
    """
    payload = {
        "timestamp": time.time(),
        "results": results,
    }

    tmp_fd, tmp_path = tempfile.mkstemp(prefix="cache_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            pyjson.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())  # ensure bytes hit disk
        os.replace(tmp_path, CACHE_FILE)  # atomic replace
        print(f"[cache] safely wrote {CACHE_FILE}")
    except Exception as e:
        print(f"[cache] failed to write cache: {e}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _parse_args():
    parser = argparse.ArgumentParser(description="arxiv digest bot")
    parser.add_argument("--no-cache", action="store_true", help="force fresh pull from arxiv")
    parser.add_argument("config_path", nargs="?", help="path to config file (defaults to config.yaml)")
    return parser.parse_args()


def load_or_fetch(cfg, *, use_cache=True, max_age=_CACHE_MAX_AGE, min_items=_CACHE_MIN_ITEMS):
    cached_payload = None
    cache_reason = ""
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached_payload = pyjson.load(f)
            valid, info = _validate_cache_payload(cached_payload, max_age, min_items)
            if valid:
                age = info
                results = cached_payload["results"]
                print(f"[cache] using cached results from {CACHE_FILE} (age={int(age)}s, items={len(results)})")
                return results, "cache-ok"
            cache_reason = info
            print(f"[cache] cache not suitable ({cache_reason}) — refetching")
        except pyjson.JSONDecodeError:
            cached_payload, cache_reason = None, "corrupt"
            print("[cache] corrupt cache detected — refetching")
        except Exception as exc:
            cached_payload, cache_reason = None, f"read-error:{exc}"
            print(f"[cache] warning: could not read cache ({exc})")
    fresh_results = safe_fetch_recent(cfg)
    if len(fresh_results) >= min_items:
        try:
            _write_cache_safely(fresh_results)
        except Exception as exc:
            print(f"[cache] warning: could not save cache ({exc})")
        return fresh_results, "fresh-fetch"
    print(f"[cache] fresh fetch returned {len(fresh_results)} items (<{min_items}); not caching")
    if cached_payload and isinstance(cached_payload.get("results"), list) and cached_payload["results"]:
        print(f"[cache] falling back to cached results despite ({cache_reason or 'unknown'})")
        return cached_payload["results"], f"stale-fallback:{cache_reason or 'unknown'}"
    return fresh_results, "fresh-insufficient"


def _validate_cache_payload(payload, max_age, min_items):
    if not isinstance(payload, dict):
        return False, "malformed"
    results = payload.get("results")
    if not isinstance(results, list):
        return False, "missing-results"
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        return False, "missing-timestamp"
    age = time.time() - timestamp
    if age > max_age:
        return False, f"stale:{int(age)}s"
    if len(results) < min_items:
        return False, f"too-few-items:{len(results)}"
    return True, age


def load_db_recipients(fallback_prefs):
    """fetch recipient preference profiles from the database, if available."""
    try:
        from webapp.models import User, Subscriber, PreferenceConfig, RecommendationSnapshot
        from sqlalchemy.orm import joinedload
    except Exception as exc:
        print(f"[arxiv bot] skipping db preferences (import error: {exc})")
        return {}
    app = _get_flask_app()
    if not app:
        print("[arxiv bot] skipping db preferences (flask app unavailable)")
        return {}

    profiles = {}
    with app.app_context():
        default_cfg = PreferenceConfig.query.filter_by(user_id=None).first()
        if default_cfg:
            default_prefs = _standardize_preferences(
                _combine_preferences(fallback_prefs, default_cfg.as_dict())
            )
        else:
            default_prefs = _standardize_preferences(fallback_prefs)
        default_categories = _dedupe_preserve_order(default_prefs.get("categories") or [])

        users = User.query.options(joinedload(User.preference_config)).all()
        for user in users:
            send_to = (user.email or "").strip()
            normalized = _normalize_email(send_to)
            if not normalized:
                continue
            pref_cfg = getattr(user, "preference_config", None)
            if pref_cfg:
                final_prefs = _standardize_preferences(pref_cfg.as_dict())
            else:
                final_prefs = _standardize_preferences(default_prefs)
            final_categories = final_prefs.get("categories", [])
            feedback_weights = _compute_feedback_weights(user, RecommendationSnapshot)
            profiles[normalized] = {
                "prefs": final_prefs,
                "categories": final_categories,
                "send_to": send_to or normalized,
                "feedback_weights": feedback_weights,
            }

        subscriber_rows = Subscriber.query.with_entities(Subscriber.email).all()
        for (email,) in subscriber_rows:
            send_to = (email or "").strip()
            normalized = _normalize_email(send_to)
            if not normalized or normalized in profiles:
                continue
            fallback_clone = _standardize_preferences(default_prefs)
            fallback_clone["categories"] = list(default_categories)
            profiles[normalized] = {
                "prefs": fallback_clone,
                "categories": fallback_clone["categories"],
                "send_to": send_to or normalized,
                "feedback_weights": _empty_feedback_weights(),
            }

    if profiles:
        print(f"[arxiv bot] loaded {len(profiles)} recipient profile(s) from database.")
    else:
        print("[arxiv bot] no recipient preferences found in database.")
    return profiles


def record_recommendation_snapshots(user_email, papers):
    """store the matched keyword/author context for later feedback learning."""
    if not user_email or not papers:
        return
    app = _get_flask_app()
    if not app:
        return
    try:
        from webapp.models import User, RecommendationSnapshot
    except Exception as exc:
        print(f"[arxiv bot] unable to import snapshot models: {exc}")
        return

    normalized = _normalize_email(user_email)
    if not normalized:
        return

    with app.app_context():
        user = User.query.filter(func.lower(User.email) == normalized).first()
        if not user:
            return

        for entry in papers:
            arxiv_id = entry.get("arxiv_id") or (entry.get("url") or "").split("/")[-1]
            if not arxiv_id:
                continue
            snapshot = RecommendationSnapshot.query.filter_by(
                user_id=user.id, arxiv_id=arxiv_id
            ).first()
            if not snapshot:
                snapshot = RecommendationSnapshot(user_id=user.id, arxiv_id=arxiv_id)
                db.session.add(snapshot)
            snapshot.title = entry.get("title") or ""
            snapshot.link = entry.get("url") or entry.get("link") or ""
            snapshot.score = entry.get("score")
            details = entry.get("details") or {}
            snapshot.matched_keywords = list(details.get("matched_any_keywords") or [])
            snapshot.matched_authors = list(details.get("matched_authors") or [])
            snapshot.details = details
            snapshot.feedback = None
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"[arxiv bot] failed to save recommendation snapshots: {exc}")


def curate(
    results,
    prefs,
    allowed_categories,
    fallback_prefs=None,
    email=None,
    feedback_weights=None,
):
    curated = []

    # handle preference fallback explicitly
    if prefs is None:
        prefs = fallback_prefs or {}
        print(f"[debug] using fallback prefs for {email or 'unknown user'}")
    else:
        print(f"[debug] using user prefs for {email or 'unknown user'}")

    allowed = _dedupe_preserve_order(allowed_categories or [])
    min_score = prefs.get("min_score", 1.0)
    weights = feedback_weights or _empty_feedback_weights()
    keyword_bias = weights.get("keywords", {})
    author_bias = weights.get("authors", {})

    for r in results:
        title = r.get("title", "")
        summary = r.get("summary", "")
        authors = r.get("authors", [])
        url = canon_abs_url(r) or r.get("link", "")
        paper_categories = r.get("categories") or []
        primary = r.get("primary_category") or (paper_categories[0] if paper_categories else "")
        category_for_filter = primary or (paper_categories[0] if paper_categories else "")

        # category filter
        if allowed and category_for_filter:
            if not match_category(category_for_filter, allowed):
                continue
        elif allowed:
            continue

        # scoring
        score, details = score_paper(title, summary, authors, prefs)
        print(f"[debug] paper '{title}' score={score} details={details}")
        feedback_bonus = _feedback_adjustment(details, keyword_bias, author_bias)
        details["feedback_bias"] = feedback_bonus
        score += feedback_bonus
        if score < min_score:
            continue

        # add to curated list
        curated.append({
            "title": title,
            "summary": summary,
            "authors": authors,
            "url": url,
            "pdf_url": r.get("pdf_url", ""),
            "category": primary or (paper_categories[0] if paper_categories else (allowed[0] if allowed else "")),
            "published": r.get("published"),
            "score": score,
            "details": details,
            "arxiv_id": r.get("arxiv_id", "") or (url.split("/")[-1] if url else ""),
        })

    print(f"[debug] curated {len(curated)} papers for {email or 'unknown user'} (min_score={min_score})")
    return curated


def select_top(curated, min_keep=3, max_keep=5, base_min_score=1.0):
    """adaptive selector that keeps 3–5 papers per day."""
    def keyfn(x):
        d = x.get("details", {})
        auth = d.get("auth_hits", 0)
        anyh = d.get("any_hits", 0)
        pub = x.get("published")
        return (x.get("score", 0), auth, anyh, pub or 0)

    items = sorted(curated, key=keyfn, reverse=True)
    thr = base_min_score
    filtered = [p for p in items if p.get("score", 0) >= thr]

    step = 0.5
    while len(filtered) > max_keep:
        thr += step
        new_filtered = [p for p in items if p.get("score", 0) >= thr]
        if len(new_filtered) == len(filtered):
            break
        filtered = new_filtered

    while len(filtered) < min_keep and thr > 0:
        thr = max(0, thr - step)
        new_filtered = [p for p in items if p.get("score", 0) >= thr]
        if len(new_filtered) == len(filtered):
            break
        filtered = new_filtered

    return filtered[:max_keep], thr


def format_authors(authors, max_authors=5):
    names = [a.name for a in authors] if authors and hasattr(authors[0], "name") else authors
    if not names:
        return ""
    if len(names) > max_authors:
        first = names[0].split(",")[0].strip()
        return f"{first} et al."
    else:
        return ", ".join(names)


def _relevance_explanation(details):
    if not details:
        return ""
    reasons = []
    keywords = [kw for kw in details.get("matched_any_keywords") or [] if kw]
    authors = [au for au in details.get("matched_authors") or [] if au]
    if keywords:
        reasons.append("keywords: " + ", ".join(keywords))
    if authors:
        reasons.append("authors: " + ", ".join(authors))
    bias = details.get("feedback_bias")
    if bias:
        reasons.append(f"feedback boost {bias:+.1f}")
    return "; ".join(reasons)


def render_paper_entry_html(paper, user_email, track_base):
    """
    build one paper block (html) with personalized like/dislike links.
    """
    arxiv_id = paper.get("arxiv_id") or (paper.get("url", "").split("/")[-1])
    raw_title = decode_unicode_escapes(paper.get("title", "") or "")
    title_wrapped = wrap_inline_tex(raw_title)
    title_html, _ = render_inline_math_html(title_wrapped)
    title_markup = title_html or Markup.escape(raw_title) or "(no title)"
    link = paper.get("url") or canon_abs_url(paper) or ""
    authors = paper.get("authors", [])
    authors_line = ", ".join(authors) if isinstance(authors, list) else str(authors)
    category = paper.get("category")
    score = paper.get("score")

    like_link = f"{track_base}/like?email={user_email}&arxiv_id={arxiv_id}&liked=true"
    dislike_link = f"{track_base}/like?email={user_email}&arxiv_id={arxiv_id}&liked=false"

    # initialize containers
    parts = []
    meta_tags = []

    parts.append("<li>")
    parts.append(f"<p><strong><a href='{link}'>{title_markup}</a></strong></p>")

    if category:
        meta_tags.append(f"<span class='category-tag'>{category}</span>")
    if score is not None:
        meta_tags.append(f"<span class='score-tag'>score: {score}</span>")

    if meta_tags:
        parts.append("<p>" + " ".join(meta_tags) + "</p>")
    if authors_line:
        parts.append(f"<p><i>{authors_line}</i></p>")
    summary_text = paper.get("summary")
    has_math = False
    if summary_text:
        summary_text = decode_unicode_escapes(summary_text)
        print("[email summary raw]", repr(summary_text))
        summary_wrapped = wrap_inline_tex(summary_text)
        summary_html, has_math = render_inline_math_html(summary_wrapped)
        parts.append(f"<p>{summary_html}</p>")
        relevance = _relevance_explanation(paper.get("details"))
        if relevance:
            parts.append(f"<p class='why-this'>why this paper? {Markup.escape(relevance)}</p>")

    parts.append(
        f"<p><a href='{like_link}'>👍 like</a> | <a href='{dislike_link}'>👎 dislike</a></p>"
    )
    parts.append("</li>")

    return "\n".join(parts), has_math


def render_paper_entry_text(paper, user_email, track_base):
    """
    build one paper block (plain text) with personalized like/dislike links.
    """
    arxiv_id = paper.get("arxiv_id") or (paper.get("url", "").split("/")[-1])
    raw_title = decode_unicode_escapes(paper.get("title", "") or "")
    title_wrapped = wrap_inline_tex(raw_title)
    title_plain = inline_math_to_plain(title_wrapped) or raw_title or "(no title)"
    link = paper.get("url") or canon_abs_url(paper) or ""
    authors = paper.get("authors", [])
    authors_line = ", ".join(authors) if isinstance(authors, list) else str(authors)
    category = paper.get("category")
    score = paper.get("score")

    like_link = f"{track_base}/like?email={user_email}&arxiv_id={arxiv_id}&liked=true"
    dislike_link = f"{track_base}/like?email={user_email}&arxiv_id={arxiv_id}&liked=false"

    # initialize containers
    lines = []
    meta_info = []

    lines.append(f"title: {title_plain}")
    lines.append(f"link: {link}")

    if category:
        meta_info.append(f"category: {category}")
    if score is not None:
        meta_info.append(f"score: {score}")
    if meta_info:
        lines.append("; ".join(meta_info))

    if authors_line:
        lines.append(f"authors: {authors_line}")
    summary = paper.get("summary")
    if summary:
        summary = decode_unicode_escapes(summary)
        summary_wrapped = wrap_inline_tex(summary)
        summary_plain = inline_math_to_plain(summary_wrapped)
        lines.append(summary_plain)
        relevance = _relevance_explanation(paper.get("details"))
        if relevance:
            lines.append(f"why this paper? {relevance}")

    lines.append(f"👍 like: {like_link}")
    lines.append(f"👎 dislike: {dislike_link}")
    lines.append("-" * 60)

    return "\n".join(lines)


def make_email_body_for_recipient(user_email, curated, track_base):
    """
    build (text, html) bodies personalized for a single recipient
    so the like/dislike links embed their email.
    """
    text_blocks = []
    html_entries = []
    found_math = False

    for p in curated:
        text_blocks.append(render_paper_entry_text(p, user_email, track_base))
        entry_html, entry_math = render_paper_entry_html(p, user_email, track_base)
        html_entries.append(entry_html)
        found_math = found_math or entry_math

    style_block = "<style>.math-inline{font-style:italic;}</style>" if found_math else ""

    html_body = (
        "<html><head>"
        f"{style_block}"
        "</head><body><h2>arxiv digest</h2><ol>"
        + "\n".join(html_entries)
        + "</ol></body></html>"
    )

    return "\n".join(text_blocks), html_body


def _standardize_preferences(prefs):
    normalized = _clone_preferences(prefs or {})
    if "any_keywords" not in normalized and normalized.get("keywords") is not None:
        normalized["any_keywords"] = list(normalized.get("keywords") or [])
    if "all_keywords" not in normalized and normalized.get("required_keywords") is not None:
        normalized["all_keywords"] = list(normalized.get("required_keywords") or [])
    if "exclude_keywords" not in normalized and normalized.get("excluded_keywords") is not None:
        normalized["exclude_keywords"] = list(normalized.get("excluded_keywords") or [])
    for key in (
        "any_keywords",
        "all_keywords",
        "exclude_keywords",
        "authors",
        "keywords",
        "excluded_keywords",
        "required_keywords",
    ):
        if isinstance(normalized.get(key), list):
            normalized[key] = _dedupe_preserve_order(normalized[key])
    normalized["categories"] = _dedupe_preserve_order(normalized.get("categories") or [])
    if normalized.get("min_score") is None:
        normalized["min_score"] = 1.0
    return normalized


def main():
    args = _parse_args()
    config_path = args.config_path or "config.yaml"
    cfg = load_config(config_path)
    email_cfg = cfg.setdefault("output", {}).setdefault("email", {})
    subject_prefix = email_cfg.get("subject_prefix", "[arxiv digest]")
    preferences = cfg.get("preferences", {})
    print(f"[debug] global preferences:", json.dumps(preferences, indent=2))
    print(f"[debug] email preferences:", json.dumps(email_cfg.get("preferences", {}), indent=2))

    today = dt.datetime.now(dt.timezone.utc)
    if today.weekday() >= 5:
        print(f"[arxiv bot] {today.strftime('%A')} detected — skipping weekend run.")
        return

    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    fallback_prefs = _standardize_preferences(merge_preferences(cfg["preferences"]))
    if not fallback_prefs.get("categories"):
        fallback_prefs["categories"] = _dedupe_preserve_order(
            cfg["arxiv"].get("categories") or []
        )
    cfg["preferences"] = fallback_prefs
    print("[arxiv bot] fallback preferences:", fallback_prefs)

    recipient_profiles = {}
    if test_mode:
        test_addr = (cfg.get("test_recipient") or email_cfg.get("test_recipient") or "").strip()
        if not test_addr:
            print("[arxiv bot] TEST MODE enabled but no test_recipient configured; aborting.")
            return
        print(f"[arxiv bot] TEST MODE ENABLED — will only send to {test_addr}")
        normalized = _normalize_email(test_addr)
        db_profiles = load_db_recipients(fallback_prefs)
        profile = db_profiles.get(normalized)
        if not profile:
            clone = _standardize_preferences(fallback_prefs)
            profile = {
                "prefs": clone,
                "categories": clone["categories"],
                "send_to": test_addr,
                "feedback_weights": _empty_feedback_weights(),
            }
        recipient_profiles = {normalized: profile}
        email_cfg["to_addrs"] = [profile.get("send_to", test_addr)]
    else:
        recipient_profiles = load_db_recipients(fallback_prefs)
        manual_addrs = [
            addr.strip()
            for addr in email_cfg.get("to_addrs", [])
            if addr and addr.strip()
        ]
        for addr in manual_addrs:
            normalized = _normalize_email(addr)
            if normalized in recipient_profiles:
                recipient_profiles[normalized].setdefault("send_to", addr)
                continue
            fallback_clone = _standardize_preferences(fallback_prefs)
            recipient_profiles[normalized] = {
                "prefs": fallback_clone,
                "categories": fallback_clone["categories"],
                "send_to": addr,
                "feedback_weights": _empty_feedback_weights(),
            }
        if not recipient_profiles:
            print("[arxiv bot] no recipients found; aborting.")
            return
        email_cfg["to_addrs"] = [
            recipient_profiles[key].get("send_to", key)
            for key in sorted(recipient_profiles)
        ]

    track_base = email_cfg.get("track_base", "https://paperscraper-one.vercel.app/")

    # union categories across recipients to widen the fetch query a bit (still cached)
    all_categories = set(cfg["arxiv"].get("categories", []))
    for profile in recipient_profiles.values():
        for cat in profile.get("categories") or []:
            if cat:
                all_categories.add(cat)
    if not all_categories:
        for cat in fallback_prefs.get("categories") or []:
            all_categories.add(cat)
    if not all_categories:
        all_categories.add("astro-ph")
    cfg["arxiv"]["categories"] = sorted(all_categories)

    # use cached+safe fetch instead of raw fetch
    papers, cache_source = load_or_fetch(cfg, use_cache=not args.no_cache)
    papers = papers or []
    print(f"[arxiv bot] using {cache_source} dataset with {len(papers)} entries")

    limits = cfg.get("limits", {})
    min_keep = limits.get("min_per_day", 3)
    max_keep = limits.get("max_per_day", 5)

    for actual_email in email_cfg["to_addrs"]:
        key = _normalize_email(actual_email)
        profile = recipient_profiles.get(key)
        if not profile:
            clone = _standardize_preferences(fallback_prefs)
            profile = {
                "prefs": clone,
                "categories": clone["categories"],
                "send_to": actual_email,
                "feedback_weights": _empty_feedback_weights(),
            }
            recipient_profiles[key] = profile
        prefs = profile["prefs"]
        allowed_categories = _dedupe_preserve_order(
            profile.get("categories") or fallback_prefs.get("categories") or cfg["arxiv"]["categories"]
        )
        if not allowed_categories:
            allowed_categories = ["astro-ph"]

        print(f"[debug] prefs for", actual_email, json.dumps(prefs, indent=2))
        curated = curate(
            papers,
            prefs,
            allowed_categories,
            fallback_prefs=fallback_prefs,
            email=actual_email,
            feedback_weights=profile.get("feedback_weights"),
        )
        print(
            f"[arxiv bot] {actual_email}: curated {len(curated)} papers "
            f"(min_score {prefs.get('min_score', 1.0)}) within categories {allowed_categories}"
        )
        if not curated:
            print(f"[arxiv bot] {actual_email}: no papers met the criteria; not sending email.")
            continue

        base_thr = prefs.get("min_score", fallback_prefs.get("min_score", 1.0))
        selected, eff_thr = select_top(curated, min_keep=min_keep, max_keep=max_keep, base_min_score=base_thr)
        if not selected:
            print(f"[arxiv bot] {actual_email}: curated papers failed selection; not sending email.")
            continue

        n = len(selected)
        subject = f"{subject_prefix} {dt.date.today()} — {n} paper{'s' if n != 1 else ''}"
        print(f"[arxiv bot] {actual_email}: selected {n} papers (effective threshold={eff_thr})")
        text_body, html_body = make_email_body_for_recipient(actual_email, selected, track_base)
        record_recommendation_snapshots(actual_email, selected)
        send_email(cfg, subject, text_body, html_body, to_override=[actual_email])

    print(f"[arxiv bot] processed {len(email_cfg['to_addrs'])} recipient(s).")

if __name__ == "__main__":
    main()

