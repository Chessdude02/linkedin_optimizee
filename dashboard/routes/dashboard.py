from flask import Blueprint, g, render_template

from control_center import actions, kill_switch

from ..auth import protect_blueprint

bp = Blueprint("dashboard", __name__)
protect_blueprint(bp)

_ALL_STATUSES = ("PENDING", "APPROVED", "EXECUTING", "EXECUTED", "DECLINED", "EXPIRED", "FAILED", "BLOCKED")


@bp.route("/")
def index():
    raw_counts = actions.count_by_status(g.conn)
    counts = {status: raw_counts.get(status, 0) for status in _ALL_STATUSES}
    write_enabled = kill_switch.get_write_enabled(g.conn)
    return render_template("dashboard.html", counts=counts, write_enabled=write_enabled)
