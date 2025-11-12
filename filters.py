import re, unicodedata

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

    any_kw = [_normalize(k) for k in prefs.get("any_keywords", [])]
    all_kw = [_normalize(k) for k in prefs.get("all_keywords", [])]
    ex_kw  = [_normalize(k) for k in prefs.get("exclude_keywords", [])]
    auth_wl = [_normalize(a) for a in prefs.get("authors", [])]

    score = 0.0
    details = {}

    # keyword matches
    any_hits = sum(1 for k in any_kw if k and k in text)
    all_ok = all(k and k in text for k in all_kw) if all_kw else False
    ex_hits = sum(1 for k in ex_kw if k and k in text)

    score += any_hits
    if all_kw and all_ok:
        score += 2.0
    if ex_hits:
        score -= 2.0 * ex_hits

    # author matches
    auth_hits = sum(1 for wl in auth_wl if any(wl in au for au in authors_norm))
    score += auth_hits

    details.update({
        "any_hits": any_hits,
        "all_ok": all_ok,
        "auth_hits": auth_hits,
        "ex_hits": ex_hits,
    })
    return score, details
