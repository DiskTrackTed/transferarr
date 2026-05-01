// ============================================================================
// State
// ============================================================================
/** @type {Object<string, Object>} Cached torrent data, keyed by client name */
let allTorrentsCache = {};
/** @type {Set<string>} Selected torrent hashes (lowercase) */
const selectedHashes = new Set();
/** @type {string|null} Client name whose torrents are currently selected */
let selectionSourceClient = null;
/** @type {Array<string>} Configured client names */
let clientNames = [];
/** @type {string|null} Currently active client tab */
let activeClientName = null;
/** @type {number|null} Poll timer ID */
let pollTimerId = null;
/** @type {AbortController|null} Abort controller for the active client fetch */
let activeFetchController = null;
/** @type {number} Poll interval for active-client refreshes */
const POLL_INTERVAL_MS = 10000;
/** @type {number} Default rows per page for the torrents table */
const DEFAULT_PAGE_SIZE = 50;
/** @type {number|null} Debounce timer for the search input */
let searchInputDebounceId = null;

const viewState = {
    filters: {
        state: '',
        search: '',
    },
    sort: {
        field: 'name',
        order: 'asc',
    },
    pagination: {
        page: 1,
        perPage: DEFAULT_PAGE_SIZE,
    },
};

// ============================================================================
// Bootstrap & Polling
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    initializeTableControls();

    // Transfer button
    document.getElementById('transfer-selected-btn')
        .addEventListener('click', openTransferModal);

    // Modal buttons
    document.getElementById('transferModalClose')
        .addEventListener('click', closeTransferModal);
    document.getElementById('transferModalCancel')
        .addEventListener('click', closeTransferModal);
    document.getElementById('confirmTransferBtn')
        .addEventListener('click', confirmTransfer);
    document.getElementById('destinationClient')
        .addEventListener('change', onDestinationChange);
    document.getElementById('includeCrossSeeds')
        .addEventListener('change', updateTransferSummary);
    document.getElementById('deleteCrossSeeds')
        .addEventListener('change', updateTransferSummary);

    // Close modal on backdrop click
    document.getElementById('transferModal')
        .addEventListener('click', function(e) {
            if (e.target === this) closeTransferModal();
        });

    void initializeTorrentsPage();
});

async function initializeTorrentsPage() {
    showLoadingIndicator();

    try {
        clientNames = await API.fetchDownloadClients();
        initializeClientTabs(clientNames);
        setTableControlsVisible(clientNames.length > 0);

        if (clientNames.length === 0) {
            renderNoClientsConfigured();
            return;
        }

        await switchToClient(clientNames[0]);
    } catch (error) {
        if (error.name === 'AbortError') return;
        renderNoClientsConfigured('Unable to load download clients');
    } finally {
        hideLoadingIndicator();
    }
}

function initializeTableControls() {
    const stateFilter = document.getElementById('torrent-filter-state');
    const searchInput = document.getElementById('torrent-filter-search');
    const pageSizeSelect = document.getElementById('torrent-page-size');

    if (!stateFilter || !searchInput || !pageSizeSelect) return;

    stateFilter.addEventListener('change', (event) => {
        viewState.filters.state = event.target.value;
        resetPagination();
        renderActiveClientTorrents();
    });

    searchInput.addEventListener('input', (event) => {
        const nextValue = event.target.value;
        if (searchInputDebounceId !== null) {
            window.clearTimeout(searchInputDebounceId);
        }

        searchInputDebounceId = window.setTimeout(() => {
            viewState.filters.search = nextValue;
            resetPagination();
            renderActiveClientTorrents();
        }, 150);
    });

    pageSizeSelect.addEventListener('change', (event) => {
        const nextValue = Number.parseInt(event.target.value, 10);
        viewState.pagination.perPage = Number.isFinite(nextValue) && nextValue > 0
            ? nextValue
            : DEFAULT_PAGE_SIZE;
        resetPagination();
        renderActiveClientTorrents();
    });

    updateTableControls();
}

function setTableControlsVisible(visible) {
    const controls = document.getElementById('torrent-table-controls');
    if (!controls) return;
    controls.classList.toggle('hidden', !visible);
}

function updateTableControls() {
    const searchInput = document.getElementById('torrent-filter-search');
    const pageSizeSelect = document.getElementById('torrent-page-size');

    if (searchInput) searchInput.value = viewState.filters.search;
    if (pageSizeSelect) pageSizeSelect.value = String(viewState.pagination.perPage);
}

function resetPagination() {
    viewState.pagination.page = 1;
}

function renderActiveClientTorrents() {
    if (!activeClientName) return;
    const clientTorrents = allTorrentsCache[activeClientName];
    if (!clientTorrents) return;
    renderClientTorrents(activeClientName, clientTorrents);
}

function setResultsSummary(message) {
    const summary = document.getElementById('torrent-results-summary');
    if (summary) summary.textContent = message;
}

function updateResultsSummary(start, end, filteredCount, rawCount) {
    if (rawCount === 0) {
        setResultsSummary('No torrents loaded');
        return;
    }

    if (filteredCount === 0) {
        setResultsSummary(`No torrents match current filters (${rawCount} total)`);
        return;
    }

    const countText = filteredCount === rawCount
        ? `${filteredCount}`
        : `${filteredCount} matching (${rawCount} total)`;

    setResultsSummary(`Showing ${start}-${end} of ${countText}`);
}

