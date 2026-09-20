"""The real (Publora-backed) execution backend.

This module is imported lazily, only from executor._run_backend, and only
when settings.MOCK_EXECUTION is False. Importing control_center.actions
(what an agent does) or dashboard.app (what the dashboard does) never
reaches this file and never reads PUBLORA_API_KEY -- only the
run_executor.py process path does, which is the actual credential
isolation the spec calls for, not just a comment saying so.

Endpoint shapes match the Publora API as used by
sergebulaev/linkedin-skills' lib/publora_client.py (verified against the
live API 2026-09-15 there): auth header x-publora-key, POST /create-post,
POST /linkedin-comments, DELETE /linkedin-comments, POST
/linkedin-reactions, POST /linkedin-reshare, DELETE /delete-post/<id>.

Failure handling distinguishes two cases on purpose:
  - A definite HTTP error (4xx/5xx) raises PubloraBackendError, which
    executor.py catches and marks the action FAILED.
  - A timeout or connection error is genuinely ambiguous -- the request
    may or may not have reached LinkedIn -- so this returns
    {"result": "UNKNOWN"} instead of raising, which executor.py leaves
    mid-flight (EXECUTING) for a human to investigate rather than
    guessing or retrying blindly.
"""
from __future__ import annotations

import os
from typing import Any

import requests

BASE_URL = "https://api.publora.com/api/v1"
TIMEOUT_SECONDS = 30

REACTION_ALIASES = {
    "INSIGHTFUL": "INTEREST",
    "CURIOUS": "INTEREST",
    "FUNNY": "ENTERTAINMENT",
    "LAUGH": "ENTERTAINMENT",
    "LOVE": "APPRECIATION",
    "CELEBRATE": "PRAISE",
}


class PubloraBackendError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("PUBLORA_API_KEY")
    if not key:
        raise PubloraBackendError(
            "PUBLORA_API_KEY is not set in this process's environment. Only the "
            "execution service (run_executor.py) should ever need this credential "
            "-- set it there, never in the dashboard's or an agent's environment."
        )
    return key


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"x-publora-key": _api_key(), "Content-Type": "application/json"})
    return s


def _handle(resp: "requests.Response") -> dict[str, Any]:
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = {"error": resp.text[:500]}
        raise PubloraBackendError(f"HTTP {resp.status_code}: {body}")
    try:
        return resp.json()
    except ValueError:
        return {}


def run(action: dict[str, Any], platform_id: str) -> dict[str, Any]:
    """Dispatch one approved action to the real Publora API.

    Returns {"result": "SUCCESS", "external_id": ...} on success, or
    {"result": "UNKNOWN", "reason": ...} on a timeout/connection error.
    Raises PubloraBackendError (or lets requests exceptions other than
    Timeout/ConnectionError propagate) on a definite failure -- the caller
    (executor.py) is responsible for turning that into a FAILED action.
    """
    action_type = action["action_type"]
    payload = action["payload"]
    target_id = action.get("target_id")

    try:
        session = _session()

        if action_type in ("CREATE_POST", "SCHEDULE_POST"):
            body: dict[str, Any] = {"content": payload["content"], "platforms": [platform_id]}
            if payload.get("scheduled_time"):
                body["scheduledTime"] = payload["scheduled_time"]
            if payload.get("media_urls"):
                body["mediaUrls"] = payload["media_urls"]
            data = _handle(session.post(f"{BASE_URL}/create-post", json=body, timeout=TIMEOUT_SECONDS))
            external_id = data.get("postGroupId") or data.get("id") or "unknown"
            return {"result": "SUCCESS", "external_id": external_id}

        if action_type in ("CREATE_COMMENT", "CREATE_REPLY"):
            body = {"postedId": target_id, "message": payload["message"], "platformId": platform_id}
            if action_type == "CREATE_REPLY":
                body["parentComment"] = payload["parent_comment"]
            data = _handle(session.post(f"{BASE_URL}/linkedin-comments", json=body, timeout=TIMEOUT_SECONDS))
            external_id = (data.get("comment") or {}).get("id") or (data.get("comment") or {}).get(
                "commentUrn", "unknown"
            )
            return {"result": "SUCCESS", "external_id": external_id}

        if action_type == "CREATE_REACTION":
            rtype = REACTION_ALIASES.get(payload["reaction_type"].upper(), payload["reaction_type"].upper())
            body = {"postedId": target_id, "platformId": platform_id, "reactionType": rtype}
            _handle(session.post(f"{BASE_URL}/linkedin-reactions", json=body, timeout=TIMEOUT_SECONDS))
            return {"result": "SUCCESS", "external_id": f"reaction:{target_id}"}

        if action_type == "RESHARE_POST":
            body = {"platformId": platform_id, "parent": target_id}
            if payload.get("commentary"):
                body["commentary"] = payload["commentary"]
            if payload.get("visibility"):
                body["visibility"] = payload["visibility"].upper()
            data = _handle(session.post(f"{BASE_URL}/linkedin-reshare", json=body, timeout=TIMEOUT_SECONDS))
            external_id = (data.get("reshare") or {}).get("id", "unknown")
            return {"result": "SUCCESS", "external_id": external_id}

        if action_type == "DELETE_POST":
            _handle(session.delete(f"{BASE_URL}/delete-post/{target_id}", timeout=TIMEOUT_SECONDS))
            return {"result": "SUCCESS", "external_id": target_id}

        if action_type == "DELETE_COMMENT":
            body = {"postedId": target_id, "commentId": payload["comment_id"], "platformId": platform_id}
            _handle(
                session.delete(
                    f"{BASE_URL}/linkedin-comments", json=body, timeout=TIMEOUT_SECONDS
                )
            )
            return {"result": "SUCCESS", "external_id": payload["comment_id"]}

        raise PubloraBackendError(
            f"no real backend implemented for action_type={action_type!r}"
        )

    except requests.Timeout:
        return {"result": "UNKNOWN", "reason": "timeout"}
    except requests.ConnectionError as exc:
        return {"result": "UNKNOWN", "reason": f"connection_error: {exc}"}
