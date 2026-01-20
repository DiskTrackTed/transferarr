"""
API Blueprint package for Transferarr.

This package organizes API routes into domain-specific modules:
- system: Health check, config endpoints
- download_clients: Download client CRUD operations
- connections: Transfer connection CRUD operations
- torrents: Torrent listing and status
- utilities: File browsing utilities
"""
from flask import Blueprint

# Create the main API blueprint with version prefix
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# Import and register routes from each module
from . import system
from . import download_clients
from . import connections
from . import torrents
from . import utilities
from . import transfers

# Register all routes with the blueprint
system.register_routes(api_bp)
download_clients.register_routes(api_bp)
connections.register_routes(api_bp)
torrents.register_routes(api_bp)
utilities.register_routes(api_bp)
transfers.register_routes(api_bp)
