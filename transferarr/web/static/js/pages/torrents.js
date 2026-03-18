// ============================================================================
// State
// ============================================================================
/** @type {Object<string, Object>} Cached all-torrents data, keyed by client name */
let allTorrentsCache = {};
/** @type {Set<string>} Selected torrent hashes (lowercase) */
const selectedHashes = new Set();
/** @type {string|null} Client name whose torrents are currently selected */
let selectionSourceClient = null;

// ============================================================================
// Bootstrap & Polling
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    showLoadingIndicator();
    fetchAllTorrents();
    setInterval(fetchAllTorrents, 3000);

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
});

function showLoadingIndicator() {
    const el = document.getElementById('loading-indicator');
    if (el) el.classList.remove('hidden');
}

function hideLoadingIndicator() {
    const el = document.getElementById('loading-indicator');
    if (el) el.classList.add('hidden');
}

async function fetchAllTorrents() {
    try {
        const data = await API.fetchAllTorrents();
        allTorrentsCache = data;
        updateClientTabsWithAllTorrents(data);
        hideLoadingIndicator();
    } catch (error) {
        console.error('Error fetching all torrents:', error);
        hideLoadingIndicator();
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

    // Update card highlight
    document.querySelectorAll('.simple-torrent-card').forEach(card => {
        const id = card.dataset.id?.toLowerCase();
        card.classList.toggle('selected', id ? selectedHashes.has(id) : false);
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
// Torrent Card Rendering (with checkboxes & cross-seed indicators)
// ============================================================================
function updateClientTabsWithAllTorrents(allTorrentsData) {
    const clientNames = Object.keys(allTorrentsData);
    if (clientNames.length === 0) return;

    const clientTabsContainer = document.getElementById('client-tabs');
    const clientTabContentsContainer = document.getElementById('client-tab-contents');

    clientTabsContainer.style.display = 'flex';
    clientTabContentsContainer.style.display = 'block';

    // Remember active tab
    let activeTabName = '';
    const currentActive = document.querySelector('.client-tab.active');
    if (currentActive) activeTabName = currentActive.dataset.client;

    // Rebuild tabs if count changed
    if (clientTabsContainer.children.length !== clientNames.length) {
        clientTabsContainer.innerHTML = '';
        clientTabContentsContainer.innerHTML = '';

        clientNames.forEach((clientName, index) => {
            const tab = document.createElement('div');
            tab.className = 'client-tab';
            if ((activeTabName && clientName === activeTabName) ||
                (!activeTabName && index === 0)) {
                tab.classList.add('active');
            }
            tab.textContent = clientName;
            tab.dataset.client = clientName;
            clientTabsContainer.appendChild(tab);

            const tabContent = document.createElement('div');
            tabContent.className = 'client-tab-content';
            if ((activeTabName && clientName === activeTabName) ||
                (!activeTabName && index === 0)) {
                tabContent.classList.add('active');
            }
            tabContent.id = `client-${clientName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '')}`;
            clientTabContentsContainer.appendChild(tabContent);
        });

        // Tab click handler
        document.querySelectorAll('.client-tab').forEach(tab => {
            tab.addEventListener('click', function() {
                document.querySelectorAll('.client-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.client-tab-content').forEach(c => c.classList.remove('active'));
                this.classList.add('active');
                const cn = this.dataset.client;
                const safeName = cn.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '');
                const el = document.getElementById(`client-${safeName}`);
                if (el) el.classList.add('active');
            });
        });
    }

    // Build cross-seed lookup for indicator rendering
    const crossSeedGroups = {};
    for (const clientName of clientNames) {
        const groups = buildCrossSeedPathGroups(allTorrentsData[clientName] || {});
        crossSeedGroups[clientName] = {};
        for (const hashes of Object.values(groups)) {
            for (const h of hashes) {
                crossSeedGroups[clientName][h.toLowerCase()] = true;
            }
        }
    }

    // Update each client tab
    clientNames.forEach(clientName => {
        const clientTorrents = allTorrentsData[clientName] || {};
        const safeName = clientName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '');
        const tabContent = document.getElementById(`client-${safeName}`);
        if (!tabContent) return;

        // Remove empty message
        const existingMsg = tabContent.querySelector('.empty-message');
        if (existingMsg) tabContent.removeChild(existingMsg);

        let container = tabContent.querySelector('.client-torrent-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'client-torrent-container';
            tabContent.appendChild(container);
        }

        const existingCards = {};
        Array.from(container.children).forEach(card => {
            if (card.dataset.id) existingCards[card.dataset.id] = card;
        });

        const torrentIds = Object.keys(clientTorrents);

        if (torrentIds.length === 0) {
            container.innerHTML = '';
            const emptyMsg = document.createElement('div');
            emptyMsg.className = 'empty-message';
            emptyMsg.textContent = `No torrents for ${clientName}`;
            emptyMsg.style.padding = '20px';
            emptyMsg.style.textAlign = 'center';
            emptyMsg.style.color = '#666';
            tabContent.appendChild(emptyMsg);
            return;
        }

        torrentIds.forEach(torrentId => {
            const torrentData = clientTorrents[torrentId];
            const isCrossSeed = !!crossSeedGroups[clientName]?.[torrentId.toLowerCase()];
            const isSeeding = (torrentData.state || '').toLowerCase() === 'seeding';

            if (existingCards[torrentId]) {
                updateClientTorrentCard(existingCards[torrentId], torrentData, isCrossSeed, isSeeding, torrentId, clientName);
                delete existingCards[torrentId];
            } else {
                container.appendChild(createClientTorrentCard(torrentId, torrentData, isCrossSeed, isSeeding, clientName));
            }
        });

        // Remove stale cards
        Object.values(existingCards).forEach(card => container.removeChild(card));
    });

    // Prune selected hashes that no longer exist on the source client
    if (selectionSourceClient && selectedHashes.size > 0) {
        const clientTorrents = allTorrentsData[selectionSourceClient] || {};
        const lowerIds = new Set(Object.keys(clientTorrents).map(h => h.toLowerCase()));
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

    // Ensure active tab
    if (!document.querySelector('.client-tab.active') && clientNames.length > 0) {
        const firstTab = document.querySelector('.client-tab');
        if (firstTab) {
            firstTab.classList.add('active');
            const cn = firstTab.dataset.client;
            const safeName = cn.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '');
            const el = document.getElementById(`client-${safeName}`);
            if (el) el.classList.add('active');
        }
    }
}

/**
 * Create the inline transfer button for a seeding torrent card.
 * @param {string} torrentId - Torrent hash
 * @param {string} clientName - Client name for the transfer source
 * @returns {HTMLButtonElement}
 */
function createInlineTransferButton(torrentId, clientName) {
    const btn = document.createElement('button');
    btn.className = 'torrent-transfer-btn';
    btn.title = 'Transfer this torrent';
    btn.innerHTML = '<i class="fas fa-exchange-alt"></i>';
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        transferSingle(torrentId, clientName);
    });
    return btn;
}

