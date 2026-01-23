/**
 * Authentication settings module for the Settings page.
 * Handles loading/saving auth settings and password changes.
 */

let authLoaded = false;
let runtimeSessionTimeout = null;  // Timeout value at app startup

/**
 * Initialize the auth settings tab.
 */
export function initAuthSettings() {
    console.log('Auth settings module initialized');
    
    // Bind event listeners
    const saveSettingsBtn = document.getElementById('save-auth-settings');
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', saveAuthSettings);
    }
    
    const changePasswordForm = document.getElementById('change-password-form');
    if (changePasswordForm) {
        changePasswordForm.addEventListener('submit', handlePasswordChange);
    }
    
    const authEnabledToggle = document.getElementById('auth-enabled');
    if (authEnabledToggle) {
        authEnabledToggle.addEventListener('change', updateAuthUI);
    }
    
    // Listen for timeout changes to update restart warning
    const sessionTimeoutSelect = document.getElementById('session-timeout');
    if (sessionTimeoutSelect) {
        sessionTimeoutSelect.addEventListener('change', updateRestartWarning);
    }
}

/**
 * Load auth settings from the API.
 */
export async function loadAuthSettings() {
    if (authLoaded) return;
    
    try {
        const response = await fetch('/api/v1/auth/settings');
        if (!response.ok) {
            if (response.status === 401) {
                // Not logged in, settings not available
                showAuthDisabledState();
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        if (data.data) {
            populateAuthSettings(data.data);
            authLoaded = true;
        } else {
            console.error('Failed to load auth settings:', data.error?.message);
        }
    } catch (error) {
        console.error('Error loading auth settings:', error);
    }
}

/**
 * Populate the form with loaded settings.
 */
function populateAuthSettings(settings) {
    const authEnabledToggle = document.getElementById('auth-enabled');
    const sessionTimeoutSelect = document.getElementById('session-timeout');
    
    if (authEnabledToggle) {
        authEnabledToggle.checked = settings.enabled;
    }
    
    if (sessionTimeoutSelect) {
        sessionTimeoutSelect.value = settings.session_timeout_minutes.toString();
    }
    
    // Store the runtime timeout for restart warning comparison
    runtimeSessionTimeout = settings.runtime_session_timeout_minutes;
    
    updateAuthUI();
    updateRestartWarning();
}

/**
 * Update UI based on auth enabled state.
 */
function updateAuthUI() {
    const authEnabled = document.getElementById('auth-enabled')?.checked;
    const passwordSection = document.getElementById('change-password-section');
    const authDisabledInfo = document.getElementById('auth-disabled-info');
    
    if (passwordSection) {
        passwordSection.style.display = authEnabled ? 'block' : 'none';
    }
    
    if (authDisabledInfo) {
        authDisabledInfo.style.display = authEnabled ? 'none' : 'block';
    }
}

/**
 * Update restart warning visibility based on timeout difference.
 */
function updateRestartWarning() {
    const restartWarning = document.getElementById('restart-warning');
    const sessionTimeoutSelect = document.getElementById('session-timeout');
    
    if (!restartWarning || !sessionTimeoutSelect || runtimeSessionTimeout === null) {
        return;
    }
    
    const currentValue = parseInt(sessionTimeoutSelect.value, 10);
    const needsRestart = currentValue !== runtimeSessionTimeout;
    
    restartWarning.style.display = needsRestart ? 'block' : 'none';
}

/**
 * Show state when auth is not configured/accessible.
 */
function showAuthDisabledState() {
    const authEnabledToggle = document.getElementById('auth-enabled');
    if (authEnabledToggle) {
        authEnabledToggle.checked = false;
    }
    updateAuthUI();
}

/**
 * Save auth settings to the API.
 */
async function saveAuthSettings() {
    const saveBtn = document.getElementById('save-auth-settings');
    const statusSpan = document.getElementById('auth-settings-status');
    
    const authEnabled = document.getElementById('auth-enabled')?.checked;
    const sessionTimeout = document.getElementById('session-timeout')?.value;
    
    // Show loading state
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    }
    
    try {
        const response = await fetch('/api/v1/auth/settings', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                enabled: authEnabled,
                session_timeout_minutes: parseInt(sessionTimeout, 10),
            }),
        });
        
        const data = await response.json();
        
        if (response.ok && data.data) {
            showStatus(statusSpan, 'Settings saved!', 'success');
            
            // If auth was disabled, we might need to reload
            if (!authEnabled) {
                showStatus(statusSpan, 'Settings saved! Auth disabled.', 'success');
            }
        } else {
            showStatus(statusSpan, data.error?.message || 'Failed to save settings', 'error');
        }
    } catch (error) {
        console.error('Error saving auth settings:', error);
        showStatus(statusSpan, 'Failed to save settings', 'error');
    } finally {
        // Reset button
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fas fa-save"></i> Save Settings';
        }
    }
}

/**
 * Handle password change form submission.
 */
async function handlePasswordChange(event) {
    event.preventDefault();
    
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const statusSpan = document.getElementById('password-change-status');
    
    const currentPassword = document.getElementById('current-password')?.value;
    const newPassword = document.getElementById('new-password')?.value;
    const confirmPassword = document.getElementById('confirm-new-password')?.value;
    
    // Client-side validation
    if (!currentPassword || !newPassword || !confirmPassword) {
        showStatus(statusSpan, 'All fields are required', 'error');
        return;
    }
    
    if (newPassword.length < 8) {
        showStatus(statusSpan, 'Password must be at least 8 characters', 'error');
        return;
    }
    
    if (newPassword !== confirmPassword) {
        showStatus(statusSpan, 'Passwords do not match', 'error');
        return;
    }
    
    // Show loading state
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Changing...';
    }
    
    try {
        const response = await fetch('/api/v1/auth/password', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword,
            }),
        });
        
        const data = await response.json();
        
        if (response.ok && data.data) {
            showStatus(statusSpan, 'Password changed successfully!', 'success');
            // Clear form
            document.getElementById('change-password-form')?.reset();
        } else {
            showStatus(statusSpan, data.error?.message || 'Failed to change password', 'error');
        }
    } catch (error) {
        console.error('Error changing password:', error);
        showStatus(statusSpan, 'Failed to change password', 'error');
    } finally {
        // Reset button
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-lock"></i> Change Password';
        }
    }
}

/**
 * Show status message.
 */
function showStatus(element, message, type) {
    if (!element) return;
    
    element.textContent = message;
    element.className = `status-message status-${type}`;
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        element.textContent = '';
        element.className = 'status-message';
    }, 5000);
}