function showLoadingIndicator() {
    const el = document.getElementById('loading-indicator');
    if (el) el.classList.remove('hidden');
}

function hideLoadingIndicator() {
    const el = document.getElementById('loading-indicator');
    if (el) el.classList.add('hidden');
}

function stopPolling() {
    if (pollTimerId !== null) {
        clearTimeout(pollTimerId);
        pollTimerId = null;
    }
}

function scheduleNextPoll(clientName = activeClientName) {
    stopPolling();
    if (!clientName || document.hidden) return;

    pollTimerId = window.setTimeout(async () => {
        pollTimerId = null;

        if (activeClientName !== clientName || document.hidden) {
            return;
        }

        await refreshClientTorrents(clientName);

        if (activeClientName === clientName && !document.hidden) {
            scheduleNextPoll(clientName);
        }
    }, POLL_INTERVAL_MS);
}

function startPolling() {
    scheduleNextPoll(activeClientName);
}

function abortActiveFetch() {
    if (activeFetchController) {
        activeFetchController.abort();
        activeFetchController = null;
    }
}

async function switchToClient(clientName) {
    if (!clientName) return;

    stopPolling();
    abortActiveFetch();
    setActiveClientTab(clientName);
    await refreshClientTorrents(clientName);

    if (activeClientName === clientName) {
        startPolling();
    }
}

async function refreshClientTorrents(clientName = activeClientName) {
    if (!clientName) return;

    const controller = new AbortController();
    activeFetchController = controller;

    try {
        const data = await API.fetchClientTorrents(clientName, controller.signal);
        if (activeClientName !== clientName) return;

        allTorrentsCache[clientName] = data;
        renderClientTorrents(clientName, data);
    } catch (error) {
        if (error.name === 'AbortError') return;
        if (activeClientName !== clientName) return;

        // Keep the last successful payload and current selection so transient
        // refresh failures don't silently change a pending manual transfer.
        renderClientError(clientName, error.message || `Unable to load torrents for ${clientName}`);
    } finally {
        if (activeFetchController === controller) {
            activeFetchController = null;
        }
    }
}

// ============================================================================
// Selection Management
// ============================================================================
function toggleSelection(torrentHash, clientName) {
    const hashLower = torrentHash.toLowerCase();

    // If selecting from a different client, clear existing selection
    if (selectionSourceClient && selectionSourceClient !== clientName) {
        clearSelection();
    }
    selectionSourceClient = clientName;

    if (selectedHashes.has(hashLower)) {
        selectedHashes.delete(hashLower);
    } else {
        selectedHashes.add(hashLower);
    }

    if (selectedHashes.size === 0) {
        selectionSourceClient = null;
    }

    updateSelectionUI();
}

function clearSelection() {
    selectedHashes.clear();
    selectionSourceClient = null;
    updateSelectionUI();
}

function updateSelectionUI() {
    const count = selectedHashes.size;
    const btn = document.getElementById('transfer-selected-btn');
    const countSpan = document.getElementById('selected-count');

    countSpan.textContent = count;
    btn.disabled = count === 0;
    btn.style.visibility = count > 0 ? 'visible' : 'hidden';
    btn.style.opacity = count > 0 ? '1' : '0';

    // Update checkbox states
    document.querySelectorAll('.torrent-checkbox').forEach(cb => {
        const hash = cb.dataset.hash?.toLowerCase();
        cb.checked = hash ? selectedHashes.has(hash) : false;
    });

    // Update row highlight
    document.querySelectorAll('.torrent-table-row').forEach(row => {
        const id = row.dataset.id?.toLowerCase();
        row.classList.toggle('selected', id ? selectedHashes.has(id) : false);
    });
}

// ============================================================================
// Cross-seed Detection
// ============================================================================
/**
 * Build cross-seed groups from a client's torrent data.
 * Cross-seeds share the same name and total_size (may be in different
 * directories when the cross-seed tool creates symlinks).
 * @param {Object} clientTorrents - hash→info object for a single client
 * @returns {Object<string, string[]>} groupKey → [hashes] (only groups with 2+ members)
 */
function buildCrossSeedPathGroups(clientTorrents) {
    const groups = {};
    for (const [hash, info] of Object.entries(clientTorrents)) {
        const name = info.name;
        const totalSize = info.total_size;
        if (!name || totalSize == null) continue;
        const key = name + '|' + totalSize;
        if (!groups[key]) groups[key] = [];
        groups[key].push(hash);
    }
    const result = {};
    for (const [key, hashes] of Object.entries(groups)) {
        if (hashes.length > 1) result[key] = hashes;
    }
    return result;
}

/**
 * Build cross-seed groups for the current selection's source client.
 * @returns {Object<string, string[]>} save_path -> list of hashes (groups with 2+)
 */
function getCrossSeedGroups() {
    if (!selectionSourceClient || !allTorrentsCache[selectionSourceClient]) return {};
    return buildCrossSeedPathGroups(allTorrentsCache[selectionSourceClient]);
}

/**
 * Get cross-seed siblings that would be added for the current selection.
 * @returns {string[]} Additional hashes that would be included
 */
