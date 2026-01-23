from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, current_app
from flask_login import login_required

from transferarr.auth import is_auth_enabled, is_auth_configured


def auth_required(f):
    """Decorator that applies login_required only if auth is enabled.
    
    Also redirects to setup page if auth is not yet configured.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Redirect to setup if not configured
        if not is_auth_configured(current_app.config['APP_CONFIG']):
            return redirect(url_for('auth.setup'))
        # Apply login_required if auth is enabled
        if is_auth_enabled(current_app.config['APP_CONFIG']):
            return login_required(f)(*args, **kwargs)
        return f(*args, **kwargs)
    return decorated_function


ui_bp = Blueprint('ui', __name__)


@ui_bp.route("/")
@auth_required
def dashboard_page():
    """Render the dashboard page."""
    return render_template("pages/dashboard.html")


@ui_bp.route("/torrents")
@auth_required
def torrents_page():
    """Render the torrents page."""
    return render_template("pages/torrents.html")


@ui_bp.route("/history")
@auth_required
def history_page():
    """Render the transfer history page."""
    return render_template("pages/history.html")


@ui_bp.route("/settings")
@auth_required
def settings_page():
    """Render the settings page."""
    return render_template("pages/settings.html")