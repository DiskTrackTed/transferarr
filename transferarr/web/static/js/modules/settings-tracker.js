/**
 * Tracker settings module for the Settings page.
 * Handles loading/saving tracker settings with dynamic save button
 * that shows "Save and Apply" when restart-requiring fields change.
 */

let trackerLoaded = false;

// Original values loaded from the API, used to detect changes
let originalValues = {};

// Fields that require a tracker restart/stop/start to take effect
const RESTART_FIELDS = ['enabled', 'port'];

/**
 * Initialize the tracker settings tab.
 */
export function initTrackerSettings() {
    console.log('Tracker settings module initialized');

    // Bind save button
    const saveBtn = document.getElementById('save-tracker-settings');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveTrackerSettings);
    }

    // Bind change listeners for dynamic button text
    const fields = [
        { id: 'tracker-enabled', event: 'change' },
        { id: 'tracker-port', event: 'input' },
        { id: 'tracker-external-url', event: 'input' },
        { id: 'tracker-announce-interval', event: 'input' },
        { id: 'tracker-peer-expiry', event: 'input' }
    ];
    for (const field of fields) {
        const el = document.getElementById(field.id);
        if (el) {
            el.addEventListener(field.event, updateSaveButtonState);
        }
    }

    // Make the advanced toggle available globally for the onclick handler
    window.toggleTrackerAdvanced = toggleTrackerAdvanced;
}

/**
 * Load tracker settings from the API.
 */
export async function loadTrackerSettings() {
    if (trackerLoaded) return;

    try {
        const response = await fetch('/api/v1/tracker/settings');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (data.data) {
            populateTrackerSettings(data.data);
            trackerLoaded = true;
        } else {
            console.error('Failed to load tracker settings:', data.error?.message);
        }
    } catch (error) {
        console.error('Error loading tracker settings:', error);
    }
}

/**
 * Populate the form with loaded settings and store original values.
 */
function populateTrackerSettings(data) {
    const config = data.config || {};
    const status = data.status || {};

    // Populate form fields
    const enabledToggle = document.getElementById('tracker-enabled');
    if (enabledToggle) enabledToggle.checked = config.enabled;

    const portInput = document.getElementById('tracker-port');
    if (portInput) portInput.value = config.port || '';

    const externalUrlInput = document.getElementById('tracker-external-url');
    if (externalUrlInput) externalUrlInput.value = config.external_url || '';

    const announceIntervalInput = document.getElementById('tracker-announce-interval');
    if (announceIntervalInput) announceIntervalInput.value = config.announce_interval || '';

    const peerExpiryInput = document.getElementById('tracker-peer-expiry');
    if (peerExpiryInput) peerExpiryInput.value = config.peer_expiry || '';

    // Store original values for change detection
    originalValues = {
        enabled: config.enabled || false,
        port: String(config.port || ''),
        external_url: config.external_url || '',
        announce_interval: String(config.announce_interval || ''),
        peer_expiry: String(config.peer_expiry || '')
    };

    // Update status display
    updateStatusDisplay(status);

    // Reset button to default state
    updateSaveButtonState();
}

/**
 * Get current form values.
 */
function getCurrentValues() {
    return {
        enabled: document.getElementById('tracker-enabled')?.checked || false,
        port: document.getElementById('tracker-port')?.value || '',
        external_url: document.getElementById('tracker-external-url')?.value || '',
        announce_interval: document.getElementById('tracker-announce-interval')?.value || '',
        peer_expiry: document.getElementById('tracker-peer-expiry')?.value || ''
    };
}

/**
 * Check if any restart-requiring fields have changed.
 */
function needsApply() {
    const current = getCurrentValues();
    for (const field of RESTART_FIELDS) {
        if (field === 'enabled') {
            if (current.enabled !== originalValues.enabled) return true;
        } else {
            if (current[field] !== originalValues[field]) return true;
        }
    }
    return false;
}

/**
 * Update the save button text based on whether restart-requiring fields changed.
 */
function updateSaveButtonState() {
    const saveBtn = document.getElementById('save-tracker-settings');
    if (!saveBtn) return;

    if (needsApply()) {
        saveBtn.innerHTML = '<i class="fas fa-save"></i> Save and Apply';
    } else {
        saveBtn.innerHTML = '<i class="fas fa-save"></i> Save Settings';
    }
}

/**
 * Update the status indicator and details.
 */
function updateStatusDisplay(status) {
    const dot = document.getElementById('tracker-status-dot');
    const text = document.getElementById('tracker-status-text');
    const activeTransfers = document.getElementById('tracker-active-transfers');
    const runningPort = document.getElementById('tracker-running-port');

    if (status.running) {
        if (dot) dot.className = 'tracker-status-dot running';
        if (text) text.textContent = 'Running';
    } else if (status.enabled) {
        if (dot) dot.className = 'tracker-status-dot stopped';
        if (text) text.textContent = 'Stopped';
    } else {
        if (dot) dot.className = 'tracker-status-dot disabled';
        if (text) text.textContent = 'Disabled';
    }

    if (activeTransfers) activeTransfers.textContent = status.active_transfers || 0;
    if (runningPort) runningPort.textContent = status.running ? status.port : '—';
}

/**
 * Save tracker settings via API.
 * Sends apply=true when restart-requiring fields have changed.
 */
async function saveTrackerSettings() {
    const saveBtn = document.getElementById('save-tracker-settings');
    const applyNeeded = needsApply();
    saveBtn.innerHTML = applyNeeded
        ? '<i class="fas fa-spinner fa-spin"></i> Applying...'
        : '<i class="fas fa-spinner fa-spin"></i> Saving...';
    saveBtn.disabled = true;

    try {
        const payload = {
            enabled: document.getElementById('tracker-enabled')?.checked || false,
            port: parseInt(document.getElementById('tracker-port')?.value) || 6969,
            external_url: document.getElementById('tracker-external-url')?.value || null,
            announce_interval: parseInt(document.getElementById('tracker-announce-interval')?.value) || 60,
            peer_expiry: parseInt(document.getElementById('tracker-peer-expiry')?.value) || 120
        };

        if (applyNeeded) {
            payload.apply = true;
        }

        const response = await fetch('/api/v1/tracker/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok) {
            // Update status display if returned
            if (data.data?.status) {
                updateStatusDisplay(data.data.status);
            }

            // Update stored originals to match what was just saved
            originalValues = {
                enabled: payload.enabled,
                port: String(payload.port),
                external_url: payload.external_url || '',
                announce_interval: String(payload.announce_interval),
                peer_expiry: String(payload.peer_expiry)
            };

            const message = applyNeeded
                ? 'Settings saved and applied successfully.'
                : 'Settings saved successfully.';
            TransferarrNotifications.success('Tracker Settings', message);
        } else {
            const errorMsg = data.error?.message || 'Failed to save settings';
            TransferarrNotifications.error('Tracker Settings', errorMsg);
        }
    } catch (error) {
        console.error('Error saving tracker settings:', error);
        try {
            TransferarrNotifications.error('Tracker Settings', 'Failed to save settings: ' + error.message);
        } catch (e) { /* notification system unavailable */ }
    } finally {
        saveBtn.disabled = false;
        updateSaveButtonState();
    }
}

/**
 * Toggle the advanced options section.
 */
function toggleTrackerAdvanced() {
    const options = document.getElementById('trackerAdvancedOptions');
    const icon = document.getElementById('trackerAdvancedIcon');
    if (!options || !icon) return;

    if (options.style.display === 'none') {
        options.style.display = 'block';
        icon.style.transform = 'rotate(90deg)';
    } else {
        options.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
    }
}