function createClientTorrentCard(torrentId, torrentData, isCrossSeed, isSeeding, clientName) {
    const card = document.createElement('div');
    card.className = 'simple-torrent-card';
    card.dataset.id = torrentId;

    // Checkbox
    const cbWrapper = document.createElement('div');
    cbWrapper.className = 'torrent-checkbox-wrapper';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'torrent-checkbox';
    cb.dataset.hash = torrentId;
    cb.checked = selectedHashes.has(torrentId.toLowerCase());
    cb.disabled = !isSeeding;
    cb.title = isSeeding ? 'Select for transfer' : 'Only seeding torrents can be transferred';
    cb.addEventListener('change', () => toggleSelection(torrentId, clientName));
    cbWrapper.appendChild(cb);
    card.appendChild(cbWrapper);

    // Name + cross-seed indicator
    const nameDiv = document.createElement('div');
    nameDiv.className = 'simple-torrent-name';
    nameDiv.textContent = torrentData.name || 'Unknown';
    if (isCrossSeed) {
        const badge = document.createElement('span');
        badge.className = 'cross-seed-badge';
        badge.title = 'Cross-seed — shares data with another torrent';
        badge.innerHTML = '<i class="fas fa-link"></i>';
        nameDiv.appendChild(badge);
    }
    card.appendChild(nameDiv);

    // State
    const stateDiv = document.createElement('div');
    stateDiv.className = 'simple-torrent-state';
    const stateText = torrentData.state || 'Unknown';
    const stateClass = getStateIndicatorClass(stateText.toUpperCase());
    const stateIndicator = document.createElement('span');
    stateIndicator.className = `state-indicator ${stateClass}`;
    stateDiv.appendChild(stateIndicator);
    stateDiv.appendChild(document.createTextNode(' ' + stateText));
    card.appendChild(stateDiv);

    // Progress
    const progressDiv = document.createElement('div');
    progressDiv.className = 'simple-torrent-progress';
    const progressBar = document.createElement('div');
    progressBar.className = 'simple-progress-bar';
    const progressFill = document.createElement('span');
    progressFill.className = 'simple-progress-fill';
    const progressValue = torrentData.progress || 0;
    progressFill.style.width = `${progressValue}%`;
    const progressText = document.createElement('div');
    progressText.className = 'simple-progress-text';
    progressText.textContent = `${Math.round(progressValue)}%`;
    progressBar.appendChild(progressFill);
    progressDiv.appendChild(progressBar);
    progressDiv.appendChild(progressText);
    card.appendChild(progressDiv);

    // Inline transfer button (seeding torrents only)
    const actionDiv = document.createElement('div');
    actionDiv.className = 'torrent-action-wrapper';
    if (isSeeding) {
        actionDiv.appendChild(createInlineTransferButton(torrentId, clientName));
    }
    card.appendChild(actionDiv);

    // Highlight if selected
    if (selectedHashes.has(torrentId.toLowerCase())) {
        card.classList.add('selected');
    }

    return card;
}

