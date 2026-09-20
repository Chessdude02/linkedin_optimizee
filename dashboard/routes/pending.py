"""The human review surface. This blueprint can only reach
approve_action()/decline_action() (caller_role="human", hardcoded here,
never taken from the request) -- it has no path to
execute_approved_action() at all. Execution is a separate process
(run_executor.py); nothing in this file imports control_center.executor.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from control_center import actions, approvals
from control_center.exceptions import ActionNotFoundError, ContentHashMismatchError, InvalidTransitionError

from ..auth import protect_blueprint
from ..csrf import csrf_protect

bp = Blueprint("pending", __name__)
protect_blueprint(bp)


@bp.route("/pending")
def list_pending():
    pending = actions.list_actions(g.conn, status="PENDING")
    return render_template("pending.html", actions=pending)


@bp.route("/actions/<action_id>")
def detail(action_id: str):
    action = actions.get_action(g.conn, action_id)
    if action is None:
        abort(404)
    return render_template("action_detail.html", action=action)


@bp.route("/actions/<action_id>/approve", methods=["POST"])
@csrf_protect
def approve(action_id: str):
    expected_hash = request.form.get("expected_hash", "")
    try:
        approvals.approve_action(
            g.conn,
            caller_role="human",
            action_id=action_id,
            approved_by=session["user"],
            expected_hash=expected_hash,
        )
        flash(f"Approved. It will be executed by the execution service, not by this dashboard.")
    except ActionNotFoundError:
        abort(404)
    except ContentHashMismatchError:
        flash(
            "Refused: this action's content no longer matches what was shown. "
            "Reload the page and review the current content before approving.",
            "error",
        )
    except InvalidTransitionError as exc:
        flash(f"Refused: {exc}", "error")
    return redirect(url_for("pending.detail", action_id=action_id))


@bp.route("/actions/<action_id>/decline", methods=["POST"])
@csrf_protect
def decline(action_id: str):
    reason = request.form.get("reason", "")
    try:
        approvals.decline_action(
            g.conn,
            caller_role="human",
            action_id=action_id,
            declined_by=session["user"],
            reason=reason or None,
        )
        flash("Declined.")
    except ActionNotFoundError:
        abort(404)
    except InvalidTransitionError as exc:
        flash(f"Refused: {exc}", "error")
    return redirect(url_for("pending.detail", action_id=action_id))
