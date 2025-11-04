"""
shared/utils.py — general-purpose helpers for astro-ph digest.
"""
import yaml
import xml.etree.ElementTree as ET
import requests


def load_yaml(path):
    """safely load yaml into a python dict."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[load_yaml] error reading {path}: {e}")
        return {}


def save_yaml(path, data):
    """save dict to yaml."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
    except Exception as e:
        print(f"[save_yaml] error writing {path}: {e}")


def build_arxiv_query(keywords, max_results=5):
    """
    construct an arXiv api query string given keywords.
    example: https://export.arxiv.org/api/query?search_query=all:black+hole&sortBy=submittedDate
    """
    base = "https://export.arxiv.org/api/query?"
    if not keywords:
        return base + "search_query=cat:astro-ph&sortBy=submittedDate&sortOrder=descending"

    query = "+OR+".join(f"all:{kw}" for kw in keywords)
    return f"{base}search_query={query}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"


def fetch_arxiv_feed(url):
    """fetch and parse the arXiv api xml feed, return a list of papers."""
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

            entries.append({
                "title": title.text.strip() if title is not None else "(no title)",
                "summary": summary.text.strip() if summary is not None else "",
                "link": link.text.strip() if link is not None else "#"
            })

        print(f"[fetch_arxiv_feed] parsed {len(entries)} entries")
        return entries
    except Exception as e:
        print(f"[fetch_arxiv_feed] error: {e}")
        return []
    