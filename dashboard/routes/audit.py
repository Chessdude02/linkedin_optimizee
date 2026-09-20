from flask import Blueprint, g, render_template, request

from control_center import audit

from ..auth import protect_blueprint

bp = Blueprint("audit", __name__)
protect_blueprint(bp)


@bp.route("/audit")
def index():
    event_type = request.args.get("event_type") or None
    action_id = request.args.get("action_id") or None
    events = audit.list_events(g.conn, action_id=action_id, event_type=event_type, limit=200)
    return render_template(
        "audit.html", events=events, event_type=event_type or "", action_id=action_id or ""
    )
