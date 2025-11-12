"""
helpers for gmail push notifications (token refresh, watch, history, message fetch).
"""
from __future__ import annotations

import os, requests
from typing import Iterable, Optional

GMAIL_API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GmailPushError(RuntimeError):
    """raised when Gmail push helper encounters an unrecoverable error."""


def _load_env(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise GmailPushError(f"missing required environment variable: {var}")
    return val


def fetch_access_token(scopes: Optional[Iterable[str]] = None) -> str:
    """
    exchange the refresh token for a short-lived access token.
    scopes are only informative; the refresh token already encodes them.
    """
    client_id = _load_env("GMAIL_PUSH_CLIENT_ID")
    client_secret = _load_env("GMAIL_PUSH_CLIENT_SECRET")
    refresh_token = _load_env("GMAIL_PUSH_REFRESH_TOKEN")

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if scopes:
        data["scope"] = " ".join(scopes)

    resp = requests.post(TOKEN_URL, data=data, timeout=10)
    if resp.status_code != 200:
        raise GmailPushError(f"token refresh failed: {resp.status_code} {resp.text}")

    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise GmailPushError("token refresh response missing access_token")
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def start_watch(token: str, *, topic: str, label_ids: Optional[Iterable[str]] = None) -> dict:
    """
    invoke users.watch with the provided Pub/Sub topic and optional label filters.
    returns the raw JSON response (includes historyId and expiration).
    """
    payload: dict[str, object] = {"topicName": topic}
    if label_ids:
        payload["labelIds"] = list(label_ids)

    resp = requests.post(
        f"{GMAIL_API_ROOT}/watch",
        headers=_auth_headers(token),
        json=payload,
        timeout=10,
    )
    if resp.status_code != 200:
        raise GmailPushError(f"users.watch failed: {resp.status_code} {resp.text}")
    return resp.json()


def list_history(
    token: str,
    *,
    start_history_id: str,
    label_id: Optional[str] = None,
    page_token: Optional[str] = None,
) -> dict:
    """call users.history.list for the supplied start history id."""
    params = {"startHistoryId": str(start_history_id)}
    if label_id:
        params["labelId"] = label_id
    if page_token:
        params["pageToken"] = page_token

    resp = requests.get(
        f"{GMAIL_API_ROOT}/history",
        headers=_auth_headers(token),
        params=params,
        timeout=10,
    )
    if resp.status_code != 200:
        raise GmailPushError(f"users.history.list failed: {resp.status_code} {resp.text}")
    return resp.json()


def get_message(token: str, message_id: str) -> dict:
    """fetch a single message with metadata (subject/from headers)."""
    params = {"format": "metadata", "metadataHeaders": ["Subject", "From"]}
    resp = requests.get(
        f"{GMAIL_API_ROOT}/messages/{message_id}",
        headers=_auth_headers(token),
        params=params,
        timeout=10,
    )
    if resp.status_code != 200:
        raise GmailPushError(f"users.messages.get failed: {resp.status_code} {resp.text}")
    return resp.json()