function getCrossSeedExpansion() {
    const groups = getCrossSeedGroups();
    const clientTorrents = allTorrentsCache[selectionSourceClient] || {};

    // Build lowercase-keyed lookup for O(1) access
    const lowerMap = {};
    for (const [h, info] of Object.entries(clientTorrents)) {
        lowerMap[h.toLowerCase()] = info;
    }

    const extra = new Set();
    for (const hash of selectedHashes) {
        const info = lowerMap[hash];
        if (!info) continue;
        const name = info.name;
        const totalSize = info.total_size;
        if (name && totalSize != null) {
            const key = name + '|' + totalSize;
            if (!groups[key]) continue;
            for (const sibling of groups[key]) {
                const sibLower = sibling.toLowerCase();
                if (!selectedHashes.has(sibLower)) {
                    const sibInfo = lowerMap[sibLower];
                    if (sibInfo && sibInfo.state?.toLowerCase() === 'seeding') {
                        extra.add(sibLower);
                    }
                }
            }
        }
    }
    return [...extra];
}

/**
 * Find the original (oldest) torrent in a cross-seed group by time_added.
 * @param {string[]} hashes - All hashes in the cross-seed group
 * @param {Object} lowerMap - lowercase hash → torrent info
 * @returns {string|null} The hash of the oldest torrent, or null
 */
function findOriginalHash(hashes, lowerMap) {
    let oldest = null;
    let oldestTime = Infinity;
    for (const h of hashes) {
        const info = lowerMap[h.toLowerCase()];
        if (!info) continue;
        const timeAdded = info.time_added;
        if (timeAdded != null && timeAdded < oldestTime) {
            oldestTime = timeAdded;
            oldest = h.toLowerCase();
        }
    }
    return oldest;
}

// ============================================================================
// Transfer Modal
// ============================================================================

/**
 * Open the transfer modal for a single torrent (from the inline button).
 * Clears any existing selection, selects just this torrent, then opens.
 */
function transferSingle(torrentHash, clientName) {
    clearSelection();
    selectionSourceClient = clientName;
    selectedHashes.add(torrentHash.toLowerCase());
    updateSelectionUI();
    openTransferModal();
}

function openTransferModal() {
    if (selectedHashes.size === 0) return;

    const modal = document.getElementById('transferModal');
    const error = document.getElementById('transfer-error');
    error.style.display = 'none';

    // Populate the torrent list preview
    updateTransferSummary();

    // Load destinations for the source client
    loadDestinations();

    // Show modal
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
}

function closeTransferModal() {
    const modal = document.getElementById('transferModal');
    modal.classList.remove('show');
    document.body.style.overflow = '';
}

async function loadDestinations() {
    const select = document.getElementById('destinationClient');
    const confirmBtn = document.getElementById('confirmTransferBtn');
    select.innerHTML = '<option value="">Loading...</option>';
    confirmBtn.disabled = true;

    try {
        const destinations = await API.fetchDestinations(selectionSourceClient);
        select.innerHTML = '<option value="">Select destination...</option>';
        for (const dest of destinations) {
            const opt = document.createElement('option');
            opt.value = dest.client;
            opt.textContent = `${dest.client} (${dest.transfer_type})`;
            opt.dataset.connection = dest.connection;
            opt.dataset.transferType = dest.transfer_type;
            select.appendChild(opt);
        }

        if (destinations.length === 0) {
            select.innerHTML = '<option value="">No destinations available</option>';
        }
    } catch (err) {
        console.error('Error loading destinations:', err);
        select.innerHTML = '<option value="">Error loading destinations</option>';
    }
}

function onDestinationChange() {
    const select = document.getElementById('destinationClient');
    const confirmBtn = document.getElementById('confirmTransferBtn');
    confirmBtn.disabled = !select.value;
}

