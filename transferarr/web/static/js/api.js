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
            const response = await fetch('/api/v1/torrents');
            const json = await response.json();
            // Unwrap data envelope (supports both old and new format)
            return json.data || json;
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
            const response = await fetch('/api/v1/all_torrents');
            const json = await response.json();
            // Unwrap data envelope (supports both old and new format)
            return json.data || json;
        } catch (error) {
            console.error('Error fetching all torrents:', error);
            return {};
        }
    },
};
