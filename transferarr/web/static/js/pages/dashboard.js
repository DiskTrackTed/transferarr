document.addEventListener('DOMContentLoaded', function() {
    // Initial data fetch
    fetchTorrents();
    fetchHistoryStats();
    
    // Set up regular updates
    setInterval(fetchTorrents, 2000); // Refresh torrents for dashboard every 2 seconds
    setInterval(fetchHistoryStats, 10000); // Refresh history stats every 10 seconds
});

// Fetch torrents data for dashboard and managed transfers
async function fetchTorrents() {
    try {
        const torrents = await API.fetchTorrents();
        
        // Update dashboard stats (active and copying only)
        updateDashboardStats(torrents);
        
        // Update recent torrents on dashboard
        updateRecentTorrents(torrents);
    } catch (error) {
        console.error('Error fetching torrents:', error);
    }
}

// Fetch history stats for completed count
async function fetchHistoryStats() {
    try {
        const response = await fetch('/api/v1/transfers/stats');
        const data = await response.json();
        
        if (response.ok && data.data) {
            document.getElementById('completed-torrents').textContent = data.data.completed || 0;
        }
    } catch (error) {
        console.error('Error fetching history stats:', error);
    }
}

// Update the dashboard stats
function updateDashboardStats(torrents) {
    const activeTorrents = torrents.length;
    const copyingTorrents = torrents.filter(t => 
        t.state === 'COPYING'
    ).length;
    
    document.getElementById('active-torrents').textContent = activeTorrents;
    document.getElementById('copying-torrents').textContent = copyingTorrents;
}

// Update current torrents on dashboard with in-place updates
function updateRecentTorrents(torrents) {
    const container = document.getElementById('recent-torrents-container');
    if (!container) return;
    
    // Clear "no torrents" message if it exists
    const noTorrentsMsg = container.querySelector('.no-torrents-msg');
    if (noTorrentsMsg && torrents.length > 0) {
        container.removeChild(noTorrentsMsg);
    }
    
    // Show "no torrents" message if there are no torrents
    if (torrents.length === 0) {
        if (!noTorrentsMsg) {
            const msgElement = document.createElement('div');
            msgElement.className = 'no-torrents-msg';
            msgElement.textContent = 'No active transfers';
            container.appendChild(msgElement);
        }
        // Clear all existing torrent cards when there are no torrents
        Array.from(container.children).forEach(child => {
            if (child.classList.contains('torrent-card')) {
                container.removeChild(child);
            }
        });
        return;
    }
    
    // Create a map of existing cards using a more reliable identifier
    const existingCards = {};
    Array.from(container.children).forEach(card => {
        if (card.classList.contains('torrent-card') && card.dataset.id) {
            existingCards[card.dataset.id] = card;
        }
    });
    
    // Create a set of current torrent IDs for tracking what to keep
    const currentTorrentIds = new Set();
    
    // Sort torrents by priority (COPYING first, then QUEUED, then others)
    const sortedTorrents = [...torrents].sort((a, b) => {
        const stateOrder = {
            'COPYING': 1,
            'QUEUED': 2,
            'HOME_SEEDING': 3
        };
        
        const aOrder = stateOrder[a.state] || 4;
        const bOrder = stateOrder[b.state] || 4;
        
        return aOrder - bOrder;
    });
    
    // Process each torrent
    sortedTorrents.forEach(torrent => {
        // Use a consistent ID (the torrent's unique identifier or hash if available, otherwise the name)
        const torrentId = torrent.id || torrent.hash || torrent.name;
        currentTorrentIds.add(torrentId);
        
        if (existingCards[torrentId]) {
            // Update existing card
            updateCardContent(existingCards[torrentId], torrent);
        } else {
            // Create new card
            const isCompact = false; // Full cards for dashboard
            const card = createTorrentCard(torrent, isCompact);
            // Make sure we set the dataset.id attribute correctly
            card.dataset.id = torrentId;
            container.appendChild(card);
        }
    });
    
    // Remove cards for torrents that no longer exist
    Object.keys(existingCards).forEach(cardId => {
        if (!currentTorrentIds.has(cardId)) {
            container.removeChild(existingCards[cardId]);
        }
    });
}

