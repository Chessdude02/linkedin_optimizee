from .audit import bp as audit_bp
from .dashboard import bp as dashboard_bp
from .pending import bp as pending_bp
from .system import bp as system_bp

__all__ = ["dashboard_bp", "pending_bp", "audit_bp", "system_bp"]
