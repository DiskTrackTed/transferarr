"""Authentication routes for login, logout, and first-run setup."""
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user

from transferarr.auth import (
    User, verify_password, hash_password, get_auth_config,
    is_auth_enabled, is_auth_configured, save_auth_config
)

auth_bp = Blueprint('auth', __name__)


def needs_setup() -> bool:
    """Check if first-run setup is needed.
    
    Returns True if auth has not been configured (neither enabled nor explicitly disabled).
    """
    return not is_auth_configured(current_app.config['APP_CONFIG'])


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-run setup page.
    
    Allows user to either:
    - Create a username/password for authentication
    - Skip authentication (disable it)
    
    Redirects to dashboard if already configured.
    """
    # If already configured, redirect to dashboard
    if not needs_setup():
        return redirect(url_for('ui.dashboard_page'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'skip':
            # Disable auth
            save_auth_config(current_app.config['APP_CONFIG'], {
                'enabled': False,
                'username': None,
                'password_hash': None,
            })
            return redirect(url_for('ui.dashboard_page'))
        
        elif action == 'create':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm = request.form.get('confirm_password', '')
            
            if not username:
                flash('Username is required', 'error')
            elif len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
            elif password != confirm:
                flash('Passwords do not match', 'error')
            else:
                # Save auth config
                save_auth_config(current_app.config['APP_CONFIG'], {
                    'enabled': True,
                    'username': username,
                    'password_hash': hash_password(password),
                })
                
                # Log in the user
                user = User(username)
                login_user(user, remember=True)
                session.permanent = True  # Enable session timeout
                
                flash('Authentication configured successfully', 'success')
                return redirect(url_for('ui.dashboard_page'))
    
    return render_template('pages/setup.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and form handler.
    
    Redirects to:
    - /setup if first-run setup is needed
    - Dashboard if auth is disabled or user already logged in
    """
    # If setup needed, redirect to setup
    if needs_setup():
        return redirect(url_for('auth.setup'))
    
    # If auth disabled, redirect to dashboard
    if not is_auth_enabled(current_app.config['APP_CONFIG']):
        return redirect(url_for('ui.dashboard_page'))
    
    # If already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('ui.dashboard_page'))
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        remember = request.form.get('remember', False) == 'on'
        
        auth_config = get_auth_config(current_app.config['APP_CONFIG'])
        
        if username == auth_config['username'] and verify_password(password, auth_config['password_hash']):
            user = User(username)
            login_user(user, remember=remember)
            session.permanent = True  # Enable session timeout
            
            # Redirect to requested page or dashboard
            # Sanitize next_page to prevent open redirect attacks
            next_page = request.args.get('next')
            if next_page and not next_page.startswith('/'):
                next_page = None  # Reject external URLs
            return redirect(next_page or url_for('ui.dashboard_page'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('pages/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the current user and redirect to login page."""
    logout_user()
    return redirect(url_for('auth.login'))
