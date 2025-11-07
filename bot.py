import re, os, yaml, feedparser, requests, datetime as dt
from filters import score_paper, match_category
from mailer import send_email
from curator import merge_preferences
from shared.utils import (
    wrap_inline_tex,
    render_inline_math_html,
    inline_math_to_plain,
    decode_unicode_escapes,
)

print(f"[arxiv bot] running: {__file__} SHA={os.environ.get('GITHUB_SHA', 'local')}")

# arXiv id pattern and canonical link helper
_ARXIV_ID_RE = re.compile(r'(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(v\d+)?', re.I)


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


def load_config(path=None):
    """
    load yaml config, automatically detecting path from cli or repo layout.
    works both locally and in github actions.
    """
    import sys

    # allow explicit cli arg
    if not path and len(sys.argv) > 1:
        path = sys.argv[1]

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
    cats = cfg["arxiv"].get("categories", ["astro-ph.CO"])
    # properly join categories
    if len(cats) > 1:
        cat_query = " OR ".join([f"cat:{c}" for c in cats])
    else:
        cat_query = f"cat:{cats[0]}"
    return cat_query


def fetch_recent(cfg):
    import urllib.parse
    import gzip

    max_results = cfg["arxiv"].get("max_results", 50)
    query = build_search_query(cfg)
    days_back = cfg["arxiv"].get("days_back", 1)
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)

    base = "https://export.arxiv.org/api/query"
    encoded_query = urllib.parse.quote(query, safe="+:()")
    params = {
        "search_query": encoded_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
        "start": "0",
    }
    url = base + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    print(f"[arxiv bot] query URL: {url}")

    headers = {"User-Agent": "arxiv-digest-bot/1.0 (mailto:ajd96@proton.me)"}

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        # only decompress if truly gzipped
        content = resp.content
        if resp.headers.get("Content-Encoding") == "gzip":
            try:
                content = gzip.decompress(content)
                data = content.decode("utf-8", errors="ignore")
                print("[arxiv bot] decompressed gzip response")
            except Exception:
                # fall back silently if it's not actually gzipped
                data = resp.text
        else:
            data = resp.text

        if "<entry>" not in data:
            print("[arxiv bot] warning: no <entry> tags in feed XML!")
            print(data[:500])
    except Exception as e:
        print(f"error: could not fetch from arXiv: {e}")
        return []

    feed = feedparser.parse(data)
    print(f"[arxiv bot] feedparser found {len(feed.entries)} entries")
    results = []

    for entry in feed.entries:
        try:
            pub = dt.datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
        except Exception:
            pub = dt.datetime.now(dt.timezone.utc)

        entry_id = getattr(entry, "id", "")
        m = _ARXIV_ID_RE.search(entry_id) or _ARXIV_ID_RE.search(getattr(entry, "link", ""))
        arxiv_id = (m.group(1) + (m.group(2) or "")) if m else ""

        summary_text = decode_unicode_escapes(entry.summary.strip())
        summary_text = wrap_inline_tex(summary_text)
        results.append({
            "title": entry.title.strip(),
            "summary": summary_text,
            "published": pub,
            "link": getattr(entry, "link", ""),
            "id": entry_id,
            "arxiv_id": arxiv_id,
            "authors": [a.name for a in getattr(entry, "authors", [])],
        })

    print(f"[arxiv bot] fetched {len(results)} papers (max {max_results})")
    return results


def load_db_recipients():
    """fetch recipient emails from the database, if available."""
    try:
        from webapp import create_app
        from webapp.models import User, Subscriber
    except Exception as exc:
        print(f"[arxiv bot] skipping db recipients (import error: {exc})")
        return []

    try:
        app = create_app()
    except Exception as exc:
        print(f"[arxiv bot] skipping db recipients (app init error: {exc})")
        return []

    emails = set()
    try:
        with app.app_context():
            for model in (Subscriber, User):
                try:
                    rows = model.query.with_entities(model.email).all()
                    for (email,) in rows:
                        if email:
                            emails.add(email.strip().lower())
                except Exception as inner_exc:
                    print(f"[arxiv bot] unable to read {model.__name__}: {inner_exc}")
    except Exception as exc:
        print(f"[arxiv bot] skipping db recipients (db error: {exc})")
        return []

    if emails:
        print(f"[arxiv bot] loaded {len(emails)} email(s) from database.")
    else:
        print("[arxiv bot] no recipient emails found in database.")
    return sorted(emails)