// Helper function to create a torrent card
function createTorrentCard(torrent, isCompact = false) {
    const card = document.createElement('div');
    card.className = 'torrent-card';
    card.dataset.id = torrent.id || torrent.hash || torrent.name;
    
    // Fill in the card content
    updateCardContent(card, torrent, isCompact);
    
    return card;
}

// Helper function to update a torrent card's content
function updateCardContent(card, torrent, isCompact = false) {
    // Determine progress percentage and status text
    let progressPercentage = 0;
    let statusText = 'Unknown';
    let progressBarClass = '';
    
    // Determine progress and status based on torrent state
    switch(torrent.state) {
        case 'HOME_DOWNLOADING':
            progressPercentage = torrent.progress || 0;
            statusText = 'Downloading';
            progressBarClass = 'progress-downloading';
            break;
        case 'HOME_SEEDING':
            progressPercentage = 100;
            statusText = 'Seeding (Home)';
            progressBarClass = 'progress-seeding';
            break;
        case 'TARGET_SEEDING':
            progressPercentage = 100;
            statusText = 'Seeding (Target)';
            progressBarClass = 'progress-seeding';
            break;
        case 'COPYING':
            progressPercentage = torrent.progress || 0;
            statusText = 'Copying';
            progressBarClass = 'progress-copying';
            break;
        case 'COPIED':
            progressPercentage = 100;
            statusText = 'Copied';
            progressBarClass = 'progress-copied';
            break;
        default:
            progressPercentage = torrent.progress || 0;
            statusText = torrent.state ? torrent.state.replace('_', ' ') : 'Unknown';
            progressBarClass = '';
    }
    
    // Format transfer speed if available and torrent is copying
    let transferSpeedHtml = '';
    if (torrent.state === 'COPYING' && torrent.transfer_speed !== undefined && torrent.transfer_speed > 0) {
        const speedFormatted = formatTransferSpeed(torrent.transfer_speed);
        transferSpeedHtml = `<div class="info-row"><span class="info-label">Speed:</span><span class="info-value speed-value">${speedFormatted}</span></div>`;
    }
    
    // Define the HTML content based on type
    let cardContent = `
        <div class="torrent-name">${torrent.name}</div>
        <div class="torrent-info">
            <div class="info-row">
                <span class="info-label">Status:</span>
                <span class="info-value">${statusText}</span>
            </div>
            ${transferSpeedHtml}
            <div class="info-row">
                <span class="info-label">Size:</span>
                <span class="info-value">${formatFileSize(torrent.size || 0)}</span>
            </div>
        </div>
        <div class="torrent-progress">
    `;
    
    // Add file information if available
    if (torrent.state === 'COPYING') {
        if (torrent.current_file) {
            cardContent += `<span class="file-name">File: ${torrent.current_file}</span>`;
        }
        
        if (torrent.current_file_count && torrent.total_files) {
            cardContent += `<span class="file-count">Progress: ${torrent.current_file_count} of ${torrent.total_files} files</span>`;
        }
    }
    
    // Add progress bar
    cardContent += `
            <div class="progress-container">
                <div class="progress-bar">
                    <span class="progress-fill ${progressBarClass}" style="width: ${progressPercentage}%"></span>
                    <span class="progress-text">${progressPercentage.toFixed(1)}%</span>
                </div>
            </div>
        </div>
    `;
    
    // Update the card's HTML content
    card.innerHTML = cardContent;
}

// Helper function to format file size in KB, MB, GB
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Helper function to format transfer speed in KB/s, MB/s, etc.
function formatTransferSpeed(bytesPerSecond) {
    if (bytesPerSecond === 0) return '0 B/s';
    const k = 1024;
    const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    const i = Math.floor(Math.log(bytesPerSecond) / Math.log(k));
    return parseFloat((bytesPerSecond / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}