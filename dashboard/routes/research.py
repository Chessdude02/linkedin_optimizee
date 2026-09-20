"""The human review surface for research findings -- separate from
pending.py (which handles actual actions). This blueprint can create a
PENDING action (via research.convert_to_action, itself the only bridge
into the Action Queue) but that conversion still requires a further,
separate Approve click under Pending Actions -- converting a finding
never approves it.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from control_center import research
from control_center.exceptions import AlreadyConvertedError, ResearchItemNotFoundError

from ..auth import protect_blueprint
from ..csrf import csrf_protect

bp = Blueprint("research", __name__)
protect_blueprint(bp)


@bp.route("/research")
def index():
    status_filter = request.args.get("status") or "SURFACED"
    items = research.list_items(g.conn, status=status_filter if status_filter != "ALL" else None)
    runs = research.list_runs(g.conn, limit=5)
    return render_template("research.html", items=items, runs=runs, status_filter=status_filter)


@bp.route("/research/<item_id>")
def detail(item_id: str):
    item = research.get_item(g.conn, item_id)
    if item is None:
        abort(404)
    return render_template("research_detail.html", item=item)


@bp.route("/research/<item_id>/save", methods=["POST"])
@csrf_protect
def save(item_id: str):
    try:
        research.set_status(g.conn, item_id, research.SAVED)
        flash("Saved.")
    except ResearchItemNotFoundError:
        abort(404)
    return redirect(url_for("research.detail", item_id=item_id))


@bp.route("/research/<item_id>/dismiss", methods=["POST"])
@csrf_protect
def dismiss(item_id: str):
    try:
        research.set_status(g.conn, item_id, research.DISMISSED)
        flash("Dismissed. It won't be shown again automatically, but the record is kept.")
    except ResearchItemNotFoundError:
        abort(404)
    return redirect(url_for("research.index"))


@bp.route("/research/<item_id>/convert", methods=["POST"])
@csrf_protect
def convert(item_id: str):
    try:
        result = research.convert_to_action(g.conn, item_id, created_by=session["user"])
        flash(
            f"Created action proposal {result['action_id']} (status: {result['status']}). "
            "It still needs your separate approval under Pending Actions -- nothing was "
            "approved or executed by converting it.",
        )
        return redirect(url_for("pending.detail", action_id=result["action_id"]))
    except ResearchItemNotFoundError:
        abort(404)
    except AlreadyConvertedError as exc:
        flash(str(exc), "error")
        return redirect(url_for("research.detail", item_id=item_id))