function updateTransferSummary() {
    const includeCrossSeeds = document.getElementById('includeCrossSeeds').checked;
    const deleteCrossSeeds = document.getElementById('deleteCrossSeeds')?.checked ?? true;
    const clientTorrents = allTorrentsCache[selectionSourceClient] || {};

    // Build lowercase-keyed lookup for O(1) access
    const lowerMap = {};
    for (const [h, info] of Object.entries(clientTorrents)) {
        lowerMap[h.toLowerCase()] = info;
    }

    const directHashes = [...selectedHashes];
    // Always compute cross-seed siblings regardless of checkbox state
    const crossSeedHashes = getCrossSeedExpansion();

    document.getElementById('modal-selected-count').textContent = directHashes.length;

    // Cross-seed warning (shown when including cross-seeds and siblings exist)
    const csWarning = document.getElementById('cross-seed-warning');
    if (csWarning) {
        csWarning.style.display = (includeCrossSeeds && crossSeedHashes.length > 0) ? 'flex' : 'none';
    }

    // Determine cross-seed groups and find the original (oldest) in each
    const groups = getCrossSeedGroups();
    const allInvolved = [...directHashes, ...crossSeedHashes];
    const originalHashes = new Set();
    const hashToGroupKey = {};
    const processedGroupKeys = new Set();

    for (const hash of allInvolved) {
        const info = lowerMap[hash];
        if (!info) continue;
        const name = info.name;
        const totalSize = info.total_size;
        if (!name || totalSize == null) continue;
        const key = name + '|' + totalSize;
        if (!groups[key]) continue;
        hashToGroupKey[hash] = key;
        if (!processedGroupKeys.has(key)) {
            processedGroupKeys.add(key);
            const orig = findOriginalHash(groups[key], lowerMap);
            if (orig) originalHashes.add(orig);
        }
    }

    // Show/hide delete-cross-seeds option
    const deleteCsGroup = document.getElementById('deleteCrossSeeds')?.closest('.form-group');
    if (deleteCsGroup) {
        deleteCsGroup.style.display = processedGroupKeys.size > 0 ? 'block' : 'none';
    }

    // Determine action for non-selected siblings based on checkboxes
    let csAction = 'none';
    if (includeCrossSeeds && deleteCrossSeeds) csAction = 'transfer-delete';
    else if (includeCrossSeeds) csAction = 'transfer';
    else if (deleteCrossSeeds) csAction = 'delete';

    // Build top section and cross-seed section.
    // Original (oldest) of each group is always promoted to the top.
    // All other siblings go to the cross-seed section.
    // Standalone selected torrents (not in any group) go to the top.
    // Action badges are NOT shown on top-section items — the section
    // subtitle ("Transferred to destination and removed from source")
    // already communicates their fate.
    const topItems = [];
    const csItems = [];
    const placedHashes = new Set();

    // 1. Place group originals in the top section
    for (const hash of allInvolved) {
        if (placedHashes.has(hash) || !originalHashes.has(hash)) continue;
        const isSelected = selectedHashes.has(hash);
        topItems.push({
            hash,
            isOriginal: true,
            isSelected,
            action: null,
        });
        placedHashes.add(hash);
    }

    // 2. Standalone directly-selected hashes (not in any group)
    for (const hash of directHashes) {
        if (placedHashes.has(hash) || hashToGroupKey[hash]) continue;
        topItems.push({
            hash,
            isOriginal: false,
            isSelected: false,
            action: null,
        });
        placedHashes.add(hash);
    }

    // 3. Remaining hashes → cross-seed section
    //    (directly-selected non-originals + non-selected siblings)
    for (const hash of allInvolved) {
        if (placedHashes.has(hash)) continue;
        const isSelected = selectedHashes.has(hash);
        csItems.push({
            hash,
            isOriginal: false,
            isSelected,
            action: csAction,
        });
        placedHashes.add(hash);
    }

    // Render the list
    const listEl = document.getElementById('transfer-torrent-list');
    listEl.innerHTML = '';

    for (const item of topItems) {
        const info = lowerMap[item.hash];
        if (!info) continue;
        listEl.appendChild(createTransferListItem(
            info, false, item.isOriginal, item.action, item.isSelected,
        ));
    }

    if (csItems.length > 0) {
        const divider = document.createElement('div');
        divider.className = 'cross-seed-divider';
        divider.innerHTML = '<i class="fas fa-link"></i> Cross-seeds';
        listEl.appendChild(divider);

        for (const item of csItems) {
            const info = lowerMap[item.hash];
            if (!info) continue;
            listEl.appendChild(createTransferListItem(
                info, true, item.isOriginal, item.action, item.isSelected,
            ));
        }
    }
}

/**
 * Extract a readable tracker hostname from Deluge tracker data.
 * Deluge returns trackers as [{url, tier}, ...] or sometimes a flat list.
 * @param {Object} torrentInfo
 * @returns {string} Tracker hostname or empty string
 */
function getTrackerName(torrentInfo) {
    const trackers = torrentInfo.trackers;
    if (!trackers || !Array.isArray(trackers) || trackers.length === 0) return '';
    try {
        const entry = trackers[0];
        const url = (typeof entry === 'string') ? entry : (entry.url || '');
        if (!url) return '';
        const hostname = new URL(url).hostname;
        return hostname || '';
    } catch {
        return '';
    }
}

function createTransferListItem(torrentInfo, isCrossSeed, isOriginal, action, isSelected) {
    const item = document.createElement('div');
    let className = 'transfer-list-item';
    if (isCrossSeed) {
        className += ' cross-seed-item';
        // Dim only non-selected siblings with no meaningful action
        if (!isSelected && (!action || action === 'none')) className += ' cross-seed-inactive';
    }
    item.className = className;

    // Left section: name (truncates) + tracker label
    const nameCol = document.createElement('div');
    nameCol.className = 'transfer-item-name';

    const nameText = document.createElement('span');
    nameText.className = 'transfer-item-name-text';
    nameText.textContent = torrentInfo.name || 'Unknown';
    nameText.title = torrentInfo.name || 'Unknown';
    nameCol.appendChild(nameText);

    // Tracker label
    const tracker = getTrackerName(torrentInfo);
    if (tracker) {
        const trackerEl = document.createElement('span');
        trackerEl.className = 'transfer-item-tracker';
        trackerEl.textContent = tracker;
        trackerEl.title = tracker;
        nameCol.appendChild(trackerEl);
    }

    // Right section: badges + size (never truncated)
    const badges = document.createElement('span');
    badges.className = 'transfer-item-badges';

    // Show "Original" badge on the oldest torrent in a cross-seed group
    if (isOriginal) {
        const badge = document.createElement('span');
        badge.className = 'original-badge';
        badge.title = 'Original torrent (oldest by time added)';
        badge.textContent = 'Original';
        badges.appendChild(badge);
    }

    // Show "Selected" badge on the torrent the user explicitly picked
    if (isSelected) {
        const badge = document.createElement('span');
        badge.className = 'selected-badge';
        badge.title = 'Directly selected for transfer';
        badge.textContent = 'Selected';
        badges.appendChild(badge);
    }

    // Show action badges for non-selected siblings
    if (action) {
        if (action === 'transfer' || action === 'transfer-delete') {
            const badge = document.createElement('span');
            badge.className = 'action-badge action-badge-transfer';
            badge.textContent = 'Transfer';
            badge.title = 'Will be transferred to destination';
            badges.appendChild(badge);
        }
        if (action === 'delete' || action === 'transfer-delete') {
            const badge = document.createElement('span');
            badge.className = 'action-badge action-badge-delete';
            badge.textContent = 'Delete';
            badge.title = 'Will be deleted from source';
            badges.appendChild(badge);
        }
        if (action === 'none') {
            const badge = document.createElement('span');
            badge.className = 'action-badge action-badge-none';
            badge.textContent = 'No action';
            badge.title = 'This cross-seed will remain unchanged';
            badges.appendChild(badge);
        }
    }

    const size = document.createElement('span');
    size.className = 'transfer-item-size';
    const totalSize = torrentInfo.total_size || 0;
    size.textContent = formatBytes(totalSize);

    item.appendChild(nameCol);
    item.appendChild(badges);
    item.appendChild(size);
    return item;
}

