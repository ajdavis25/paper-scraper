import yaml

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def merge_preferences(user_prefs, defaults_path="defaults.yaml"):
    defaults = load_yaml(defaults_path)
    merged = {k: list(set(defaults.get(k, []) + user_prefs.get(k, [])))
              for k in set(defaults) | set(user_prefs)}
    return merged
