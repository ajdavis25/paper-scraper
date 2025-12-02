import re, unicodedata

from shared.preferences import WEIGHT_DEFAULTS


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


def _tokenize_name(norm: str):
    if not norm:
        return []
    return [tok for tok in re.split(r"[^0-9a-z]+", norm) if tok]


def _normalize_author_name(value):
    normalized = _normalize(value or "")
    tokens = _tokenize_name(normalized)
    if not tokens:
        return normalized, tokens, "", ""

    raw = value or ""
    has_comma = "," in raw
    if has_comma and len(tokens) >= 1:
        last = tokens[0]
        first = tokens[1] if len(tokens) > 1 else ""
    else:
        last = tokens[-1]
        if len(tokens) > 1:
            first = tokens[0]
        else:
            first = ""

    return normalized, tokens, first, last


def _prepare_author_terms(values):
    prepared = []
    for value in values or []:
        if not value:
            continue
        norm, tokens, first, last = _normalize_author_name(value)
        if norm:
            prepared.append((value, norm, tokens, first, last))
    return prepared


def _author_match(
    pref_norm,
    pref_tokens,
    pref_first,
    pref_last,
    author_norm,
    author_tokens,
    author_first,
    author_last,
):
    if not pref_norm or not author_norm:
        return False

    if pref_norm == author_norm or pref_norm in author_norm or author_norm in pref_norm:
        return True

    if not pref_last or not author_last or pref_last != author_last:
        return False

    if len(pref_tokens) == 1:
        return True

    if not pref_first or not author_first:
        return False

    if pref_first == author_first:
        return True

    if len(pref_first) == 1 and author_first.startswith(pref_first):
        return True

    if len(author_first) == 1 and pref_first.startswith(author_first):
        return True

    return False


def _get_weight(prefs, key):
    default = WEIGHT_DEFAULTS.get(key, 0.0)
    value = prefs.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    authors_norm = []
    for a in authors or []:
        norm, tokens, first, last = _normalize_author_name(a)
        if norm:
            authors_norm.append((norm, tokens, first, last))

    any_kw = _prepare_terms(prefs.get("any_keywords", []))
    all_kw = _prepare_terms(prefs.get("all_keywords", []))
    ex_kw = _prepare_terms(prefs.get("exclude_keywords", []))
    auth_wl = _prepare_author_terms(prefs.get("authors", []))

    keyword_weight = _get_weight(prefs, "keyword_weight")
    author_weight = _get_weight(prefs, "author_weight")
    exclude_penalty = _get_weight(prefs, "exclude_penalty")
    all_bonus = _get_weight(prefs, "all_bonus")

    score = 0.0
    details = {}
    matched_any = [orig for orig, norm in any_kw if norm and norm in text]
    any_hits = len(matched_any)
    missing_all = [orig for orig, norm in all_kw if norm and norm not in text]
    all_ok = bool(all_kw) and not missing_all
    matched_excluded = [orig for orig, norm in ex_kw if norm and norm in text]
    ex_hits = len(matched_excluded)

    score += any_hits * keyword_weight
    if all_ok:
        score += all_bonus
    if ex_hits:
        score -= exclude_penalty * ex_hits

    # author matches
    matched_authors = [
        orig
        for orig, norm, tokens, first, last in auth_wl
        if norm
        and any(
            _author_match(norm, tokens, first, last, au_norm, au_tokens, au_first, au_last)
            for au_norm, au_tokens, au_first, au_last in authors_norm
        )
    ]
    auth_hits = len(matched_authors)
    score += auth_hits * author_weight

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