def curate(cfg, results):
    curated = []
    prefs = cfg["preferences"]

    for r in results:
        title = r.get("title", "")
        summary = r.get("summary", "")
        authors = r.get("authors", [])
        pdf_url = r.get("pdf_url", "")
        category = cfg["arxiv"]["categories"][0]
        url = canon_abs_url(r)

        if not match_category(category, cfg["arxiv"]["categories"]):
            continue

        score, details = score_paper(title, summary, authors, prefs)

        if score >= prefs.get("min_score", 1.0):
            curated.append({
                "title": title,
                "summary": summary,
                "authors": authors,
                "url": url,
                "pdf_url": pdf_url,
                "category": category,
                "published": r.get("published"),
                "score": score,
                "details": details,
                "arxiv_id": r.get("arxiv_id", "") or (url.split("/")[-1] if url else ""),
            })

    print(f"[arxiv bot] curated {len(curated)} papers (score ≥ {prefs.get('min_score', 1.0)})")
    print(f"[arxiv bot] curated {len(curated)} / {len(results)} papers (score ≥ {prefs.get('min_score', 1.0)})")
    for r in results[:10]:  # show first few raw entries
        print("→", r["title"][:80])

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


def render_paper_entry_html(paper, user_email, track_base):
    """
    build one paper block (html) with personalized like/dislike links.
    """
    arxiv_id = paper.get("arxiv_id") or (paper.get("url", "").split("/")[-1])
    title = paper.get("title", "")
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
    parts.append(f"<p><strong><a href='{link}'>{title}</a></strong></p>")

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
        print("[email summary raw]", repr(summary_text))
        summary_wrapped = wrap_inline_tex(summary_text)
        summary_html, has_math = render_inline_math_html(summary_wrapped)
        parts.append(f"<p>{summary_html}</p>")

    print("[email summary raw]", repr(summary_text))

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
    title = paper.get("title", "")
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

    lines.append(f"title: {title}")
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
        summary_wrapped = wrap_inline_tex(summary)
        summary_plain = inline_math_to_plain(summary_wrapped)
        lines.append(summary_plain)

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


def main():
    cfg = load_config()

    # read testing flag from github secrets (env var)
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    if test_mode:
        test_addr = cfg.get("test_recipient", "ashton.davis3@my.utsa.edu")
        print(f"[arxiv bot] TEST MODE ENABLED — will only send to {test_addr}")
        cfg["output"]["email"]["to_addrs"] = [test_addr]
    else:
        email_cfg = cfg.setdefault("output", {}).setdefault("email", {})
        existing = email_cfg.get("to_addrs", [])
        db_recipients = load_db_recipients()
        combined = sorted({*(addr.strip().lower() for addr in existing if addr), *db_recipients})
        if combined:
            email_cfg["to_addrs"] = combined
        else:
            email_cfg.setdefault("to_addrs", existing)

    # where your flask app is serving the /like endpoint
    track_base = (
        cfg.get("output", {})
           .get("email", {})
           .get("track_base", "https://paperscraper-one.vercel.app/")
    )

    cfg["preferences"] = merge_preferences(cfg["preferences"])
    print("[arxiv bot] merged keywords:", cfg["preferences"])

    papers = fetch_recent(cfg)
    curated = curate(cfg, papers)

    if not curated:
        print("no matches today.")
        subject = f'{cfg["output"]["email"]["subject_prefix"]} {dt.date.today()} — 0 papers'
        # still send a “no matches” note to list (or just to you in test mode)
        for rcpt in cfg["output"]["email"]["to_addrs"]:
            send_email(cfg, subject, "no matching papers found today.", "<p>no matches today.</p>", to_override=[rcpt])
        return

    limits = cfg.get("limits", {})
    min_keep = limits.get("min_per_day", 3)
    max_keep = limits.get("max_per_day", 5)
    base_thr = cfg["preferences"].get("min_score", 1.0)

    selected, eff_thr = select_top(curated, min_keep=min_keep, max_keep=max_keep, base_min_score=base_thr)
    print(f"[arxiv bot] selected {len(selected)} (effective threshold={eff_thr}) out of {len(curated)} curated")

    recipients = cfg["output"]["email"]["to_addrs"]
    print("[arxiv bot] sending digest to:", recipients)

    n = len(selected)
    subject = f'{cfg["output"]["email"]["subject_prefix"]} {dt.date.today()} — {n} paper{"s" if n != 1 else ""}'

    # personalize for each recipient so their like/dislike links carry their email
    for rcpt in recipients:
        text_body, html_body = make_email_body_for_recipient(rcpt, selected, track_base)
        send_email(cfg, subject, text_body, html_body, to_override=[rcpt])

    print(f"emailed {n} curated papers to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()

