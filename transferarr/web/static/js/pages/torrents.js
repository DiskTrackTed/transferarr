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
 * Build cross-seed path groups from a client's torrent data.
 * @param {Object} clientTorrents - hash→info object for a single client
 * @returns {Object<string, string[]>} save_path → [hashes] (only groups with 2+ members)
 */
function buildCrossSeedPathGroups(clientTorrents) {
    const pathGroups = {};
    for (const [hash, info] of Object.entries(clientTorrents)) {
        const savePath = info.save_path;
        if (!savePath) continue;
        if (!pathGroups[savePath]) pathGroups[savePath] = [];
        pathGroups[savePath].push(hash);
    }
    const result = {};
    for (const [path, hashes] of Object.entries(pathGroups)) {
        if (hashes.length > 1) result[path] = hashes;
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
        const savePath = info.save_path;
        if (savePath && groups[savePath]) {
            for (const sibling of groups[savePath]) {
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
    const clientTorrents = allTorrentsCache[selectionSourceClient] || {};

    // Build lowercase-keyed lookup for O(1) access
    const lowerMap = {};
    for (const [h, info] of Object.entries(clientTorrents)) {
        lowerMap[h.toLowerCase()] = info;
    }

    const directHashes = [...selectedHashes];
    const crossSeedHashes = includeCrossSeeds ? getCrossSeedExpansion() : [];

    document.getElementById('modal-selected-count').textContent = directHashes.length;

    // Cross-seed notice (shown when including cross-seeds)
    const csNotice = document.getElementById('cross-seed-notice');
    if (crossSeedHashes.length > 0) {
        document.getElementById('cross-seed-count').textContent = crossSeedHashes.length;
        csNotice.style.display = 'flex';
    } else {
        csNotice.style.display = 'none';
    }

    // Cross-seed warning (shown when NOT including cross-seeds but siblings exist)
    const csWarning = document.getElementById('cross-seed-warning');
    if (csWarning) {
        // Check if any selected torrent has cross-seed siblings
        const potentialExpansion = getCrossSeedExpansion();
        const hasSiblings = potentialExpansion.length > 0;
        csWarning.style.display = (!includeCrossSeeds && hasSiblings) ? 'flex' : 'none';
    }

    // Build torrent list
    const listEl = document.getElementById('transfer-torrent-list');
    listEl.innerHTML = '';

    for (const hash of directHashes) {
        const info = lowerMap[hash];
        if (!info) continue;
        listEl.appendChild(createTransferListItem(info, false));
    }

    if (crossSeedHashes.length > 0) {
        const divider = document.createElement('div');
        divider.className = 'cross-seed-divider';
        divider.innerHTML = '<i class="fas fa-link"></i> Cross-seeds';
        listEl.appendChild(divider);

        for (const hash of crossSeedHashes) {
            const info = lowerMap[hash];
            if (!info) continue;
            listEl.appendChild(createTransferListItem(info, true));
        }
    }
}

function createTransferListItem(torrentInfo, isCrossSeed) {
    const item = document.createElement('div');
    item.className = 'transfer-list-item' + (isCrossSeed ? ' cross-seed-item' : '');
    
    const name = document.createElement('span');
    name.className = 'transfer-item-name';
    name.textContent = torrentInfo.name || 'Unknown';

    const size = document.createElement('span');
    size.className = 'transfer-item-size';
    const totalSize = torrentInfo.total_size || 0;
    size.textContent = formatBytes(totalSize);

    item.appendChild(name);
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
        const result = await API.initiateManualTransfer({
            hashes: [...selectedHashes],
            source_client: selectionSourceClient,
            destination_client: destSelect.value,
            include_cross_seeds: includeCrossSeeds,
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