async function confirmTransfer() {
    const destSelect = document.getElementById('destinationClient');
    const includeCrossSeeds = document.getElementById('includeCrossSeeds').checked;
    const confirmBtn = document.getElementById('confirmTransferBtn');
    const error = document.getElementById('transfer-error');

    if (!destSelect.value) return;

    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Transferring...';
    error.style.display = 'none';

    try {
        const deleteCrossSeeds = document.getElementById('deleteCrossSeeds')?.checked ?? true;
        const result = await API.initiateManualTransfer({
            hashes: [...selectedHashes],
            source_client: selectionSourceClient,
            destination_client: destSelect.value,
            include_cross_seeds: includeCrossSeeds,
            delete_source_cross_seeds: deleteCrossSeeds,
        });

        closeTransferModal();
        clearSelection();

        // Show success notification
        if (window.TransferarrNotifications) {
            const data = result.data || result;
            window.TransferarrNotifications.success(
                'Transfer Initiated',
                `${data.total_initiated} torrent(s) queued for transfer`
            );
        }
    } catch (err) {
        error.textContent = err.message;
        error.style.display = 'block';
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fas fa-exchange-alt"></i> Start Transfer';
    }
}

// ============================================================================
// Torrent Table Rendering
// ============================================================================
function getSafeClientName(clientName) {
    return clientName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '');
}

function initializeClientTabs(names) {
    const clientTabsContainer = document.getElementById('client-tabs');
    const clientTabContentsContainer = document.getElementById('client-tab-contents');

    clientTabsContainer.innerHTML = '';
    clientTabContentsContainer.innerHTML = '';

    if (names.length === 0) {
        clientTabsContainer.style.display = 'none';
        clientTabContentsContainer.style.display = 'block';
        return;
    }

    clientTabsContainer.style.display = 'flex';
    clientTabContentsContainer.style.display = 'block';

    names.forEach(clientName => {
        const tab = document.createElement('div');
        tab.className = 'client-tab';
        tab.textContent = clientName;
        tab.dataset.client = clientName;
        tab.addEventListener('click', function() {
            if (clientName === activeClientName) return;
            resetPagination();
            void switchToClient(clientName);
        });
        clientTabsContainer.appendChild(tab);

        const tabContent = document.createElement('div');
        tabContent.className = 'client-tab-content';
        tabContent.id = `client-${getSafeClientName(clientName)}`;
        clientTabContentsContainer.appendChild(tabContent);
    });
}

function setActiveClientTab(clientName) {
    activeClientName = clientName;

    document.querySelectorAll('.client-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.client === clientName);
    });

    document.querySelectorAll('.client-tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `client-${getSafeClientName(clientName)}`);
    });
}

function getClientTabContent(clientName) {
    return document.getElementById(`client-${getSafeClientName(clientName)}`);
}

function ensureClientTorrentContainer(tabContent) {
    let container = tabContent.querySelector('.client-torrent-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'client-torrent-container';
        tabContent.appendChild(container);
    }
    return container;
}

function renderNoClientsConfigured(message = 'No download clients configured') {
    const clientTabsContainer = document.getElementById('client-tabs');
    const clientTabContentsContainer = document.getElementById('client-tab-contents');

    setTableControlsVisible(false);
    clientTabsContainer.innerHTML = '';
    clientTabsContainer.style.display = 'none';
    clientTabContentsContainer.style.display = 'block';
    clientTabContentsContainer.innerHTML = '';

    const status = document.createElement('div');
    status.className = 'client-status-message no-clients-message';
    status.textContent = message;
    clientTabContentsContainer.appendChild(status);
    setResultsSummary(message);
}

function buildStatusMessage(message, kind = 'empty') {
    const status = document.createElement('div');
    const className = {
        error: 'client-error-message',
        filtered: 'filtered-empty-message',
        empty: 'empty-message',
    }[kind] || 'empty-message';
    status.className = `client-status-message ${className}`;
    status.textContent = message;
    return status;
}

function appendStatusMessage(container, message, kind = 'empty') {
    container.appendChild(buildStatusMessage(message, kind));
}

function renderClientStatusMessage(clientName, message, kind = 'empty') {
    const tabContent = getClientTabContent(clientName);
    if (!tabContent) return;

    const container = ensureClientTorrentContainer(tabContent);
    container.innerHTML = '';
    appendStatusMessage(container, message, kind);
}

function renderClientError(clientName, message) {
    const cachedTorrents = allTorrentsCache[clientName];
    if (cachedTorrents && Object.keys(cachedTorrents).length > 0) {
        renderClientTorrents(clientName, cachedTorrents, {
            message,
            kind: 'error',
        });
        return;
    }

    renderClientStatusMessage(clientName, message, 'error');
    setResultsSummary(message);
}

function pruneSelectedHashes(clientName, clientTorrents) {
    if (selectionSourceClient !== clientName || selectedHashes.size === 0) return;

    const lowerIds = new Set(Object.keys(clientTorrents).map(hash => hash.toLowerCase()));
    let pruned = false;

    for (const hash of [...selectedHashes]) {
        if (!lowerIds.has(hash)) {
            selectedHashes.delete(hash);
            pruned = true;
        }
    }

    if (pruned) {
        if (selectedHashes.size === 0) selectionSourceClient = null;
        updateSelectionUI();
    }
}

function updateStateFilterOptions(clientTorrents) {
    const stateFilter = document.getElementById('torrent-filter-state');
    if (!stateFilter) return;

    const states = Array.from(new Set(
        Object.values(clientTorrents || {})
            .map((torrent) => torrent.state)
            .filter(Boolean)
    )).sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));

    if (viewState.filters.state) {
        const selectedExists = states.some(
            (state) => state.toLowerCase() === viewState.filters.state
        );
        if (!selectedExists) {
            states.unshift(viewState.filters.state);
        }
    }

    stateFilter.innerHTML = '<option value="">All states</option>';
    states.forEach((state) => {
        const option = document.createElement('option');
        option.value = state.toLowerCase();
        option.textContent = state;
        stateFilter.appendChild(option);
    });
    stateFilter.value = viewState.filters.state;
}

function normalizeClientTorrentRows(clientTorrents) {
    const groups = buildCrossSeedPathGroups(clientTorrents || {});
    const crossSeedHashes = new Set();
    Object.values(groups).forEach((hashes) => {
        hashes.forEach((hash) => crossSeedHashes.add(hash.toLowerCase()));
    });

    return Object.entries(clientTorrents || {}).map(([torrentId, torrentData]) => {
        const stateText = torrentData.state || 'Unknown';
        const stateLower = stateText.toLowerCase();
        const isSeeding = stateLower === 'seeding';
        const rateValue = getRateValue(torrentData, isSeeding);
        const seedsValue = toNumberOrNull(torrentData.num_seeds);
        const addedValue = toNumberOrNull(torrentData.time_added);
        const tracker = getTrackerName(torrentData);

        return {
            id: torrentId,
            info: torrentData,
            name: torrentData.name || 'Unknown',
            stateText,
            progressValue: toNumberOrZero(torrentData.progress),
            sizeValue: toNumberOrZero(torrentData.total_size),
            seedsValue,
            rateValue,
            rateDisplay: rateValue !== null && rateValue > 0 ? `${formatBytes(rateValue)}/s` : '',
            tracker,
            addedValue,
            addedDisplay: formatAddedAt(addedValue),
            isCrossSeed: crossSeedHashes.has(torrentId.toLowerCase()),
            isSeeding,
        };
    });
}

function applyTorrentFilters(rows) {
    const stateFilter = viewState.filters.state;
    const searchFilter = viewState.filters.search.trim().toLowerCase();

    return rows.filter((row) => {
        if (stateFilter && row.stateText.toLowerCase() !== stateFilter) {
            return false;
        }

        if (searchFilter && !row.name.toLowerCase().includes(searchFilter)) {
            return false;
        }

        return true;
    });
}

function sortTorrentRows(rows) {
    const { field, order } = viewState.sort;
    return [...rows].sort((left, right) => {
        const comparison = compareSortValues(
            getRowSortValue(left, field),
            getRowSortValue(right, field),
            order,
        );
        if (comparison !== 0) return comparison;
        return left.name.localeCompare(right.name, undefined, {
            sensitivity: 'base',
            numeric: true,
        });
    });
}

function paginateTorrentRows(rows) {
    const perPage = viewState.pagination.perPage;
    const totalPages = Math.max(1, Math.ceil(rows.length / perPage));
    const currentPage = Math.min(viewState.pagination.page, totalPages);
    viewState.pagination.page = currentPage;

    const startIndex = (currentPage - 1) * perPage;
    const endIndex = Math.min(startIndex + perPage, rows.length);

    return {
        pageRows: rows.slice(startIndex, endIndex),
        currentPage,
        totalPages,
        startIndex,
        endIndex,
    };
}

