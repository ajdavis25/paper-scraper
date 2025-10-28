import re, os, yaml, feedparser, requests, datetime as dt
from filters import score_paper, match_category
from mailer import send_email
from curator import merge_preferences

print(f"[astro-ph bot] running: {__file__} SHA={os.environ.get('GITHUB_SHA', 'local')}")

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


def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    expanded = re.sub(r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), ""), raw)
    return yaml.safe_load(expanded)


def build_search_query(cfg):
    cats = cfg["arxiv"].get("categories", ["astro-ph*"])
    cat_query = " OR ".join([f"cat:{c}" for c in cats])
    return f"({cat_query})"


def fetch_recent(cfg):
    max_results = cfg["arxiv"].get("max_results", 50)
    query = build_search_query(cfg)
    days_back = cfg["arxiv"].get("days_back", 1)
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)

    base = "https://export.arxiv.org/api/query"
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
        "start": "0",
    }
    url = base + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"error: could not fetch from arXiv: {e}")
        return []

    feed = feedparser.parse(resp.text)
    results = []
    for entry in feed.entries:
        try:
            pub = dt.datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
        except Exception:
            pub = dt.datetime.now(dt.timezone.utc)

        entry_id = getattr(entry, "id", "")
        m = _ARXIV_ID_RE.search(entry_id) or _ARXIV_ID_RE.search(entry.link)
        arxiv_id = (m.group(1) + (m.group(2) or "")) if m else ""

        if pub >= since:
            results.append({
                "title": entry.title.strip(),
                "summary": entry.summary.strip(),
                "published": pub,
                "link": entry.link,
                "id": entry_id,
                "arxiv_id": arxiv_id,
                "authors": [a.name for a in entry.authors],
            })

    print(f"[astro-ph bot] fetched {len(results)} papers (max {max_results})")
    return results


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
            })

    print(f"[astro-ph bot] curated {len(curated)} papers (score ≥ {prefs.get('min_score', 1.0)})")
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


def make_email_body(cfg, curated):
    lines_txt = []
    lines_html = ['<html><body><h2>astro-ph digest</h2><ol>']

    # your live backend base url:
    email_base = "https://astro-digest.vercel.app"

    for r in curated:
        url = r.get("url") or canon_abs_url(r) or ""
        title = r.get("title", "")
        abstract = r.get("summary", "")
        authors = r.get("authors", [])
        arxiv_id = r.get("arxiv_id", "") or url.split("/")[-1]
        authors_line = ", ".join(authors) if isinstance(authors, list) else str(authors)

        # like/dislike feedback links
        like_link = f"{email_base}/like?email=ashton.davis3@my.utsa.edu&arxiv_id={arxiv_id}&liked=true"
        dislike_link = f"{email_base}/like?email=ashton.davis3@my.utsa.edu&arxiv_id={arxiv_id}&liked=false"

        # TEXT email section
        lines_txt.append(f"{title}\n{url}\n")
        if authors_line:
            lines_txt.append(f"authors: {authors_line}\n")
        lines_txt.append(abstract + "\n")
        lines_txt.append(f"👍 like: {like_link}\n👎 dislike: {dislike_link}\n")
        lines_txt.append("-" * 60)

        # HTML email section
        lines_html.append("<li>")
        lines_html.append(f'<p><b><a href="{url}">{title}</a></b></p>')
        if authors_line:
            lines_html.append(f"<p><i>{authors_line}</i></p>")
        lines_html.append(f"<p>{abstract}</p>")
        lines_html.append(
            f"<p><a href='{like_link}'>👍 like</a> | <a href='{dislike_link}'>👎 dislike</a></p>"
        )
        lines_html.append("</li>")

    lines_html.append("</ol></body></html>")
    return "\n".join(lines_txt), "\n".join(lines_html)


def main():
    cfg = load_config()

    # read testing flag from github secrets (env var)
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    if test_mode:
        test_addr = cfg.get("test_recipient", "ashton.davis3@my.utsa.edu")
        print(f"[astro-ph bot] TEST MODE ENABLED — will only send to {test_addr}")
        cfg["output"]["email"]["to_addrs"] = [test_addr]

    cfg["preferences"] = merge_preferences(cfg["preferences"])
    print("[astro-ph bot] merged keywords:", cfg["preferences"])

    papers = fetch_recent(cfg)
    curated = curate(cfg, papers)

    if not curated:
        print("no matches today.")
        subject = f'{cfg["output"]["email"]["subject_prefix"]} {dt.date.today()} — 0 papers'
        send_email(cfg, subject, "no matching papers found today.", "<p>no matches today.</p>")
        return

    limits = cfg.get("limits", {})
    min_keep = limits.get("min_per_day", 3)
    max_keep = limits.get("max_per_day", 5)
    base_thr = cfg["preferences"].get("min_score", 1.0)

    selected, eff_thr = select_top(curated, min_keep=min_keep, max_keep=max_keep, base_min_score=base_thr)
    print(f"[astro-ph bot] selected {len(selected)} (effective threshold={eff_thr}) out of {len(curated)} curated")

    # confirm recipients before sending
    print("[astro-ph bot] sending digest to:", cfg["output"]["email"]["to_addrs"])

    text_body, html_body = make_email_body(cfg, selected)
    n = len(selected)
    subject = f'{cfg["output"]["email"]["subject_prefix"]} {dt.date.today()} — {n} paper{"s" if n != 1 else ""}'
    send_email(cfg, subject, text_body, html_body)
    print(f"emailed {n} curated papers.")


if __name__ == "__main__":
    main()
