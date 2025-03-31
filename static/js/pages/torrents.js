document.addEventListener('DOMContentLoaded', function() {
    // Show loading indicator on initial load
    showLoadingIndicator();
    
    // Initial data fetch
    fetchAllTorrents();
    
    // Set up regular updates
    setInterval(fetchAllTorrents, 3000); // Refresh all torrents every 3 seconds
});

// Show loading indicator
function showLoadingIndicator() {
    const loadingIndicator = document.getElementById('loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.classList.remove('hidden');
    }
}

// Hide loading indicator
function hideLoadingIndicator() {
    const loadingIndicator = document.getElementById('loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.classList.add('hidden');
    }
}

// Fetch all torrents directly from clients for the torrents tab
async function fetchAllTorrents() {
    try {
        const allTorrentsData = await API.fetchAllTorrents();
        
        // Update client tabs with all torrents
        updateClientTabsWithAllTorrents(allTorrentsData);
        
        // Hide loading indicator after first successful load
        hideLoadingIndicator();
    } catch (error) {
        console.error('Error fetching all torrents:', error);
        
        // Hide loading indicator and show error message if needed
        hideLoadingIndicator();
    }
}

// Update client tabs with all torrents from all clients
function updateClientTabsWithAllTorrents(allTorrentsData) {
    console.log("Updating client tabs with all torrents:", allTorrentsData);
    
    // Get client names from the response
    const clientNames = Object.keys(allTorrentsData);
    
    if (clientNames.length === 0) {
        console.warn("No clients found in the response");
        return;
    }
    
    // Create tabs if they don't exist
    const clientTabsContainer = document.getElementById('client-tabs');
    const clientTabContentsContainer = document.getElementById('client-tab-contents');
    
    // Show tabs and contents when we have data
    clientTabsContainer.style.display = 'flex';
    clientTabContentsContainer.style.display = 'block';
    
    // Clear existing tabs if client list changed
    if (clientTabsContainer.children.length !== clientNames.length) {
        clientTabsContainer.innerHTML = '';
        clientTabContentsContainer.innerHTML = '';
    }
    
    let activeTabSet = false;
    let activeTabName = '';
    
    // If we have a currently active tab, remember it
    const currentActive = document.querySelector('.client-tab.active');
    if (currentActive) {
        activeTabName = currentActive.dataset.client;
    }
    
    // Check if we need to create the tabs
    if (clientTabsContainer.children.length === 0 && clientNames.length > 0) {
        clientNames.forEach((clientName, index) => {
            // Create tab
            const tab = document.createElement('div');
            tab.className = 'client-tab';
            
            // If this was the previously active tab, or it's the first one and we had no active tab
            if ((activeTabName && clientName === activeTabName) || 
                (!activeTabName && index === 0)) {
                tab.classList.add('active');
                activeTabSet = true;
            }
            
            tab.textContent = clientName;
            tab.dataset.client = clientName;
            clientTabsContainer.appendChild(tab);
            
            // Create tab content container
            const tabContent = document.createElement('div');
            tabContent.className = 'client-tab-content';
            
            if ((activeTabName && clientName === activeTabName) || 
                (!activeTabName && index === 0)) {
                tabContent.classList.add('active');
            }
            
            tabContent.id = `client-${clientName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '')}`;
            clientTabContentsContainer.appendChild(tabContent);
        });
        
        // Add event listeners to tabs
        document.querySelectorAll('.client-tab').forEach(tab => {
            tab.addEventListener('click', function() {
                // Remove active class from all tabs and content
                document.querySelectorAll('.client-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.client-tab-content').forEach(c => c.classList.remove('active'));
                
                // Add active class to clicked tab and corresponding content
                this.classList.add('active');
                const clientName = this.dataset.client;
                const safeClientName = clientName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '');
                const contentElement = document.getElementById(`client-${safeClientName}`);
                
                if (contentElement) {
                    contentElement.classList.add('active');
                }
            });
        });
    }
    
    // Update each client tab content with its torrents
    clientNames.forEach(clientName => {
        const clientTorrents = allTorrentsData[clientName] || {};
        const safeClientName = clientName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '');
        const tabContentId = `client-${safeClientName}`;
        const tabContent = document.getElementById(tabContentId);
        
        if (!tabContent) {
            console.error(`Tab content element not found: ${tabContentId}`);
            return;
        }
        
        // Clear any existing message
        const existingMessage = tabContent.querySelector('.empty-message');
        if (existingMessage) {
            tabContent.removeChild(existingMessage);
        }
        
        // Get the container for torrent cards
        let container = tabContent.querySelector('.client-torrent-container');
        
        // Create container if it doesn't exist
        if (!container) {
            container = document.createElement('div');
            container.className = 'client-torrent-container';
            tabContent.appendChild(container);
        }
        
        // Create a map of existing cards
        const existingCards = {};
        Array.from(container.children).forEach(card => {
            if (card.dataset.id) {
                existingCards[card.dataset.id] = card;
            }
        });
        
        // Get the torrent IDs from this client
        const torrentIds = Object.keys(clientTorrents);
        
        // If no torrents, show message
        if (torrentIds.length === 0) {
            container.innerHTML = '';
            const emptyMessage = document.createElement('div');
            emptyMessage.className = 'empty-message';
            emptyMessage.textContent = `No torrents for ${clientName}`;
            emptyMessage.style.padding = '20px';
            emptyMessage.style.textAlign = 'center';
            emptyMessage.style.color = '#666';
            tabContent.appendChild(emptyMessage);
            return;
        }
        
        // Update or create cards for each torrent
        torrentIds.forEach(torrentId => {
            const torrentData = clientTorrents[torrentId];
            
            if (existingCards[torrentId]) {
                // Update existing card
                updateClientTorrentCard(existingCards[torrentId], torrentData);
                delete existingCards[torrentId];
            } else {
                // Create new card
                container.appendChild(createClientTorrentCard(torrentId, torrentData));
            }
        });
        
        // Remove cards for torrents that no longer exist
        Object.values(existingCards).forEach(card => {
            container.removeChild(card);
        });
    });
    
    // If no tabs are active and we have clients, set the first one active
    const activeTab = document.querySelector('.client-tab.active');
    if (!activeTab && clientNames.length > 0 && !activeTabSet) {
        const firstTab = document.querySelector('.client-tab');
        if (firstTab) {
            firstTab.classList.add('active');
            const clientName = firstTab.dataset.client;
            const safeClientName = clientName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '');
            const contentElement = document.getElementById(`client-${safeClientName}`);
            
            if (contentElement) {
                contentElement.classList.add('active');
            }
        }
    }
}

