#!/usr/bin/env python3
"""
backend routes that power the dashboard / JSON APIs.
"""
import base64, json, os, re

from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import func

from shared.db import db
from shared.gmail_push import (
    fetch_access_token,
    get_message,
    list_history,
    GmailPushError,
)
from webapp.account_utils import ensure_user_stub
from webapp.models import PreferenceConfig, GmailWatchState, Subscriber

backend = Blueprint("backend", __name__)


@backend.route("/preferences", methods=["GET", "POST"])
@login_required
def api_preferences():
    """load or persist per-user preference defaults."""
    if request.method == "GET":
        try:
            config = PreferenceConfig.get_or_create_for_user(current_user)
            if config is None:
                return jsonify({}), 400
            return jsonify(config.as_dict())
        except Exception as exc:  # pragma: no cover
            print(f"[api/preferences] error loading prefs: {exc}")
            return jsonify({}), 500

    # POST: save preferences
    try:
        data = request.get_json(force=True) or {}
        config = PreferenceConfig.get_or_create_for_user(current_user, commit=False)

        config.keywords = data.get("keywords") or []
        config.excluded_keywords = data.get("excluded_keywords") or []
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


# gmail push webhook
def _verify_pubsub_jwt(req) -> bool:
    """verify the OIDC token attached to push requests (if configured)."""
    audience = os.getenv("PUBSUB_OIDC_AUDIENCE")
    if not audience:
        return True  # auth disabled

    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        print("[gmail-hook] missing bearer token.")
        return False

    token = auth_header.split(" ", 1)[1].strip()
    try:
        info = id_token.verify_oauth2_token(token, google_requests.Request(), audience)
    except Exception as exc:
        print(f"[gmail-hook] OIDC verification failed: {exc}")
        return False

    expected_email = os.getenv("PUBSUB_PUSH_SERVICE_ACCOUNT")
    if expected_email and info.get("email") != expected_email:
        print(
            f"[gmail-hook] token email {info.get('email')} did not match expected {expected_email}."
        )
        return False
    return True


_EMAIL_RE = re.compile(r"<(.+?)>")


def _extract_sender(sender_header: str) -> str:
    match = _EMAIL_RE.search(sender_header or "")
    email = match.group(1) if match else sender_header
    return (email or "").strip().lower()


def _subscribe_email(address: str) -> bool:
    normalized = (address or "").strip().lower()
    if not normalized:
        return False
    existing = Subscriber.query.filter(func.lower(Subscriber.email) == normalized).first()
    if existing:
        print(f"[gmail-hook] already subscribed: {normalized}")
        return False
    sub = Subscriber(email=normalized)
    db.session.add(sub)
    ensure_user_stub(normalized, commit=False)
    db.session.commit()
    print(f"[gmail-hook] subscribed {normalized}")
    return True


def _unsubscribe_email(address: str) -> bool:
    normalized = (address or "").strip().lower()
    if not normalized:
        return False
    existing = Subscriber.query.filter(func.lower(Subscriber.email) == normalized).first()
    if not existing:
        print(f"[gmail-hook] unsubscribe requested but not found: {normalized}")
        return False
    db.session.delete(existing)
    db.session.commit()
    print(f"[gmail-hook] unsubscribed {normalized}")
    return True


def _handle_message(token: str, message_id: str) -> None:
    """inspect message metadata and update subscriber list if needed."""
    msg = get_message(token, message_id)
    headers = {
        hdr["name"]: hdr["value"]
        for hdr in msg.get("payload", {}).get("headers", [])
        if "name" in hdr
    }
    subject = (headers.get("Subject") or "").lower()
    sender = _extract_sender(headers.get("From", ""))
    if not sender:
        print(f"[gmail-hook] unable to parse sender for message {message_id}")
        return

    if "unsubscribe" in subject:
        _unsubscribe_email(sender)
    elif "subscribe" in subject:
        _subscribe_email(sender)
    else:
        print(f"[gmail-hook] ignored message {message_id} with subject '{subject}'")


def _process_history(token: str, start_history_id: str, label_id: str | None) -> tuple[int, str]:
    """fetch history entries since start_history_id and handle new messages."""
    processed = 0
    newest_history = start_history_id
    page_token = None

    while True:
        resp = list_history(
            token,
            start_history_id=start_history_id,
            label_id=label_id,
            page_token=page_token,
        )
        for entry in resp.get("history", []):
            newest_history = entry.get("id", newest_history)
            for addition in entry.get("messagesAdded", []):
                message = addition.get("message") or {}
                message_id = message.get("id")
                if message_id:
                    _handle_message(token, message_id)
                    processed += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            newest_history = resp.get("historyId", newest_history)
            break

    return processed, newest_history


@backend.route("/gmail-hook", methods=["POST"])
def gmail_hook():
    """Pub/Sub push endpoint for Gmail watch notifications."""
    if not _verify_pubsub_jwt(request):
        return jsonify({"status": "unauthorized"}), 401

    envelope = request.get_json(force=True, silent=True)
    if not envelope or "message" not in envelope:
        return jsonify({"status": "no-message"}), 400

    raw_data = envelope["message"].get("data")
    if not raw_data:
        return jsonify({"status": "no-data"}), 204

    try:
        payload = json.loads(base64.b64decode(raw_data).decode("utf-8"))
    except Exception as exc:
        print(f"[gmail-hook] failed to decode payload: {exc}")
        return jsonify({"status": "bad-payload"}), 400

    history_id = payload.get("historyId")
    if not history_id:
        return jsonify({"status": "no-history"}), 204

    state = GmailWatchState.get_state()
    label_id = state.label_id or os.getenv("GMAIL_WATCH_LABEL")
    if not state.history_id:
        GmailWatchState.update_history(history_id, label_id=label_id)
        print("[gmail-hook] initialized history id state.")
        return jsonify({"status": "initialized"}), 200

    try:
        token = fetch_access_token()
        processed, newest_history = _process_history(token, state.history_id, label_id)
    except GmailPushError as exc:
        print(f"[gmail-hook] gmail api error: {exc}")
        return jsonify({"status": "gmail-error"}), 500
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[gmail-hook] unexpected error: {exc}")
        return jsonify({"status": "server-error"}), 500

    GmailWatchState.update_history(newest_history or history_id, label_id=label_id)
    return jsonify({"status": "ok", "processed": processed}), 200
