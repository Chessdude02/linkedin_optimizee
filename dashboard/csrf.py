"""Minimal CSRF protection: a per-session random token embedded in every
form and checked on every state-changing POST before it reaches a route
handler's logic."""
from __future__ import annotations

import secrets
from functools import wraps

from flask import abort, request, session


def get_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method == "POST":
            token = session.get("_csrf_token")
            submitted = request.form.get("csrf_token")
            if not token or not submitted or not secrets.compare_digest(token, submitted):
                abort(403, description="CSRF token missing or invalid")
        return view(*args, **kwargs)

    return wrapped
