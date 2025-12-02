"""Shared preference defaults for scoring weights."""

WEIGHT_DEFAULTS = {
    "keyword_weight": 1.0,
    "author_weight": 3.0,
    "exclude_penalty": 2.0,
    "all_bonus": 2.0,
}


def clamp_weight(value, field, *, minimum=0.0, maximum=10.0):
    """
    Clamp a weight to the allowed range, returning the fallback default when parsing fails.
    """
    default = WEIGHT_DEFAULTS[field]
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed
