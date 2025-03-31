document.addEventListener('DOMContentLoaded', function() {
    // Initial data fetch
    fetchTorrents();
    fetchConfigInfo();
    
    // Set up regular updates
    setInterval(fetchTorrents, 2000); // Refresh torrents for dashboard every 2 seconds
    setInterval(fetchConfigInfo, 5000); // Refresh stats every 5 seconds
});

// Fetch torrents data for dashboard and managed transfers
async function fetchTorrents() {
    try {
        const torrents = await API.fetchTorrents();
        
        // Update dashboard stats
        updateDashboardStats(torrents);
        
        // Update recent torrents on dashboard
        updateRecentTorrents(torrents);
    } catch (error) {
        console.error('Error fetching torrents:', error);
    }
}

// Update the dashboard stats
function updateDashboardStats(torrents) {
    const activeTorrents = torrents.length;
    const completedTorrents = torrents.filter(t => 
        t.state === 'TARGET_SEEDING' || t.state === 'COPIED'
    ).length;
    const copyingTorrents = torrents.filter(t => 
        t.state === 'COPYING'
    ).length;
    
    document.getElementById('active-torrents').textContent = activeTorrents;
    document.getElementById('completed-torrents').textContent = completedTorrents;
    document.getElementById('copying-torrents').textContent = copyingTorrents;
}

// Update current torrents on dashboard with in-place updates
function updateRecentTorrents(torrents) {
    // ...existing code...
}

// Fetch basic configuration info to display in settings
async function fetchConfigInfo() {
    try {
        const stats = await API.fetchStats();
        // Use stats data if needed on dashboard
    } catch (error) {
        console.error('Error fetching config info:', error);
    }
}