from flask import Blueprint, render_template

ui_bp = Blueprint('ui', __name__)

@ui_bp.route("/")
def dashboard_page():
    """Render the dashboard page."""
    return render_template("pages/dashboard.html")

@ui_bp.route("/torrents")
def torrents_page():
    """Render the torrents page."""
    return render_template("pages/torrents.html")

@ui_bp.route("/history")
def history_page():
    """Render the transfer history page."""
    return render_template("pages/history.html")


@ui_bp.route("/settings")
def settings_page():
    """Render the settings page."""
    return render_template("pages/settings.html")