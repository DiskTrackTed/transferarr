/**
 * Authentication settings module for the Settings page.
 * Handles loading/saving auth settings and password changes.
 */

let authLoaded = false;
let runtimeSessionTimeout = null;  // Timeout value at app startup
let initialAuthEnabled = null;  // Auth state when page loaded

// API Key state
let apiKeyVisible = false;
let currentApiKey = null;
let initialKeyRequired = null;

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
    
    // API Key event listeners
    initApiKeyListeners();
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
    
    // Also load API key settings
    await loadApiKeySettings();
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
    
    // Store initial auth state to detect when it's newly enabled
    initialAuthEnabled = settings.enabled;
    
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
    
    // Update API key warning when auth state changes
    updateApiKeyAuthWarning();
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
            // If auth was just enabled (was disabled, now enabled), redirect to login
            // (session was invalidated server-side)
            if (authEnabled && !initialAuthEnabled) {
                TransferarrNotifications.success('Auth Enabled', 'Redirecting to login...');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1500);
            } else if (!authEnabled) {
                TransferarrNotifications.success('Settings Saved', 'Authentication disabled.');
            } else {
                TransferarrNotifications.success('Settings Saved', 'Authentication settings updated.');
            }
        } else {
            TransferarrNotifications.error('Save Failed', data.error?.message || 'Failed to save settings');
        }
    } catch (error) {
        console.error('Error saving auth settings:', error);
        TransferarrNotifications.error('Save Failed', 'Failed to save settings');
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
    
    const currentPassword = document.getElementById('current-password')?.value;
    const newPassword = document.getElementById('new-password')?.value;
    const confirmPassword = document.getElementById('confirm-new-password')?.value;
    
    // Client-side validation
    if (!currentPassword || !newPassword || !confirmPassword) {
        TransferarrNotifications.error('Validation Error', 'All fields are required');
        return;
    }
    
    if (newPassword.length < 8) {
        TransferarrNotifications.error('Validation Error', 'Password must be at least 8 characters');
        return;
    }
    
    if (newPassword !== confirmPassword) {
        TransferarrNotifications.error('Validation Error', 'Passwords do not match');
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
            TransferarrNotifications.success('Password Changed', 'Your password has been updated.');
            // Clear form
            document.getElementById('change-password-form')?.reset();
        } else {
            TransferarrNotifications.error('Password Change Failed', data.error?.message || 'Failed to change password');
        }
    } catch (error) {
        console.error('Error changing password:', error);
        TransferarrNotifications.error('Password Change Failed', 'Failed to change password');
    } finally {
        // Reset button
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-lock"></i> Change Password';
        }
    }
}

// =============================================================================
// API Key Management
// =============================================================================

/**
 * Initialize API key event listeners.
 */
function initApiKeyListeners() {
    const generateBtn = document.getElementById('generate-api-key');
    if (generateBtn) {
        generateBtn.addEventListener('click', generateApiKey);
    }
    
    const revokeBtn = document.getElementById('revoke-api-key');
    if (revokeBtn) {
        revokeBtn.addEventListener('click', revokeApiKey);
    }
    
    const toggleVisibilityBtn = document.getElementById('toggle-api-key-visibility');
    if (toggleVisibilityBtn) {
        toggleVisibilityBtn.addEventListener('click', toggleApiKeyVisibility);
    }
    
    const copyBtn = document.getElementById('copy-api-key');
    if (copyBtn) {
        copyBtn.addEventListener('click', copyApiKey);
    }
    
    const keyRequiredToggle = document.getElementById('api-key-required');
    if (keyRequiredToggle) {
        keyRequiredToggle.addEventListener('change', onKeyRequiredChange);
    }
    
    const saveApiKeySettingsBtn = document.getElementById('save-api-key-settings');
    if (saveApiKeySettingsBtn) {
        saveApiKeySettingsBtn.addEventListener('click', saveApiKeySettings);
    }
}

/**
 * Load API key settings from the API.
 */
