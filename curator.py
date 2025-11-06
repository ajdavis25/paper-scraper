import yaml
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent
_DEFAULTS_PATH = _BASE_DIR / "defaults.yaml"


def load_yaml(path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def merge_preferences(user_prefs, defaults_path=_DEFAULTS_PATH):
    defaults = load_yaml(defaults_path)
    merged = {}

    # merge list-like keys safely
    for key in set(defaults) | set(user_prefs):
        def_val = defaults.get(key)
        usr_val = user_prefs.get(key)

        # if both are lists -> combine and deduplicate
        if isinstance(def_val, list) and isinstance(usr_val, list):
            merged[key] = list(set(def_val + usr_val))
        # if only one is a list -> use that
        elif isinstance(def_val, list):
            merged[key] = def_val
        elif isinstance(usr_val, list):
            merged[key] = usr_val
        # otherwise (numbers, bools, etc.) -> take user’s value first, fallback to default
        else:
            merged[key] = usr_val if usr_val is not None else def_val

    return merged
