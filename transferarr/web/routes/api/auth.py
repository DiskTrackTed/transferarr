"""
API routes for authentication settings.

These endpoints allow managing auth settings and changing the password
from the Settings page.
"""
from functools import wraps

from flask import request, current_app
from flask_login import login_required, current_user, logout_user

from transferarr.auth import (
    get_auth_config,
    hash_password,
    verify_password,
    save_auth_config,
    is_auth_enabled,
)
from transferarr.web.routes.api.responses import success_response, error_response


def auth_api_required(f):
    """Decorator for auth settings endpoints.
    
    - If auth is enabled: requires login
    - If auth is disabled: allows access (for settings page to work)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if is_auth_enabled(current_app.config['APP_CONFIG']):
            if not current_user.is_authenticated:
                return error_response('UNAUTHORIZED', 'Authentication required', 401)
        return f(*args, **kwargs)
    return decorated_function


def register_routes(api_bp):
    """Register auth API routes on the given blueprint."""
    
    @api_bp.route('/auth/settings', methods=['GET'])
    @auth_api_required
    def get_auth_settings():
        """Get current auth settings.
        ---
        tags:
          - Authentication
        responses:
          200:
            description: Auth settings (without password_hash)
            schema:
              type: object
              properties:
                success:
                  type: boolean
                data:
                  type: object
                  properties:
                    enabled:
                      type: boolean
                    username:
                      type: string
                    session_timeout_minutes:
                      type: integer
          401:
            description: Authentication required
        """
        auth = get_auth_config(current_app.config['APP_CONFIG'])
        return success_response({
            'enabled': auth['enabled'],
            'username': auth['username'],
            'session_timeout_minutes': auth['session_timeout_minutes'],
            'runtime_session_timeout_minutes': current_app.config.get('RUNTIME_SESSION_TIMEOUT', 60),
        })
    
    @api_bp.route('/auth/settings', methods=['PUT'])
    @auth_api_required
    def update_auth_settings():
        """Update auth settings (enable/disable, change timeout).
        ---
        tags:
          - Authentication
        parameters:
          - in: body
            name: body
            required: true
            schema:
              type: object
              properties:
                enabled:
                  type: boolean
                  description: Enable or disable authentication
                session_timeout_minutes:
                  type: integer
                  description: Session timeout in minutes (0 for never)
        responses:
          200:
            description: Settings updated successfully
          400:
            description: Invalid request
          401:
            description: Authentication required
        """
        data = request.get_json()
        if not data:
            return error_response('BAD_REQUEST', 'Request body required', 400)
        
        updates = {}
        if 'enabled' in data:
            updates['enabled'] = bool(data['enabled'])
        if 'session_timeout_minutes' in data:
            try:
                timeout = int(data['session_timeout_minutes'])
                if timeout < 0:
                    return error_response('BAD_REQUEST', 'Timeout must be non-negative', 400)
                updates['session_timeout_minutes'] = timeout
            except (ValueError, TypeError):
                return error_response('BAD_REQUEST', 'Invalid timeout value', 400)
        
        if updates:
            save_auth_config(current_app.config['APP_CONFIG'], updates)
            
            # If auth was just enabled, invalidate current session
            # so user must log in with the new credentials
            if updates.get('enabled') is True:
                logout_user()
        
        return success_response({'message': 'Settings updated'})
    
    @api_bp.route('/auth/password', methods=['PUT'])
    @login_required
    def change_password():
        """Change the current user's password.
        ---
        tags:
          - Authentication
        parameters:
          - in: body
            name: body
            required: true
            schema:
              type: object
              required:
                - current_password
                - new_password
                - confirm_password
              properties:
                current_password:
                  type: string
                  description: Current password for verification
                new_password:
                  type: string
                  description: New password (min 8 characters)
                confirm_password:
                  type: string
                  description: Confirm new password
        responses:
          200:
            description: Password changed successfully
          400:
            description: Validation error (wrong password, mismatch, etc.)
          401:
            description: Authentication required
        """
        data = request.get_json()
        if not data:
            return error_response('BAD_REQUEST', 'Request body required', 400)
        
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')
        
        auth = get_auth_config(current_app.config['APP_CONFIG'])
        
        # Verify current password
        if not verify_password(current_password, auth['password_hash']):
            return error_response('INVALID_PASSWORD', 'Current password is incorrect', 400)
        
        # Validate new password
        if len(new_password) < 8:
            return error_response('WEAK_PASSWORD', 'Password must be at least 8 characters', 400)
        
        if new_password != confirm_password:
            return error_response('PASSWORD_MISMATCH', 'Passwords do not match', 400)
        
        # Save new password
        save_auth_config(current_app.config['APP_CONFIG'], {
            'password_hash': hash_password(new_password)
        })
        
        return success_response({'message': 'Password changed successfully'})
