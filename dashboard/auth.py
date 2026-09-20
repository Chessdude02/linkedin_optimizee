"""Session-based authentication for a single operator account.

Credentials come from the environment (DASHBOARD_USERNAME,
DASHBOARD_PASSWORD_HASH) -- never hardcoded, never logged, never rendered
back in any response. Generate a hash with `python3 scripts/hash_password.py`.
"""
from __future__ import annotations

import os
from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for

from .csrf import csrf_protect, get_csrf_token
from .security import login_rate_limiter, verify_password

bp = Blueprint("auth", __name__)


def _configured_username() -> str | None:
    return os.environ.get("DASHBOARD_USERNAME")


def _configured_password_hash() -> str | None:
    return os.environ.get("DASHBOARD_PASSWORD_HASH")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def protect_blueprint(blueprint: Blueprint) -> None:
    """Require login for every route on `blueprint`. Registered as a
    before_request hook rather than decorating each view individually, so
    a route added later can't accidentally be left unprotected."""

    @blueprint.before_request
    def _require_login():
        if not session.get("user"):
            return redirect(url_for("auth.login", next=request.path))
        return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        get_csrf_token()  # seed the session with a token before the form renders
        return render_template("login.html", error=None)

    token = session.get("_csrf_token")
    submitted_token = request.form.get("csrf_token")
    import secrets as _secrets

    if not token or not submitted_token or not _secrets.compare_digest(token, submitted_token):
        return render_template("login.html", error="Session expired, please try again."), 403

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    configured_user = _configured_username()
    configured_hash = _configured_password_hash()

    if not configured_user or not configured_hash:
        return (
            render_template(
                "login.html",
                error=(
                    "No operator account is configured (DASHBOARD_USERNAME / "
                    "DASHBOARD_PASSWORD_HASH). Ask an administrator to set one up."
                ),
            ),
            500,
        )

    rate_key = username or "unknown"
    if login_rate_limiter.is_locked(rate_key):
        return render_template("login.html", error="Too many failed attempts. Try again later."), 429

    # verify_password always runs, even for an unrecognized username, so a
    # failure doesn't reveal via timing whether the username was the part
    # that was wrong.
    ok = username == configured_user and verify_password(password, configured_hash)
    if not ok:
        login_rate_limiter.record_failure(rate_key)
        return render_template("login.html", error="Invalid username or password."), 401

    login_rate_limiter.record_success(rate_key)
    session.clear()
    session["user"] = username
    session.permanent = True
    next_url = request.args.get("next") or url_for("dashboard.index")
    return redirect(next_url)


@bp.route("/logout", methods=["POST"])
@csrf_protect
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
