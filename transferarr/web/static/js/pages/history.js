/**
 * History page JavaScript
 * Handles fetching, filtering, sorting, and displaying transfer history
 */

// State management
const state = {
    transfers: [],
    stats: null,
    filters: {
        status: '',
        source: '',
        target: '',
        search: '',
        from_date: '',
        to_date: ''
    },
    pagination: {
        page: 1,
        per_page: 25,
        total: 0,
        total_pages: 0
    },
    sort: {
        field: 'created_at',
        order: 'desc'
    },
    // Track known clients for filter dropdowns (avoid rebuilding if unchanged)
    knownSources: new Set(),
    knownTargets: new Set(),
    // Cache for change detection
    lastTransferIds: null,
    lastStatsHash: null
};

// DOM ready
document.addEventListener('DOMContentLoaded', function() {
    initializeFilters();
    initializeSorting();
    initializePagination();
    initializeDeleteHandlers();
    
    // Initial data fetch
    fetchStats();
    fetchTransfers();
    
    // Set up auto-refresh every 10 seconds (background refresh - no loading indicator)
    setInterval(() => {
        fetchStats(true);
        fetchTransfers(true);
    }, 10000);
});

/**
 * Initialize filter controls
 */
function initializeFilters() {
    // Status filter
    document.getElementById('filter-status').addEventListener('change', (e) => {
        state.filters.status = e.target.value;
        state.pagination.page = 1;
        fetchTransfers();
    });
    
    // Source filter
    document.getElementById('filter-source').addEventListener('change', (e) => {
        state.filters.source = e.target.value;
        state.pagination.page = 1;
        fetchTransfers();
    });
    
    // Target filter
    document.getElementById('filter-target').addEventListener('change', (e) => {
        state.filters.target = e.target.value;
        state.pagination.page = 1;
        fetchTransfers();
    });
    
    // Search filter with debounce
    let searchTimeout;
    document.getElementById('filter-search').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            state.filters.search = e.target.value;
            state.pagination.page = 1;
            fetchTransfers();
        }, 300);
    });
    
    // From date filter
    document.getElementById('filter-from-date').addEventListener('change', (e) => {
        state.filters.from_date = e.target.value;
        state.pagination.page = 1;
        fetchTransfers();
    });
    
    // To date filter
    document.getElementById('filter-to-date').addEventListener('change', (e) => {
        state.filters.to_date = e.target.value;
        state.pagination.page = 1;
        fetchTransfers();
    });
    
    // Clear filters button
    document.getElementById('btn-clear-filters').addEventListener('click', clearFilters);
}

/**
 * Initialize table column sorting
 */
function initializeSorting() {
    document.querySelectorAll('.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const field = th.dataset.sort;
            
            // Toggle sort order if same field, otherwise default to desc
            if (state.sort.field === field) {
                state.sort.order = state.sort.order === 'asc' ? 'desc' : 'asc';
            } else {
                state.sort.field = field;
                state.sort.order = 'desc';
            }
            
            // Update UI
            updateSortIndicators();
            fetchTransfers();
        });
    });
}

/**
 * Update sort indicators on table headers
 */
