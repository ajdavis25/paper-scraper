#!/usr/bin/env python3
"""
backend routes that power the dashboard / JSON APIs.
"""
from flask import Blueprint, request, jsonify

from shared.db import db
from webapp.models import PreferenceConfig

backend = Blueprint("backend", __name__)


@backend.route("/preferences", methods=["GET", "POST"])
def api_preferences():
    """load or persist global preference defaults."""
    if request.method == "GET":
        try:
            config = PreferenceConfig.query.first()
            if config is None:
                config = PreferenceConfig()
                db.session.add(config)
                db.session.commit()
            return jsonify(config.as_dict())
        except Exception as exc:  # pragma: no cover
            print(f"[api/preferences] error loading prefs: {exc}")
            return jsonify({}), 500

    # POST: save preferences
    try:
        data = request.get_json(force=True) or {}
        config = PreferenceConfig.query.first()
        if config is None:
            config = PreferenceConfig()
            db.session.add(config)

        config.keywords = data.get("keywords") or []
        config.authors = data.get("authors") or []
        config.categories = data.get("categories") or ["astro-ph"]
        config.min_score = data.get("min_score", 1.0) or 1.0

        db.session.commit()
        payload = config.as_dict()
        print("[api/preferences] preferences saved:", payload)
        return jsonify({"status": "ok", "preferences": payload})
    except Exception as exc:  # pragma: no cover
        db.session.rollback()
        print(f"[api/preferences] error saving prefs: {exc}")
        return jsonify({"error": str(exc)}), 500
