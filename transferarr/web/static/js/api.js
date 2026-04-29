/**
 * API client for Transferarr
 */
async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    let json = {};
    try {
        json = await response.json();
    } catch {
        json = {};
    }

    if (!response.ok) {
        const error = new Error(json.error?.message || `Request failed with status ${response.status}`);
        error.status = response.status;
        error.code = json.error?.code || 'REQUEST_FAILED';
        error.details = json.error?.details || {};
        throw error;
    }

    return json.data || json;
}

const API = {
    /**
     * Fetch torrents data
     * @returns {Promise<Array>} Torrents data
     */
    fetchTorrents: async function() {
        try {
            return await fetchJson('/api/v1/torrents');
        } catch (error) {
            console.error('Error fetching torrents:', error);
            return [];
        }
    },

    /**
     * Fetch configured download client names.
     * @returns {Promise<Array<string>>} Configured client names
     */
    fetchDownloadClients: async function() {
        const clients = await fetchJson('/api/v1/download_clients');
        return Object.keys(clients || {});
    },

    /**
     * Fetch torrents for a single client.
     * @param {string} clientName - Configured download client name
     * @param {AbortSignal} [signal] - Abort signal for in-flight cancellation
     * @returns {Promise<Object>} Torrent data keyed by torrent hash
     */
    fetchClientTorrents: async function(clientName, signal) {
        return fetchJson(
            `/api/v1/clients/${encodeURIComponent(clientName)}/torrents`,
            { signal }
        );
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
