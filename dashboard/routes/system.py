from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from control_center import kill_switch, settings

from ..auth import protect_blueprint
from ..csrf import csrf_protect

bp = Blueprint("system", __name__)
protect_blueprint(bp)


@bp.route("/system")
def index():
    write_enabled = kill_switch.get_write_enabled(g.conn)
    return render_template(
        "system.html",
        write_enabled=write_enabled,
        mock_execution=settings.MOCK_EXECUTION,
    )


@bp.route("/system/write-enabled", methods=["POST"])
@csrf_protect
def set_write_enabled():
    enabled = request.form.get("enabled") == "true"
    kill_switch.set_write_enabled(g.conn, enabled, actor=session["user"])
    flash("🟢 Writes ENABLED." if enabled else "🔴 ALL WRITES DISABLED (kill switch engaged).")
    return redirect(url_for("system.index"))
