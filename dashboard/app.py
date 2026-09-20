"""Flask app factory for the Control Center dashboard.

Deliberately does NOT import control_center.executor -- this process can
approve and decline, and can flip the kill switch, but has no code path to
execute an action. That happens in a separate process (run_executor.py).
"""
from __future__ import annotations

import os
from datetime import timedelta

from flask import Flask, g, session

from control_center import db as cc_db
from control_center import kill_switch, settings

from . import auth
from .csrf import get_csrf_token
from .routes import audit_bp, dashboard_bp, pending_bp, system_bp


def _truthy(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)

    secret = os.environ.get("DASHBOARD_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "DASHBOARD_SECRET_KEY is not set. Refusing to start with a default or "
            "missing secret key -- that would let anyone forge a session cookie. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    app.config["SECRET_KEY"] = secret

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
    # Secure cookies require HTTPS. Only disable for local plain-HTTP
    # development; never in anything resembling production.
    app.config["SESSION_COOKIE_SECURE"] = _truthy(os.environ.get("DASHBOARD_COOKIE_SECURE"), True)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    app.config["DB_PATH"] = db_path or settings.DB_PATH

    @app.before_request
    def _open_db():
        g.conn = cc_db.get_connection(app.config["DB_PATH"])
        cc_db.init_db(g.conn)

    @app.teardown_request
    def _close_db(_exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.context_processor
    def _inject_globals():
        write_status = None
        if session.get("user") and "conn" in g:
            write_status = kill_switch.get_write_enabled(g.conn)
        return {"csrf_token": get_csrf_token, "write_status": write_status}

    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(pending_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(system_bp)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=int(os.environ.get("DASHBOARD_PORT", "5000")))
