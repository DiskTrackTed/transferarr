/**
 * API client for Transferarr
 */
const API = {
    /**
     * Fetch torrents data
     * @returns {Promise<Array>} Torrents data
     */
    fetchTorrents: async function() {
        try {
            const response = await fetch('/api/torrents');
            return await response.json();
        } catch (error) {
            console.error('Error fetching torrents:', error);
            return [];
        }
    },
    
    /**
     * Fetch all torrents from all clients
     * @returns {Promise<Object>} All torrents data by client
     */
    fetchAllTorrents: async function() {
        try {
            const response = await fetch('/api/all_torrents');
            return await response.json();
        } catch (error) {
            console.error('Error fetching all torrents:', error);
            return {};
        }
    },
};
