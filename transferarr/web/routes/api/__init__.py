"""
API Blueprint package for Transferarr.

This package organizes API routes into domain-specific modules:
- system: Health check, config endpoints
- download_clients: Download client CRUD operations
- connections: Transfer connection CRUD operations
- torrents: Torrent listing and status
- utilities: File browsing utilities
"""
from flask import Blueprint, request, current_app
from flask_login import current_user

from transferarr.auth import is_auth_enabled, is_auth_configured
from transferarr.web.routes.api.responses import error_response

# Create the main API blueprint with version prefix
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


@api_bp.before_request
def check_api_auth():
    """Check authentication for API routes (except health).
    
    This middleware runs before every API request and:
    - Always allows the health endpoint (for monitoring)
    - Allows all requests if auth is not configured yet
    - Allows all requests if auth is disabled
    - Allows requests from authenticated users (session-based)
    - Returns 401 for unauthenticated requests when auth is enabled
    
    TODO: Issue #3 - Add API key support here
    """
    # Always allow health endpoint
    if request.endpoint == 'api.health_check':
        return None
    
    # If auth not configured, allow all (setup not done yet)
    if not is_auth_configured(current_app.config['APP_CONFIG']):
        return None
    
    # If auth not enabled, allow all
    if not is_auth_enabled(current_app.config['APP_CONFIG']):
        return None
    
    # If user is logged in via session, allow
    if current_user.is_authenticated:
        return None
    
    # TODO: Issue #3 - Add API key check here
    # Check X-API-Key header or ?apikey= query param against configured keys
    
    # Otherwise deny
    return error_response("UNAUTHORIZED", "Authentication required", status_code=401)


# Import and register routes from each module
from . import system
from . import download_clients
from . import connections
from . import torrents
from . import utilities
from . import transfers
from . import auth

# Register all routes with the blueprint
system.register_routes(api_bp)
download_clients.register_routes(api_bp)
connections.register_routes(api_bp)
torrents.register_routes(api_bp)
utilities.register_routes(api_bp)
transfers.register_routes(api_bp)
auth.register_routes(api_bp)
