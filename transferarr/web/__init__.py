from flask import Flask
from flasgger import Swagger
from transferarr import __version__

def create_app(config, torrent_manager):
    app = Flask(__name__, 
                static_folder="static",
                template_folder="templates")
    
    # Store torrent_manager in app configuration
    app.config['TORRENT_MANAGER'] = torrent_manager
    
    # Configure Swagger/OpenAPI documentation
    app.config['SWAGGER'] = {
        'title': 'Transferarr API',
        'description': 'API for managing torrent transfers between download clients',
        'version': __version__,
        'uiversion': 3,
        'specs_route': '/apidocs/',
        'definitions': {
            'Transfer': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'string', 'description': 'Unique transfer UUID'},
                    'torrent_name': {'type': 'string', 'description': 'Name of the torrent'},
                    'torrent_hash': {'type': 'string', 'description': 'Torrent info hash'},
                    'source_client': {'type': 'string', 'description': 'Source download client name'},
                    'target_client': {'type': 'string', 'description': 'Target download client name'},
                    'connection_name': {'type': 'string', 'description': 'Transfer connection name'},
                    'media_type': {'type': 'string', 'enum': ['movie', 'episode', 'unknown'], 'description': 'Type of media'},
                    'media_manager': {'type': 'string', 'enum': ['radarr', 'sonarr'], 'description': 'Media manager that owns this torrent'},
                    'size_bytes': {'type': 'integer', 'description': 'Total size in bytes'},
                    'bytes_transferred': {'type': 'integer', 'description': 'Bytes transferred so far'},
                    'status': {'type': 'string', 'enum': ['pending', 'transferring', 'completed', 'failed', 'cancelled'], 'description': 'Current transfer status'},
                    'error_message': {'type': 'string', 'description': 'Error message if status is failed'},
                    'created_at': {'type': 'string', 'format': 'date-time', 'description': 'When the transfer was created'},
                    'started_at': {'type': 'string', 'format': 'date-time', 'description': 'When the transfer started'},
                    'completed_at': {'type': 'string', 'format': 'date-time', 'description': 'When the transfer completed or failed'}
                }
            }
        }
    }
    Swagger(app)
    
    # Inject version into all templates
    @app.context_processor
    def inject_version():
        return {'version': __version__}
    
    # Configure logging for Flask
    if config.get("web_log_file"):
        configure_flask_logging(app, config)
    
    # Register blueprints
    from transferarr.web.routes.api import api_bp
    from transferarr.web.routes.ui import ui_bp
    
    app.register_blueprint(api_bp)
    app.register_blueprint(ui_bp)
    
    return app

def configure_flask_logging(app, config):
    """Configure Flask logging to file"""
    import logging
    from logging.handlers import RotatingFileHandler
    import os
    
    flask_log_file = config.get("web_log_file")
    log_dir = os.path.dirname(flask_log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    flask_handler = RotatingFileHandler(
        flask_log_file, 
        maxBytes=10485760,
        backupCount=5
    )
    flask_handler.setLevel(logging.INFO)
    flask_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    flask_logger = logging.getLogger('werkzeug')
    flask_logger.setLevel(logging.INFO)
    flask_logger.addHandler(flask_handler)
    flask_logger.propagate = False
    
    app.logger.addHandler(flask_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False