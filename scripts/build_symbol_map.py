import json, re
from pathlib import Path


def main() -> None:
    data_ts = Path("shared/data.ts")
    if not data_ts.exists():
        raise FileNotFoundError(f"Cannot find {data_ts}")

    text = data_ts.read_text(encoding="utf-8")
    pairs = re.findall(r"\['([^']*)', '([^']*)'\]", text)
    mapping = {latex: value for latex, value in pairs}

    out_path = Path("shared/latex_symbols.json")
    out_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(mapping)} mappings to {out_path}")


if __name__ == "__main__":
    main()