function updateClientTorrentCard(card, torrentData, isCrossSeed, isSeeding, torrentId, clientName) {
    // Update checkbox
    let cb = card.querySelector('.torrent-checkbox');
    if (!cb) {
        // Add checkbox if missing (shouldn't happen but be safe)
        const cbWrapper = document.createElement('div');
        cbWrapper.className = 'torrent-checkbox-wrapper';
        cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'torrent-checkbox';
        cb.dataset.hash = torrentId;
        cb.addEventListener('change', () => toggleSelection(torrentId, clientName));
        cbWrapper.appendChild(cb);
        card.insertBefore(cbWrapper, card.firstChild);
    }
    cb.checked = selectedHashes.has(torrentId.toLowerCase());
    cb.disabled = !isSeeding;

    // Update cross-seed badge
    const nameDiv = card.querySelector('.simple-torrent-name');
    const existingBadge = nameDiv?.querySelector('.cross-seed-badge');
    if (isCrossSeed && !existingBadge && nameDiv) {
        const badge = document.createElement('span');
        badge.className = 'cross-seed-badge';
        badge.title = 'Cross-seed — shares data with another torrent';
        badge.innerHTML = '<i class="fas fa-link"></i>';
        nameDiv.appendChild(badge);
    } else if (!isCrossSeed && existingBadge) {
        existingBadge.remove();
    }

    // Update state
    const stateDiv = card.querySelector('.simple-torrent-state');
    const stateText = torrentData.state || 'Unknown';
    const stateClass = getStateIndicatorClass(stateText.toUpperCase());
    const stateIndicator = stateDiv.querySelector('.state-indicator');
    if (stateIndicator) stateIndicator.className = `state-indicator ${stateClass}`;
    Array.from(stateDiv.childNodes).forEach(node => {
        if (node.nodeType === Node.TEXT_NODE) stateDiv.removeChild(node);
    });
    stateDiv.appendChild(document.createTextNode(' ' + stateText));

    // Update progress
    const progressFill = card.querySelector('.simple-progress-fill');
    const progressText = card.querySelector('.simple-progress-text');
    const progressValue = torrentData.progress || 0;
    progressFill.style.width = `${progressValue}%`;
    progressText.textContent = `${Math.round(progressValue)}%`;

    // Update inline transfer button visibility
    let actionDiv = card.querySelector('.torrent-action-wrapper');
    if (!actionDiv) {
        actionDiv = document.createElement('div');
        actionDiv.className = 'torrent-action-wrapper';
        card.appendChild(actionDiv);
    }
    const existingBtn = actionDiv.querySelector('.torrent-transfer-btn');
    if (isSeeding && !existingBtn) {
        actionDiv.appendChild(createInlineTransferButton(torrentId, clientName));
    } else if (!isSeeding && existingBtn) {
        existingBtn.remove();
    }

    // Selection highlight
    card.classList.toggle('selected', selectedHashes.has(torrentId.toLowerCase()));
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
