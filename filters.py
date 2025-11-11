import fnmatch, re, unicodedata


def _normalize(s):
    """
    normalize a string for case-insensitive and diacritic-insensitive matching.
    examples:
      'järvelä' -> 'jarvela'
      'gußmann' -> 'gussmann'
      'françois' -> 'francois'
    """
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)

    # language-specific replacements
    replacements = {
        "ß": "ss",                      # german eszett
        "ä": "a", "ö": "o", "ü": "u",   # german/finnish umlauts
        "å": "a", "ø": "o", "æ": "ae",  # nordic letters
        "ñ": "n",                       # spanish
        "č": "c", "š": "s", "ž": "z",   # slavic accents
    }

    for old, new in replacements.items():
        s = s.replace(old, new)

    # strip any remaining combining marks (accents, tildes, etc.)
    s = "".join(c for c in s if not unicodedata.combining(c))

    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_category(cat, allowed):
    return any(cat == a or cat.startswith(a + ".") for a in allowed)


def score_paper(title, abstract, authors, prefs):
    t = (title or "").lower()
    a = (abstract or "").lower()
    joined = f"{t} {a}"

    any_kw = prefs.get("any_keywords", [])
    all_kw = prefs.get("all_keywords", [])
    ex_kw = prefs.get("exclude_keywords", [])
    auth_wl = [s.lower() for s in prefs.get("authors", [])]

    score = 0.0
    details = {}

    # keyword hits
    any_hits = sum(1 for k in any_kw if k.lower() in joined)
    score += any_hits
    details["any_hits"] = any_hits

    # require all keywords together
    if all_kw:
        all_ok = all(k.lower() in joined for k in all_kw)
        if all_ok:
            score += 2.0
        details["all_ok"] = all_ok

    # author matches
    al = [x.lower() for x in authors]
    auth_hits = sum(1 for wl in auth_wl if any(wl in au for au in al))
    score += auth_hits
    details["auth_hits"] = auth_hits

    # excludes
    ex_hits = sum(1 for k in ex_kw if k.lower() in joined)
    if ex_hits:
        score -= 2.0 * ex_hits
    details["ex_hits"] = ex_hits

    return score, details