function updateSortIndicators() {
    document.querySelectorAll('.sortable').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.sort === state.sort.field) {
            th.classList.add(state.sort.order === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

/**
 * Initialize pagination controls
 */
function initializePagination() {
    document.getElementById('btn-prev').addEventListener('click', () => {
        if (state.pagination.page > 1) {
            state.pagination.page--;
            fetchTransfers();
        }
    });
    
    document.getElementById('btn-next').addEventListener('click', () => {
        if (state.pagination.page < state.pagination.total_pages) {
            state.pagination.page++;
            fetchTransfers();
        }
    });
}

/**
 * Initialize delete handlers for clear history and single transfer deletion
 */
function initializeDeleteHandlers() {
    // Clear History button
    document.getElementById('btn-clear-history').addEventListener('click', showClearHistoryModal);
    
    // Clear History modal buttons
    document.getElementById('clear-modal-close').addEventListener('click', hideClearHistoryModal);
    document.getElementById('clear-modal-cancel').addEventListener('click', hideClearHistoryModal);
    document.getElementById('clear-modal-confirm').addEventListener('click', clearHistory);
    
    // Delete Transfer modal buttons
    document.getElementById('delete-modal-close').addEventListener('click', hideDeleteTransferModal);
    document.getElementById('delete-modal-cancel').addEventListener('click', hideDeleteTransferModal);
    document.getElementById('delete-modal-confirm').addEventListener('click', deleteTransfer);
    
    // Close modals when clicking overlay
    document.getElementById('clear-history-modal').addEventListener('click', (e) => {
        if (e.target.id === 'clear-history-modal') hideClearHistoryModal();
    });
    document.getElementById('delete-transfer-modal').addEventListener('click', (e) => {
        if (e.target.id === 'delete-transfer-modal') hideDeleteTransferModal();
    });
}

// Track the transfer ID being deleted
let deleteTransferId = null;

/**
 * Show clear history confirmation modal
 */
function showClearHistoryModal() {
    document.getElementById('clear-history-modal').style.display = 'flex';
}

/**
 * Hide clear history confirmation modal
 */
function hideClearHistoryModal() {
    document.getElementById('clear-history-modal').style.display = 'none';
}

/**
 * Show delete transfer confirmation modal
 */
function showDeleteTransferModal(transferId, torrentName) {
    deleteTransferId = transferId;
    document.getElementById('delete-torrent-name').textContent = torrentName;
    document.getElementById('delete-transfer-modal').style.display = 'flex';
}

/**
 * Hide delete transfer confirmation modal
 */
function hideDeleteTransferModal() {
    deleteTransferId = null;
    document.getElementById('delete-transfer-modal').style.display = 'none';
}

/**
 * Clear all history (completed/failed only)
 */
async function clearHistory() {
    const confirmBtn = document.getElementById('clear-modal-confirm');
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Clearing...';
    
    try {
        const response = await fetch('/api/v1/transfers', {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (response.ok) {
            hideClearHistoryModal();
            // Show success notification if available
            if (typeof showNotification === 'function') {
                showNotification('success', data.message || 'History cleared successfully');
            }
            // Refresh data
            fetchStats();
            fetchTransfers();
        } else {
            throw new Error(data.error?.message || 'Failed to clear history');
        }
    } catch (error) {
        console.error('Error clearing history:', error);
        if (typeof showNotification === 'function') {
            showNotification('error', error.message);
        } else {
            alert('Error: ' + error.message);
        }
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fas fa-trash"></i> Clear History';
    }
}

/**
 * Delete a single transfer record
 */
async function deleteTransfer() {
    if (!deleteTransferId) return;
    
    const confirmBtn = document.getElementById('delete-modal-confirm');
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
    
    try {
        const response = await fetch(`/api/v1/transfers/${deleteTransferId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (response.ok) {
            hideDeleteTransferModal();
            // Show success notification if available
            if (typeof showNotification === 'function') {
                showNotification('success', 'Transfer record deleted');
            }
            // Refresh data
            fetchStats();
            fetchTransfers();
        } else {
            throw new Error(data.error?.message || 'Failed to delete transfer');
        }
    } catch (error) {
        console.error('Error deleting transfer:', error);
        if (typeof showNotification === 'function') {
            showNotification('error', error.message);
        } else {
            alert('Error: ' + error.message);
        }
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fas fa-trash"></i> Delete';
    }
}

/**
 * Clear all filters
 */
function clearFilters() {
    state.filters = {
        status: '',
        source: '',
        target: '',
        search: '',
        from_date: '',
        to_date: ''
    };
    state.pagination.page = 1;
    
    // Reset form controls
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-source').value = '';
    document.getElementById('filter-target').value = '';
    document.getElementById('filter-search').value = '';
    document.getElementById('filter-from-date').value = '';
    document.getElementById('filter-to-date').value = '';
    
    fetchTransfers();
}

/**
 * Fetch transfer statistics
 * @param {boolean} isBackgroundRefresh - If true, skip updates when data unchanged
 */
async function fetchStats(isBackgroundRefresh = false) {
    try {
        const response = await fetch('/api/v1/transfers/stats');
        const data = await response.json();
        
        if (response.ok && data.data) {
            // Check if stats actually changed
            const statsHash = JSON.stringify(data.data);
            const dataChanged = statsHash !== state.lastStatsHash;
            
            state.stats = data.data;
            state.lastStatsHash = statsHash;
            
            // Only update DOM if data changed or this is not a background refresh
            if (dataChanged || !isBackgroundRefresh) {
                updateStatsDisplay();
            }
        }
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

/**
 * Update stats display
 */
function updateStatsDisplay() {
    if (!state.stats) return;
    
    document.getElementById('stat-total').textContent = state.stats.total || 0;
    document.getElementById('stat-completed').textContent = state.stats.completed || 0;
    document.getElementById('stat-failed').textContent = state.stats.failed || 0;
    
    // Use success rate from API (already calculated)
    const successRate = state.stats.success_rate || 0;
    document.getElementById('stat-success-rate').textContent = `${Math.round(successRate)}%`;
    
    // Format total bytes
    document.getElementById('stat-total-bytes').textContent = formatBytes(state.stats.total_bytes_transferred || 0);
}

/**
 * Populate client filter dropdowns from transfer data
 * Only rebuilds dropdowns if client list has changed
 */
function populateClientFilters() {
    // Collect unique client names from transfers
    const sources = new Set();
    const targets = new Set();
    
    state.transfers.forEach(transfer => {
        if (transfer.source_client) sources.add(transfer.source_client);
        if (transfer.target_client) targets.add(transfer.target_client);
    });
    
    // Check if sources changed
    const sourcesChanged = !setsEqual(sources, state.knownSources);
    if (sourcesChanged) {
        state.knownSources = new Set(sources);
        const sourceSelect = document.getElementById('filter-source');
        const currentSource = sourceSelect.value;
        sourceSelect.innerHTML = '<option value="">All Sources</option>';
        Array.from(sources).sort().forEach(client => {
            const option = document.createElement('option');
            option.value = client;
            option.textContent = client;
            sourceSelect.appendChild(option);
        });
        sourceSelect.value = currentSource;
    }
    
    // Check if targets changed
    const targetsChanged = !setsEqual(targets, state.knownTargets);
    if (targetsChanged) {
        state.knownTargets = new Set(targets);
        const targetSelect = document.getElementById('filter-target');
        const currentTarget = targetSelect.value;
        targetSelect.innerHTML = '<option value="">All Targets</option>';
        Array.from(targets).sort().forEach(client => {
            const option = document.createElement('option');
            option.value = client;
            option.textContent = client;
            targetSelect.appendChild(option);
        });
        targetSelect.value = currentTarget;
    }
}

/**
 * Check if two Sets are equal
 */
function setsEqual(a, b) {
    if (a.size !== b.size) return false;
    for (const item of a) {
        if (!b.has(item)) return false;
    }
    return true;
}

/**
 * Fetch transfer history with current filters
 * @param {boolean} isBackgroundRefresh - If true, skip loading indicator
 */
async function fetchTransfers(isBackgroundRefresh = false) {
    if (!isBackgroundRefresh) {
        showLoading(true);
    }
    
    try {
        // Build query parameters
        const params = new URLSearchParams({
            page: state.pagination.page,
            per_page: state.pagination.per_page,
            sort: state.sort.field,
            order: state.sort.order
        });
        
        // Add filters
        if (state.filters.status) params.append('status', state.filters.status);
        if (state.filters.source) params.append('source', state.filters.source);
        if (state.filters.target) params.append('target', state.filters.target);
        if (state.filters.search) params.append('search', state.filters.search);
        if (state.filters.from_date) params.append('from_date', state.filters.from_date);
        if (state.filters.to_date) params.append('to_date', state.filters.to_date);
        
        const response = await fetch(`/api/v1/transfers?${params}`);
        const data = await response.json();
        
        if (response.ok && data.data) {
            const newTransfers = data.data.transfers || [];
            
            // Check if data actually changed before updating DOM
            const newIds = newTransfers.map(t => `${t.id}-${t.status}`).join(',');
            const dataChanged = newIds !== state.lastTransferIds;
            
            state.transfers = newTransfers;
            state.pagination.total = data.data.total || 0;
            state.pagination.total_pages = data.data.pages || 1;
            state.lastTransferIds = newIds;
            
            // Only update DOM if data changed or this is not a background refresh
            if (dataChanged || !isBackgroundRefresh) {
                updateTable();
                updatePagination();
            }
        } else {
            showError(data.error?.message || 'Failed to fetch transfers');
        }
    } catch (error) {
        console.error('Error fetching transfers:', error);
        showError('Network error fetching transfers');
    } finally {
        if (!isBackgroundRefresh) {
            showLoading(false);
        }
    }
}

/**
 * Show/hide loading indicator
 */
function showLoading(show) {
    document.getElementById('loading-indicator').style.display = show ? 'block' : 'none';
    document.getElementById('history-table').style.opacity = show ? '0.5' : '1';
}

/**
 * Show error message in table
 */
function showError(message) {
    const tbody = document.getElementById('history-tbody');
    tbody.innerHTML = `
        <tr class="error-row">
            <td colspan="7">
                <i class="fas fa-exclamation-triangle"></i> ${message}
            </td>
        </tr>
    `;
}

/**
 * Update the history table
 */
function updateTable() {
    const tbody = document.getElementById('history-tbody');
    const emptyState = document.getElementById('empty-state');
    
    // Populate client filter dropdowns from transfers
    populateClientFilters();
    
    if (state.transfers.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }
    
    emptyState.style.display = 'none';
    
    tbody.innerHTML = state.transfers.map(transfer => `
        <tr data-id="${transfer.id}">
            <td class="torrent-name-cell" title="${escapeHtml(transfer.torrent_name)}">
                ${escapeHtml(transfer.torrent_name)}
            </td>
            <td class="route-cell">
                <span class="client-name">${escapeHtml(transfer.source_client)}</span>
                <span class="route-arrow">→</span>
                <span class="client-name">${escapeHtml(transfer.target_client)}</span>
            </td>
            <td class="size-cell">${formatBytes(transfer.size_bytes)}</td>
            <td class="duration-cell">${formatDuration(transfer.started_at, transfer.completed_at, transfer.status)}</td>
            <td>${formatStatus(transfer.status)}</td>
            <td class="date-cell">${formatDate(transfer.created_at)}</td>
            <td class="actions-cell">
                ${canDeleteTransfer(transfer.status) ? `
                    <button class="btn-icon btn-delete-transfer" data-id="${transfer.id}" data-name="${escapeHtml(transfer.torrent_name)}" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                ` : ''}
            </td>
        </tr>
    `).join('');
    
    // Attach delete button event handlers
    tbody.querySelectorAll('.btn-delete-transfer').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const id = btn.dataset.id;
            const name = btn.dataset.name;
            showDeleteTransferModal(id, name);
        });
    });
}

/**
 * Update pagination controls
 */
function updatePagination() {
    const start = (state.pagination.page - 1) * state.pagination.per_page + 1;
    const end = Math.min(start + state.transfers.length - 1, state.pagination.total);
    
    document.getElementById('showing-start').textContent = state.pagination.total > 0 ? start : 0;
    document.getElementById('showing-end').textContent = end;
    document.getElementById('total-count').textContent = state.pagination.total;
    document.getElementById('current-page').textContent = state.pagination.page;
    document.getElementById('total-pages').textContent = state.pagination.total_pages;
    
    document.getElementById('btn-prev').disabled = state.pagination.page <= 1;
    document.getElementById('btn-next').disabled = state.pagination.page >= state.pagination.total_pages;
}

/**
 * Format bytes to human readable string
 */
function formatBytes(bytes) {
    if (bytes === 0 || bytes === null) return '0 B';
    
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + units[i];
}

/**
 * Format duration between two timestamps
 */
function formatDuration(startedAt, completedAt, status) {
    if (!startedAt) return '—';
    
    const start = new Date(startedAt);
    const end = completedAt ? new Date(completedAt) : new Date();
    
    // If still transferring, show elapsed time with indicator
    const isActive = status === 'transferring';
    
    const seconds = Math.floor((end - start) / 1000);
    
    if (seconds < 60) {
        return `${seconds}s${isActive ? ' ⏱' : ''}`;
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}m ${secs}s${isActive ? ' ⏱' : ''}`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m${isActive ? ' ⏱' : ''}`;
    }
}

/**
 * Format status as badge
 */
function formatStatus(status) {
    const statusConfig = {
        'completed': { icon: 'fa-check-circle', label: 'Completed' },
        'failed': { icon: 'fa-times-circle', label: 'Failed' },
        'transferring': { icon: 'fa-sync fa-spin', label: 'Transferring' },
        'pending': { icon: 'fa-clock', label: 'Pending' },
        'cancelled': { icon: 'fa-ban', label: 'Cancelled' }
    };
    
    const config = statusConfig[status] || { icon: 'fa-question-circle', label: status };
    
    return `<span class="status-badge ${status}">
        <i class="fas ${config.icon}"></i>
        ${config.label}
    </span>`;
}

/**
 * Format date to readable string
 */
function formatDate(dateString) {
    if (!dateString) return '—';
    
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    // If less than 24 hours ago, show relative time
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        if (hours < 1) {
            const mins = Math.floor(diff / 60000);
            if (mins < 1) {
                const secs = Math.floor(diff / 1000);
                return secs < 5 ? 'Just now' : `${secs}s ago`;
            }
            return `${mins}m ago`;
        }
        return `${hours}h ago`;
    }
    
    // Otherwise show date
    return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Check if a transfer can be deleted (not active)
 */
function canDeleteTransfer(status) {
    return !['pending', 'transferring'].includes(status);
}