function renderClientTorrents(clientName, clientTorrents, statusMessage = null) {
    const tabContent = getClientTabContent(clientName);
    if (!tabContent) return;

    const container = ensureClientTorrentContainer(tabContent);
    container.innerHTML = '';

    updateStateFilterOptions(clientTorrents);
    updateTableControls();
    pruneSelectedHashes(clientName, clientTorrents);

    const rawRows = normalizeClientTorrentRows(clientTorrents || {});
    if (rawRows.length === 0) {
        renderClientStatusMessage(clientName, `No torrents for ${clientName}`, 'empty');
        updateResultsSummary(0, 0, 0, 0);
        return;
    }

    const filteredRows = applyTorrentFilters(rawRows);
    if (filteredRows.length === 0) {
        if (statusMessage) {
            appendStatusMessage(container, statusMessage.message, statusMessage.kind);
        }
        appendStatusMessage(container, 'No torrents match current filters', 'filtered');
        updateResultsSummary(0, 0, 0, rawRows.length);
        container.appendChild(createPaginationControls(1, 1));
        return;
    }

    const sortedRows = sortTorrentRows(filteredRows);
    const pagination = paginateTorrentRows(sortedRows);

    updateResultsSummary(
        pagination.startIndex + 1,
        pagination.endIndex,
        filteredRows.length,
        rawRows.length,
    );

    if (statusMessage) {
        appendStatusMessage(container, statusMessage.message, statusMessage.kind);
    }
    container.appendChild(createClientTorrentTable(clientName, pagination.pageRows));
    container.appendChild(createPaginationControls(pagination.currentPage, pagination.totalPages));
    updateSelectionUI();
}

function clearClientViews() {
    stopPolling();
    abortActiveFetch();
    allTorrentsCache = {};
    clientNames = [];
    activeClientName = null;
    clearSelection();
}

window.addEventListener('beforeunload', function() {
    stopPolling();
    abortActiveFetch();
    clearClientViews();
});

window.addEventListener('pagehide', function() {
    stopPolling();
    abortActiveFetch();
    clearClientViews();
});

window.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        stopPolling();
        return;
    }
    if (activeClientName) {
        startPolling();
    }
});

function createInlineTransferButton(torrentId, clientName) {
    const btn = document.createElement('button');
    btn.className = 'torrent-transfer-btn';
    btn.title = 'Transfer this torrent';
    btn.innerHTML = '<i class="fas fa-exchange-alt"></i>';
    btn.addEventListener('click', (event) => {
        event.stopPropagation();
        transferSingle(torrentId, clientName);
    });
    return btn;
}

function createClientTorrentTable(clientName, rows) {
    const wrapper = document.createElement('div');
    wrapper.className = 'client-torrent-table-wrapper';

    const table = document.createElement('table');
    table.className = 'client-torrent-table';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    headerRow.appendChild(createPlainHeader('Select', 'col-select'));
    headerRow.appendChild(createSortableHeader('Name', 'name'));
    headerRow.appendChild(createSortableHeader('State', 'state'));
    headerRow.appendChild(createSortableHeader('Progress', 'progress'));
    headerRow.appendChild(createSortableHeader('Size', 'size'));
    headerRow.appendChild(createSortableHeader('Seeds', 'seeds'));
    headerRow.appendChild(createSortableHeader('Rate', 'rate'));
    headerRow.appendChild(createSortableHeader('Tracker', 'tracker'));
    headerRow.appendChild(createSortableHeader('Added', 'added'));
    headerRow.appendChild(createPlainHeader('Actions', 'col-actions'));
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    rows.forEach((row) => {
        tbody.appendChild(createClientTorrentRow(clientName, row));
    });
    table.appendChild(tbody);

    wrapper.appendChild(table);
    return wrapper;
}

function createPlainHeader(label, className = '') {
    const th = document.createElement('th');
    if (className) th.className = className;
    th.textContent = label;
    return th;
}

function createSortableHeader(label, field) {
    const th = document.createElement('th');
    th.className = 'sortable';
    th.dataset.sort = field;

    if (viewState.sort.field === field) {
        th.classList.add(viewState.sort.order === 'asc' ? 'sort-asc' : 'sort-desc');
    }

    const labelSpan = document.createElement('span');
    labelSpan.className = 'sortable-label';
    labelSpan.textContent = label;

    const indicator = document.createElement('span');
    indicator.className = 'sort-indicator';
    indicator.textContent = viewState.sort.field === field
        ? (viewState.sort.order === 'asc' ? '↑' : '↓')
        : '↕';

    th.appendChild(labelSpan);
    th.appendChild(indicator);
    th.addEventListener('click', () => {
        if (viewState.sort.field === field) {
            viewState.sort.order = viewState.sort.order === 'asc' ? 'desc' : 'asc';
        } else {
            viewState.sort.field = field;
            viewState.sort.order = 'asc';
        }
        renderActiveClientTorrents();
    });
    return th;
}

function createClientTorrentRow(clientName, row) {
    const tr = document.createElement('tr');
    tr.className = 'torrent-table-row';
    tr.dataset.id = row.id;
    tr.classList.toggle('selected', selectedHashes.has(row.id.toLowerCase()));

    tr.appendChild(createSelectionCell(row, clientName));
    tr.appendChild(createNameCell(row));
    tr.appendChild(createStateCell(row));
    tr.appendChild(createProgressCell(row));
    tr.appendChild(createTextCell(formatBytes(row.sizeValue), 'align-right'));
    tr.appendChild(createTextCell(row.seedsValue === null ? '--' : String(row.seedsValue), 'align-right'));
    tr.appendChild(createTextCell(row.rateDisplay || '--', 'align-right'));
    tr.appendChild(createTextCell(row.tracker || '--', 'muted-cell'));
    tr.appendChild(createTextCell(row.addedDisplay || '--', 'muted-cell'));
    tr.appendChild(createActionsCell(row, clientName));

    return tr;
}