// Create a client torrent card based on direct client data
function createClientTorrentCard(torrentId, torrentData) {
    const card = document.createElement('div');
    card.className = 'simple-torrent-card';
    card.dataset.id = torrentId;
    
    const nameDiv = document.createElement('div');
    nameDiv.className = 'simple-torrent-name';
    nameDiv.textContent = torrentData.name || 'Unknown';
    
    const stateDiv = document.createElement('div');
    stateDiv.className = 'simple-torrent-state';
    
    const stateText = torrentData.state || 'Unknown';
    const stateClass = getStateIndicatorClass(stateText.toUpperCase());
    
    const stateIndicator = document.createElement('span');
    stateIndicator.className = `state-indicator ${stateClass}`;
    stateDiv.appendChild(stateIndicator);
    stateDiv.appendChild(document.createTextNode(' ' + stateText));
    
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
    
    card.appendChild(nameDiv);
    card.appendChild(stateDiv);
    card.appendChild(progressDiv);
    
    return card;
}

// Update a client torrent card
function updateClientTorrentCard(card, torrentData) {
    const stateDiv = card.querySelector('.simple-torrent-state');
    const progressFill = card.querySelector('.simple-progress-fill');
    const progressText = card.querySelector('.simple-progress-text');
    
    const stateText = torrentData.state || 'Unknown';
    const stateClass = getStateIndicatorClass(stateText.toUpperCase());
    
    // Update state
    const stateIndicator = stateDiv.querySelector('.state-indicator');
    if (stateIndicator) {
        stateIndicator.className = `state-indicator ${stateClass}`;
    }
    
    // Remove all text nodes from stateDiv
    Array.from(stateDiv.childNodes).forEach(node => {
        if (node.nodeType === Node.TEXT_NODE) {
            stateDiv.removeChild(node);
        }
    });
    
    // Add the updated state text
    stateDiv.appendChild(document.createTextNode(' ' + stateText));
    
    // Update progress
    const progressValue = torrentData.progress || 0;
    progressFill.style.width = `${progressValue}%`;
    progressText.textContent = `${Math.round(progressValue)}%`;
}