async function loadApiKeySettings() {
    try {
        const response = await fetch('/api/v1/auth/api-key');
        if (!response.ok) {
            if (response.status === 401) {
                return; // Not logged in
            }
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        if (data.data) {
            populateApiKeySettings(data.data);
        }
    } catch (error) {
        console.error('Error loading API key settings:', error);
    }
}

/**
 * Populate API key settings in the UI.
 */
function populateApiKeySettings(settings) {
    const keyRequiredToggle = document.getElementById('api-key-required');
    const apiKeyInput = document.getElementById('api-key-value');
    const generateBtn = document.getElementById('generate-api-key');
    const generateBtnText = document.getElementById('generate-api-key-text');
    const revokeBtn = document.getElementById('revoke-api-key');
    
    currentApiKey = settings.key;
    initialKeyRequired = settings.key_required;
    
    if (keyRequiredToggle) {
        keyRequiredToggle.checked = settings.key_required;
    }
    
    if (apiKeyInput) {
        if (settings.key) {
            apiKeyInput.value = maskApiKey(settings.key);
            apiKeyInput.classList.add('masked');
            apiKeyInput.placeholder = '';
        } else {
            apiKeyInput.value = '';
            apiKeyInput.placeholder = 'No API key generated';
        }
    }
    
    // Update button visibility
    if (generateBtn && generateBtnText) {
        generateBtnText.textContent = settings.key ? 'Regenerate Key' : 'Generate API Key';
    }
    
    if (revokeBtn) {
        revokeBtn.style.display = settings.key ? 'inline-flex' : 'none';
    }
    
    // Reset visibility state
    apiKeyVisible = false;
    updateVisibilityIcon();
    
    // Update API key auth warning
    updateApiKeyAuthWarning();
}

/**
 * Update the warning that shows when API key exists but auth is disabled.
 */
function updateApiKeyAuthWarning() {
    const warning = document.getElementById('api-key-auth-warning');
    const authEnabled = document.getElementById('auth-enabled')?.checked;
    
    if (warning) {
        // Show warning if: API key exists AND auth is disabled
        const shouldShow = currentApiKey && !authEnabled;
        warning.style.display = shouldShow ? 'block' : 'none';
    }
}

/**
 * Mask the API key for display.
 */
function maskApiKey(key) {
    if (!key) return '';
    // Show prefix (tr_) and first 4 chars, mask the rest
    const visiblePart = key.substring(0, 7); // tr_ + 4 chars
    const maskedPart = '•'.repeat(Math.max(0, key.length - 7));
    return visiblePart + maskedPart;
}

/**
 * Toggle API key visibility.
 */
function toggleApiKeyVisibility() {
    if (!currentApiKey) return;
    
    apiKeyVisible = !apiKeyVisible;
    const apiKeyInput = document.getElementById('api-key-value');
    
    if (apiKeyInput) {
        if (apiKeyVisible) {
            apiKeyInput.value = currentApiKey;
            apiKeyInput.classList.remove('masked');
        } else {
            apiKeyInput.value = maskApiKey(currentApiKey);
            apiKeyInput.classList.add('masked');
        }
    }
    
    updateVisibilityIcon();
}

/**
 * Update the visibility toggle icon.
 */
function updateVisibilityIcon() {
    const toggleBtn = document.getElementById('toggle-api-key-visibility');
    if (toggleBtn) {
        const icon = toggleBtn.querySelector('i');
        if (icon) {
            icon.className = apiKeyVisible ? 'fas fa-eye-slash' : 'fas fa-eye';
        }
    }
}

/**
 * Copy API key to clipboard.
 */
async function copyApiKey() {
    if (!currentApiKey) {
        TransferarrNotifications.error('Copy Failed', 'No API key to copy');
        return;
    }
    
    try {
        await navigator.clipboard.writeText(currentApiKey);
        TransferarrNotifications.success('Copied', 'API key copied to clipboard!');
    } catch (error) {
        console.error('Failed to copy API key:', error);
        TransferarrNotifications.error('Copy Failed', 'Failed to copy to clipboard');
    }
}

/**
 * Generate a new API key.
 */
async function generateApiKey() {
    const generateBtn = document.getElementById('generate-api-key');
    
    // Confirm if regenerating
    if (currentApiKey) {
        if (!confirm('Are you sure you want to regenerate the API key? The old key will stop working immediately.')) {
            return;
        }
    }
    
    if (generateBtn) {
        generateBtn.disabled = true;
        generateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
    }
    
    try {
        const response = await fetch('/api/v1/auth/api-key/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        
        const data = await response.json();
        
        if (response.ok && data.data) {
            currentApiKey = data.data.key;
            
            // Show the new key (visible by default)
            const apiKeyInput = document.getElementById('api-key-value');
            if (apiKeyInput) {
                apiKeyInput.value = currentApiKey;
                apiKeyInput.classList.remove('masked');
            }
            apiKeyVisible = true;
            updateVisibilityIcon();
            
            // Update button text
            const generateBtnText = document.getElementById('generate-api-key-text');
            if (generateBtnText) {
                generateBtnText.textContent = 'Regenerate Key';
            }
            
            // Show revoke button
            const revokeBtn = document.getElementById('revoke-api-key');
            if (revokeBtn) {
                revokeBtn.style.display = 'inline-flex';
            }
            
            // Update warning (new key may trigger warning if auth disabled)
            updateApiKeyAuthWarning();
            
            TransferarrNotifications.success('API Key Generated', 'New API key generated! Make sure to save it.');
        } else {
            TransferarrNotifications.error('Generation Failed', data.error?.message || 'Failed to generate API key');
        }
    } catch (error) {
        console.error('Error generating API key:', error);
        TransferarrNotifications.error('Generation Failed', 'Failed to generate API key');
    } finally {
        if (generateBtn) {
            generateBtn.disabled = false;
            const generateBtnText = document.getElementById('generate-api-key-text');
            generateBtn.innerHTML = `<i class="fas fa-sync-alt"></i> <span id="generate-api-key-text">${generateBtnText?.textContent || 'Generate API Key'}</span>`;
        }
    }
}

/**
 * Revoke the current API key.
 */
async function revokeApiKey() {
    if (!confirm('Are you sure you want to revoke the API key? Any applications using this key will lose access.')) {
        return;
    }
    
    const revokeBtn = document.getElementById('revoke-api-key');
    if (revokeBtn) {
        revokeBtn.disabled = true;
        revokeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Revoking...';
    }
    
    try {
        const response = await fetch('/api/v1/auth/api-key/revoke', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        
        const data = await response.json();
        
        if (response.ok && data.data) {
            currentApiKey = null;
            apiKeyVisible = false;
            
            // Clear the input
            const apiKeyInput = document.getElementById('api-key-value');
            if (apiKeyInput) {
                apiKeyInput.value = '';
                apiKeyInput.placeholder = 'No API key generated';
                apiKeyInput.classList.remove('masked');
            }
            updateVisibilityIcon();
            
            // Update button text
            const generateBtnText = document.getElementById('generate-api-key-text');
            if (generateBtnText) {
                generateBtnText.textContent = 'Generate API Key';
            }
            
            // Hide revoke button
            if (revokeBtn) {
                revokeBtn.style.display = 'none';
            }
            
            // Disable key_required toggle (backend sets it to false)
            const keyRequiredToggle = document.getElementById('api-key-required');
            if (keyRequiredToggle) {
                keyRequiredToggle.checked = false;
                initialKeyRequired = false;  // Update initial state
            }
            
            // Update warning (no key = no warning)
            updateApiKeyAuthWarning();
            
            TransferarrNotifications.success('API Key Revoked', 'The API key has been revoked.');
        } else {
            TransferarrNotifications.error('Revoke Failed', data.error?.message || 'Failed to revoke API key');
        }
    } catch (error) {
        console.error('Error revoking API key:', error);
        TransferarrNotifications.error('Revoke Failed', 'Failed to revoke API key');
    } finally {
        if (revokeBtn) {
            revokeBtn.disabled = false;
            revokeBtn.innerHTML = '<i class="fas fa-trash"></i> Revoke Key';
        }
    }
}

/**
 * Handle key_required toggle change.
 */
function onKeyRequiredChange() {
    const saveBtn = document.getElementById('save-api-key-settings');
    const keyRequiredToggle = document.getElementById('api-key-required');
    
    // Show save button if value changed from initial
    if (saveBtn && keyRequiredToggle) {
        const hasChanged = keyRequiredToggle.checked !== initialKeyRequired;
        saveBtn.style.display = hasChanged ? 'inline-flex' : 'none';
    }
}

/**
 * Save API key settings.
 */
async function saveApiKeySettings() {
    const saveBtn = document.getElementById('save-api-key-settings');
    const keyRequired = document.getElementById('api-key-required')?.checked;
    
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    }
    
    try {
        const response = await fetch('/api/v1/auth/api-key', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key_required: keyRequired }),
        });
        
        const data = await response.json();
        
        if (response.ok && data.data) {
            initialKeyRequired = keyRequired;
            TransferarrNotifications.success('Settings Saved', 'API key settings saved!');
            
            // Hide save button since values match
            if (saveBtn) {
                saveBtn.style.display = 'none';
            }
        } else {
            TransferarrNotifications.error('Save Failed', data.error?.message || 'Failed to save settings');
        }
    } catch (error) {
        console.error('Error saving API key settings:', error);
        TransferarrNotifications.error('Save Failed', 'Failed to save settings');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fas fa-save"></i> Save Settings';
        }
    }
}
