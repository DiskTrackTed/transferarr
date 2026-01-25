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

from transferarr.auth import (
    is_auth_enabled,
    is_auth_configured,
    is_api_key_required,
    check_api_key_in_request,
    get_api_config,
)
from transferarr.web.routes.api.responses import error_response

# Create the main API blueprint with version prefix
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')


@api_bp.before_request
def check_api_auth():
    """Check authentication for API routes (except health).
    
    This middleware runs before every API request and:
    - Always allows the health endpoint (for monitoring)
    - Allows all requests if auth is not configured yet
    - Allows all requests if neither user auth nor API key is required
    - Allows requests from authenticated users (session-based)
    - Allows requests with valid API key
    - Returns 401 for unauthenticated requests when auth is enabled
    """
    config = current_app.config['APP_CONFIG']
    
    # Always allow health endpoint
    if request.endpoint == 'api.health_check':
        return None
    
    # If auth not configured, allow all (setup not done yet)
    if not is_auth_configured(config):
        return None
    
    # Check if any authentication is required
    user_auth_enabled = is_auth_enabled(config)
    api_key_required = is_api_key_required(config)
    
    # If neither user auth nor API key is required, allow all
    if not user_auth_enabled and not api_key_required:
        return None
    
    # If user is logged in via session, allow
    if current_user.is_authenticated:
        return None
    
    # Check API key if configured
    if api_key_required:
        if check_api_key_in_request(config, request):
            return None
        # API key is required but invalid/missing
        return error_response("UNAUTHORIZED", "Invalid or missing API key", status_code=401)
    
    # User auth is enabled but no session - check if they provided API key anyway
    # (API key can be used even when key_required=False, as long as key exists)
    api_config = get_api_config(config)
    if api_config.get("key") and check_api_key_in_request(config, request):
        return None
    
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