function createSelectionCell(row, clientName) {
    const td = document.createElement('td');
    td.className = 'col-select';

    const cbWrapper = document.createElement('div');
    cbWrapper.className = 'torrent-checkbox-wrapper';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'torrent-checkbox';
    cb.dataset.hash = row.id;
    cb.checked = selectedHashes.has(row.id.toLowerCase());
    cb.disabled = !row.isSeeding;
    cb.title = row.isSeeding ? 'Select for transfer' : 'Only seeding torrents can be transferred';
    cb.addEventListener('change', () => toggleSelection(row.id, clientName));
    cbWrapper.appendChild(cb);

    td.appendChild(cbWrapper);
    return td;
}

function createNameCell(row) {
    const td = document.createElement('td');
    td.className = 'torrent-name-cell';

    const content = document.createElement('div');
    content.className = 'torrent-name-content';

    const nameText = document.createElement('span');
    nameText.className = 'torrent-name-text';
    nameText.textContent = row.name;
    nameText.title = row.name;
    content.appendChild(nameText);

    if (row.isCrossSeed) {
        const badge = document.createElement('span');
        badge.className = 'cross-seed-badge';
        badge.title = 'Cross-seed — shares data with another torrent';
        badge.innerHTML = '<i class="fas fa-link"></i>';
        content.appendChild(badge);
    }

    td.appendChild(content);

    return td;
}

function createStateCell(row) {
    const td = document.createElement('td');
    td.className = 'torrent-state-cell';

    const indicator = document.createElement('span');
    indicator.className = `state-indicator ${getStateIndicatorClass(row.stateText.toUpperCase())}`;
    td.appendChild(indicator);
    td.appendChild(document.createTextNode(` ${row.stateText}`));
    return td;
}

function createProgressCell(row) {
    const td = document.createElement('td');
    td.className = 'torrent-progress-cell';

    const progressContent = document.createElement('div');
    progressContent.className = 'table-progress-content';

    const progressBar = document.createElement('div');
    progressBar.className = 'table-progress-bar';
    const progressFill = document.createElement('span');
    progressFill.className = 'table-progress-fill';
    progressFill.style.width = `${row.progressValue}%`;
    progressBar.appendChild(progressFill);

    const progressText = document.createElement('span');
    progressText.className = 'table-progress-text';
    progressText.textContent = `${Math.round(row.progressValue)}%`;

    progressContent.appendChild(progressBar);
    progressContent.appendChild(progressText);
    td.appendChild(progressContent);
    return td;
}

function createActionsCell(row, clientName) {
    const td = document.createElement('td');
    td.className = 'col-actions';

    const actionWrapper = document.createElement('div');
    actionWrapper.className = 'torrent-action-wrapper';
    if (row.isSeeding) {
        actionWrapper.appendChild(createInlineTransferButton(row.id, clientName));
    }
    td.appendChild(actionWrapper);
    return td;
}

function createTextCell(text, className = '') {
    const td = document.createElement('td');
    if (className) td.className = className;
    td.textContent = text;
    return td;
}

function createPaginationControls(currentPage, totalPages) {
    const pagination = document.createElement('div');
    pagination.className = 'torrent-pagination';

    const prevBtn = document.createElement('button');
    prevBtn.className = 'pagination-btn';
    prevBtn.textContent = 'Previous';
    prevBtn.disabled = currentPage <= 1;
    prevBtn.addEventListener('click', () => {
        if (viewState.pagination.page <= 1) return;
        viewState.pagination.page -= 1;
        renderActiveClientTorrents();
    });

    const nextBtn = document.createElement('button');
    nextBtn.className = 'pagination-btn';
    nextBtn.textContent = 'Next';
    nextBtn.disabled = currentPage >= totalPages;
    nextBtn.addEventListener('click', () => {
        if (viewState.pagination.page >= totalPages) return;
        viewState.pagination.page += 1;
        renderActiveClientTorrents();
    });

    const status = document.createElement('span');
    status.className = 'pagination-status';
    status.textContent = `Page ${currentPage} of ${totalPages}`;

    pagination.appendChild(prevBtn);
    pagination.appendChild(status);
    pagination.appendChild(nextBtn);
    return pagination;
}

// ============================================================================
// Utilities
// ============================================================================
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

function formatAddedAt(timestamp) {
    if (timestamp === null) return '';
    const date = new Date(timestamp * 1000);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString([], {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

function getRateValue(torrentData, isSeeding) {
    const downloadRate = toNumberOrNull(torrentData.download_payload_rate);
    const uploadRate = toNumberOrNull(torrentData.upload_payload_rate);
    const rate = isSeeding ? uploadRate : downloadRate;
    return rate !== null && rate > 0 ? rate : null;
}

function toNumberOrNull(value) {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function toNumberOrZero(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function getRowSortValue(row, field) {
    switch (field) {
    case 'name':
        return row.name;
    case 'state':
        return row.stateText;
    case 'progress':
        return row.progressValue;
    case 'size':
        return row.sizeValue;
    case 'seeds':
        return row.seedsValue;
    case 'rate':
        return row.rateValue;
    case 'tracker':
        return row.tracker;
    case 'added':
        return row.addedValue;
    default:
        return row.name;
    }
}

function compareSortValues(left, right, order) {
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;

    let result;
    if (typeof left === 'string' || typeof right === 'string') {
        result = String(left).localeCompare(String(right), undefined, {
            sensitivity: 'base',
            numeric: true,
        });
    } else {
        result = left - right;
    }

    return order === 'asc' ? result : -result;
}
