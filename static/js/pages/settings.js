document.addEventListener('DOMContentLoaded', function() {
    // Initial data fetch
    fetchConfigInfo();
    
    // Set up regular updates
    setInterval(fetchConfigInfo, 5000); // Refresh stats every 5 seconds
});

// Fetch basic configuration info to display in settings
async function fetchConfigInfo() {
    try {
        const stats = await API.fetchStats();
        document.getElementById('config-info').textContent = 
            `Active transfers: ${stats.active_transfers}\n` +
            `Total torrents: ${stats.total_torrents}\n` +
            `Connections: ${stats.connections}`;
    } catch (error) {
        document.getElementById('config-info').textContent = 
            "Unable to fetch system statistics.";
    }
}
