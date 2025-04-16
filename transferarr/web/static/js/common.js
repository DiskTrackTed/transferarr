/**
 * Common utility functions for Transferarr UI
 */

// Helper function to get state indicator class
function getStateIndicatorClass(state) {
    if (state.includes('COPYING')) return 'state-copying';
    if (state.includes('SEEDING')) return 'state-seeding';
    if (state.includes('ERROR')) return 'state-error';
    if (state.includes('QUEUED')) return 'state-queued';
    return 'state-default';
}

// Create the initial card structure
function createTorrentCard(torrent, isCompact = false) {
    const card = document.createElement('div');
    card.className = 'torrent-card';
    card.dataset.id = torrent.name; // Use name as unique identifier
    
    // Create the basic structure that won't change
    const nameDiv = document.createElement('div');
    nameDiv.className = 'torrent-name';
    nameDiv.textContent = torrent.name;
    
    const infoDiv = document.createElement('div');
    infoDiv.className = 'torrent-info';
    
    const progressDiv = document.createElement('div');
    progressDiv.className = 'torrent-progress';
    
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress-container';
    
    const fileCountDiv = document.createElement('div');
    fileCountDiv.className = 'file-count';
    fileCountDiv.dataset.container = 'file-count';
    
    const fileNameDiv = document.createElement('div');
    fileNameDiv.className = 'file-name';
    fileNameDiv.dataset.container = 'file-name';
    
    const progressBar = document.createElement('div');
    progressBar.className = 'progress-bar';
    
    const progressText = document.createElement('div');
    progressText.className = 'progress-text';
    progressText.dataset.container = 'progress-text';
    
    const progressFill = document.createElement('span');
    progressFill.className = 'progress-fill';
    progressFill.dataset.container = 'progress-fill';
    
    progressBar.appendChild(progressText);
    progressBar.appendChild(progressFill);
    
    progressContainer.appendChild(fileCountDiv);
    progressContainer.appendChild(fileNameDiv);
    progressContainer.appendChild(progressBar);
    
    progressDiv.appendChild(progressContainer);
    
    // Create info rows
    if (isCompact) {
        const stateRow = createInfoRow('State', torrent.state, getStateIndicatorClass(torrent.state));
        const homeRow = createInfoRow('Home', torrent.home_client_name || 'N/A');
        const targetRow = createInfoRow('Target', torrent.target_client_name || 'N/A');
        
        infoDiv.appendChild(stateRow);
        infoDiv.appendChild(homeRow);
        infoDiv.appendChild(targetRow);
    } else {
        const stateRow = createInfoRow('State', torrent.state, getStateIndicatorClass(torrent.state));
        const homeRow = createInfoRow('Home', torrent.home_client_name || 'N/A');
        const targetRow = createInfoRow('Target', torrent.target_client_name || 'N/A');
        
        infoDiv.appendChild(stateRow);
        infoDiv.appendChild(homeRow);
        infoDiv.appendChild(targetRow);
    }
    
    card.appendChild(nameDiv);
    card.appendChild(infoDiv);
    card.appendChild(progressDiv);
    
    // Now update the card with current values
    updateCardContent(card, torrent);
    
    return card;
}

function createInfoRow(label, value, stateClass = null) {
    const row = document.createElement('div');
    row.className = 'info-row';
    
    const labelDiv = document.createElement('div');
    labelDiv.className = 'info-label';
    labelDiv.textContent = `${label}:`;
    
    const valueDiv = document.createElement('div');
    valueDiv.className = 'info-value';
    valueDiv.dataset.label = label.toLowerCase();
    
    if (stateClass) {
        const indicator = document.createElement('span');
        indicator.className = `state-indicator ${stateClass}`;
        indicator.dataset.container = 'state-indicator';
        valueDiv.appendChild(indicator);
    }
    
    const valueText = document.createTextNode(value);
    valueDiv.appendChild(valueText);
    
    row.appendChild(labelDiv);
    row.appendChild(valueDiv);
    
    return row;
}

// Update card content
function updateCardContent(card, torrent) {
    // Update file count if needed
    const fileCountDiv = card.querySelector('.file-count');
    if (torrent.state === 'COPYING' && torrent.total_files > 0) {
        fileCountDiv.textContent = `Copying file ${torrent.current_file_count} / ${torrent.total_files}`;
        fileCountDiv.style.display = 'block';
    } else {
        fileCountDiv.textContent = '';
        fileCountDiv.style.display = 'none';
    }
    
    // Update current file
    const fileNameDiv = card.querySelector('.file-name');
    fileNameDiv.textContent = torrent.current_file || '';
    
    // Update progress text
    const progressText = card.querySelector('.progress-text');
    progressText.textContent = `${Math.round(torrent.progress || 0)}%`;
    
    // Update progress fill
    const progressFill = card.querySelector('.progress-fill');
    progressFill.style.width = `${torrent.progress || 0}%`;
    
    // Update state indicator and value
    const stateValue = card.querySelector('[data-label="state"]');
    if (stateValue) {
        // Remove all text nodes (but keep the indicator)
        Array.from(stateValue.childNodes).forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                stateValue.removeChild(node);
            }
        });
        
        // Update state indicator
        const stateIndicator = stateValue.querySelector('.state-indicator');
        if (stateIndicator) {
            stateIndicator.className = `state-indicator ${getStateIndicatorClass(torrent.state)}`;
        }
        
        // Add updated text
        stateValue.appendChild(document.createTextNode(torrent.state));
    }
    
    // Update home client if present
    const homeValue = card.querySelector('[data-label="home"]');
    if (homeValue) {
        homeValue.textContent = torrent.home_client_name || 'N/A';
    }
    
    // Update target client if present
    const targetValue = card.querySelector('[data-label="target"]');
    if (targetValue) {
        targetValue.textContent = torrent.target_client_name || 'N/A';
    }
}