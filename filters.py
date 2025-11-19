import re, unicodedata


def _prepare_terms(values):
    prepared = []
    for value in values or []:
        if value is None:
            continue
        normalized = _normalize(value)
        if normalized:
            prepared.append((value, normalized))
    return prepared

def _normalize(s: str) -> str:
    """
    normalize text for case- and accent-insensitive matching.
    """
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    replacements = {
        "ß": "ss",                      # german eszett
        "ä": "a", "ö": "o", "ü": "u",   # german/finnish umlauts
        "å": "a", "ø": "o", "æ": "ae",  # nordic letters
        "ñ": "n",                       # spanish
        "č": "c", "š": "s", "ž": "z",   # slavic accents
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return re.sub(r"\s+", " ", s).strip()


def match_category(cat, allowed):
    return any(cat == a or cat.startswith(a + ".") for a in allowed)


def score_paper(title, abstract, authors, prefs):
    """
    compute a numeric relevance score for a paper.
    - case/diacritic insensitive
    - handles multiword phrases
    - ignores punctuation boundaries
    """
    text = _normalize(f"{title or ''} {abstract or ''}")
    authors_norm = [_normalize(a) for a in authors or []]

    any_kw = _prepare_terms(prefs.get("any_keywords", []))
    all_kw = _prepare_terms(prefs.get("all_keywords", []))
    ex_kw = _prepare_terms(prefs.get("exclude_keywords", []))
    auth_wl = _prepare_terms(prefs.get("authors", []))

    score = 0.0
    details = {}
    matched_any = [orig for orig, norm in any_kw if norm and norm in text]
    any_hits = len(matched_any)
    missing_all = [orig for orig, norm in all_kw if norm and norm not in text]
    all_ok = bool(all_kw) and not missing_all
    matched_excluded = [orig for orig, norm in ex_kw if norm and norm in text]
    ex_hits = len(matched_excluded)

    score += any_hits
    if all_kw and all_ok:
        score += 2.0
    if ex_hits:
        score -= 2.0 * ex_hits

    # author matches
    matched_authors = [
        orig for orig, norm in auth_wl if norm and any(norm in au for au in authors_norm)
    ]
    auth_hits = len(matched_authors)
    score += auth_hits

    details.update(
        {
            "any_hits": any_hits,
            "matched_any_keywords": matched_any,
            "all_ok": all_ok,
            "missing_all_keywords": missing_all,
            "auth_hits": auth_hits,
            "matched_authors": matched_authors,
            "ex_hits": ex_hits,
            "matched_excluded_keywords": matched_excluded,
        }
    )
    return score, details
