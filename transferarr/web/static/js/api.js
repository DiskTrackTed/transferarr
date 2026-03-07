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

    /**
     * Fetch valid destination clients for a source client
     * @param {string} sourceClient - Source client name
     * @returns {Promise<Array>} Destination client options
     */
    fetchDestinations: async function(sourceClient) {
        try {
            const response = await fetch(`/api/v1/transfers/destinations?source=${encodeURIComponent(sourceClient)}`);
            const json = await response.json();
            return json.data || [];
        } catch (error) {
            console.error('Error fetching destinations:', error);
            return [];
        }
    },

    /**
     * Initiate a manual transfer
     * @param {Object} data - Transfer request data
     * @returns {Promise<Object>} Transfer result
     */
    initiateManualTransfer: async function(data) {
        const response = await fetch('/api/v1/transfers/manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        const json = await response.json();
        if (!response.ok) {
            throw new Error(json.error?.message || 'Transfer failed');
        }
        return json;
    },
};
