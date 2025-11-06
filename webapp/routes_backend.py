#!/usr/bin/env python3
"""
routes_backend.py — backend routes for astro-ph digest
"""
import os, yaml
from flask import Blueprint, request, jsonify
from astroph_bot.shared.db import db

backend = Blueprint("backend", __name__)


# ----------------------------------------------------------
# user preferences api (for dashboard)
# ----------------------------------------------------------
@backend.route("/preferences", methods=["GET", "POST"])
def api_preferences():
    """get or save user preferences."""
    prefs_path = os.path.join(os.path.dirname(__file__), "user_prefs.yaml")

    if request.method == "GET":
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = yaml.safe_load(f) or {}
            prefs.setdefault("keywords", [])
            prefs.setdefault("authors", [])
            prefs.setdefault("min_score", 1.0)
            prefs.setdefault("categories", ["astro-ph"])
            return jsonify(prefs)
        except Exception as e:
            print(f"[api/preferences] error loading prefs: {e}")
            return jsonify({}), 500

    # post — save preferences
    try:
        data = request.get_json(force=True)
        prefs = {
            "keywords": data.get("keywords", []),
            "authors": data.get("authors", []),
            "min_score": data.get("min_score", 1.0),
            "categories": data.get("categories", ["astro-ph"]),
        }
        with open(prefs_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(prefs, f, sort_keys=False)

        print("[api/preferences] preferences saved:", prefs)
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[api/preferences] error saving prefs: {e}")
        return jsonify({"error": str(e)}), 500
