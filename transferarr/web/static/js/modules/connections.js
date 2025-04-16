/**
 * Connection management module - handles all connection CRUD operations
 */

// Module-level variables
let connectionModal;
let directoryBrowserModal;
let currentBrowseTarget = null;
let currentBrowseSide = null;
let currentBrowsePath = '/';
let browseSftpConfig = null;
let browseType = 'local';

// Initialize the connections module
export function initConnections(modals) {
    console.log('Initializing connections module');
    connectionModal = modals.connectionModal;
    directoryBrowserModal = modals.directoryBrowserModal;
    
    // Initialize the connection form event listeners
    initConnectionForm();
    
    // Add connection button functionality
    const addConnectionBtn = document.getElementById('addConnectionBtn');
    if (addConnectionBtn) {
        addConnectionBtn.addEventListener('click', function() {
            resetConnectionForm();
            
            // Load clients for the dropdowns
            populateClientDropdowns().then(() => {
                document.getElementById('connectionModalTitle').textContent = 'Add Connection';
                connectionModal.show();
                
                // Set default types and show appropriate config sections
                document.getElementById('fromType').value = 'sftp';
                document.getElementById('toType').value = 'sftp';
                toggleConfigSection('from', 'sftp');
                toggleConfigSection('to', 'sftp');
            });
        });
    }

    // Save connection button event
    const saveConnectionBtn = document.getElementById('saveConnectionBtn');
    if (saveConnectionBtn) {
        saveConnectionBtn.addEventListener('click', saveConnection);
    }
    
    // Test connection button event
    const testConnectionBtn = document.getElementById('testConnectionBtn2');
    if (testConnectionBtn) {
        testConnectionBtn.addEventListener('click', testConnection);
    }
    
    // Add event listeners to connection form fields
    setupConnectionFormListeners();
    
    // Import and initialize directory browser 
    import('./directorybrowser.js').then(dirBrowserModule => {
        dirBrowserModule.initDirectoryBrowser(modals);
    }).catch(error => {
        console.error('Error loading directory browser module:', error);
    });
}

// Load connections data
export function loadConnections() {
    console.log('Loading connections...');
    // Show loading indicator
    const loadingElement = document.getElementById('loadingConnections');
    if (loadingElement) {
        loadingElement.style.display = 'flex';
    }
    
    const connectionsListElement = document.getElementById('connectionsList');
    if (connectionsListElement) {
        // Clear all connection cards first to prevent duplication
        connectionsListElement.innerHTML = '';
        
        // Re-add the empty state element
        const emptyState = document.createElement('div');
        emptyState.className = 'empty-state';
        emptyState.innerHTML = `
            <i class="fas fa-exchange-alt"></i>
            <h4>No Connections</h4>
            <p>Add a connection to transfer torrents between clients</p>
        `;
        connectionsListElement.appendChild(emptyState);
    }
    
    fetch('/api/connections')
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server returned ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(connections => {
            console.log('Connections data received:', connections);
            
            if (!connectionsListElement) {
                console.error('connectionsList element not found');
                return;
            }
            
            // Hide loading indicator
            if (loadingElement) {
                loadingElement.style.display = 'none';
            }
            
            // Show/hide empty state message
            const emptyStateEl = connectionsListElement.querySelector('.empty-state');
            if (connections.length === 0) {
                // Show empty state
                if (emptyStateEl) {
                    emptyStateEl.style.display = 'block';
                }
                return;
            } else if (emptyStateEl) {
                // Hide empty state if we have connections
                emptyStateEl.style.display = 'none';
            }
            
            // Create connection cards
            connections.forEach(connection => {
                connectionsListElement.appendChild(createConnectionCard(connection));
            });
        })
        .catch(error => {
            console.error('Error loading connections:', error);
            
            if (connectionsListElement) {
                // Show the error in the connection list
                const emptyStateEl = connectionsListElement.querySelector('.empty-state');
                if (emptyStateEl) {
                    emptyStateEl.style.display = 'none';
                }
                
                const errorEl = document.createElement('div');
                errorEl.className = 'alert alert-danger';
                errorEl.textContent = `Error loading connections: ${error.message}`;
                connectionsListElement.appendChild(errorEl);
            }
            
            // Hide loading indicator
            if (loadingElement) {
                loadingElement.style.display = 'none';
            }
            
            // Show error notification
            TransferarrNotifications.error(
                'Error Loading Connections',
                error.message
            );
        });
}

// Create connection card UI element
function createConnectionCard(connection) {
    const card = document.createElement('div');
    card.className = 'connection-card';
    card.dataset.id = connection.id;
    
    // Create card header
    const cardHeader = document.createElement('div');
    cardHeader.className = 'card-header';
    cardHeader.textContent = `${connection.from} → ${connection.to}`;
    
    // Create card body
    const cardBody = document.createElement('div');
    cardBody.className = 'card-body';
    
    // Create connection info
    const connectionInfo = document.createElement('div');
    connectionInfo.className = 'connection-info';
    
    // Add connection details
    connectionInfo.innerHTML = `
        <p><strong>Status:</strong> <span class="status-badge ${connection.status.toLowerCase()}">${connection.status}</span></p>
        <p><strong>From Client:</strong> ${connection.from}</p>
        <p><strong>To Client:</strong> ${connection.to}</p>
        <p><strong>Active Transfers:</strong> ${connection.active_transfers} / ${connection.max_transfers}</p>
        <p><strong>Total Transfers:</strong> ${connection.total_transfers}</p>
    `;
    
    // Create actions div
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'connection-actions';
    
    // Create edit button
    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-sm btn-primary';
    editBtn.innerHTML = '<i class="fas fa-edit"></i> Edit';
    editBtn.addEventListener('click', function() {
        editConnection(connection);
    });
    
    // Create delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-sm btn-danger';
    deleteBtn.innerHTML = '<i class="fas fa-trash"></i> Delete';
    deleteBtn.addEventListener('click', function() {
        console.log("Connection delete button clicked");
        // Show confirmation dialog
        if (confirm(`Are you sure you want to delete the connection from ${connection.from} to ${connection.to}?`)) {
            deleteConnection(connection.id);
        }
    });
    
    // Add buttons to actions div
    actionsDiv.appendChild(editBtn);
    actionsDiv.appendChild(deleteBtn);
    
    // Add info and actions to card body
    cardBody.appendChild(connectionInfo);
    cardBody.appendChild(actionsDiv);
    
    // Add header and body to card
    card.appendChild(cardHeader);
    card.appendChild(cardBody);
    
    return card;
}

// Delete connection function
function deleteConnection(connectionId) {
    // Call API to delete the connection
    fetch(`/api/connections/${connectionId}`, {
        method: 'DELETE'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(error => {
                throw new Error(error.error || 'Unknown error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        // Reload connections list
        loadConnections();
        
        // Show success notification
        TransferarrNotifications.success(
            'Connection Deleted',
            data.message || `Connection has been deleted successfully.`
        );
    })
    .catch(error => {
        TransferarrNotifications.error(
            'Error Deleting Connection',
            error.message
        );
    });
}

// Edit existing connection
function editConnection(connection) {
    resetConnectionForm();
    
    // Populate the basic form with connection data
    document.getElementById('connectionId').value = connection.id;
    
    // Load clients for the dropdowns
    populateClientDropdowns().then(() => {
        // Set selected values after clients are loaded
        document.getElementById('fromClient').value = connection.from;
        document.getElementById('toClient').value = connection.to;
        
        // Set transfer types and show appropriate config sections
        const fromType = connection.transfer_config?.from?.type || 'sftp';
        const toType = connection.transfer_config?.to?.type || 'sftp';
        
        document.getElementById('fromType').value = fromType;
        document.getElementById('toType').value = toType;
        
        toggleConfigSection('from', fromType);
        toggleConfigSection('to', toType);
        
        // Populate SFTP config if available
        if (fromType === 'sftp' && connection.transfer_config?.from?.sftp) {
            const fromSftp = connection.transfer_config.from.sftp;
            
            // Determine if using SSH config or direct credentials
            if (fromSftp.ssh_config_file) {
                document.getElementById('fromUseSshConfig').checked = true;
                document.getElementById('fromSshConfigFile').value = fromSftp.ssh_config_file;
                document.getElementById('fromSshConfigHost').value = fromSftp.ssh_config_host;
                document.getElementById('fromSshConfigSection').style.display = 'block';
                
                // Hide direct SFTP fields
                const directFields = document.querySelectorAll('#fromSftpConfig input:not([id^="fromSshConfig"])');
                for (let i = 0; i < directFields.length; i++) {
                    if (directFields[i].id !== 'fromUseSshConfig') {
                        directFields[i].parentElement.style.display = 'none';
                    }
                }
            } else {
                document.getElementById('fromSftpHost').value = fromSftp.host || '';
                document.getElementById('fromSftpPort').value = fromSftp.port || 22;
                document.getElementById('fromSftpUsername').value = fromSftp.username || '';
                document.getElementById('fromSftpPassword').value = fromSftp.password || '';
            }
        }
        
        if (toType === 'sftp' && connection.transfer_config?.to?.sftp) {
            const toSftp = connection.transfer_config.to.sftp;
            
            // Determine if using SSH config or direct credentials
            if (toSftp.ssh_config_file) {
                document.getElementById('toUseSshConfig').checked = true;
                document.getElementById('toSshConfigFile').value = toSftp.ssh_config_file;
                document.getElementById('toSshConfigHost').value = toSftp.ssh_config_host;
                document.getElementById('toSshConfigSection').style.display = 'block';
                
                // Hide direct SFTP fields
                const directFields = document.querySelectorAll('#toSftpConfig input:not([id^="toSshConfig"])');
                for (let i = 0; i < directFields.length; i++) {
                    if (directFields[i].id !== 'toUseSshConfig') {
                        directFields[i].parentElement.style.display = 'none';
                    }
                }
            } else {
                document.getElementById('toSftpHost').value = toSftp.host || '';
                document.getElementById('toSftpPort').value = toSftp.port || 22;
                document.getElementById('toSftpUsername').value = toSftp.username || '';
                document.getElementById('toSftpPassword').value = toSftp.password || '';
            }
        }

        // Populate path configuration
        document.getElementById('sourceDotTorrentPath').value = connection.source_dot_torrent_path || '';
        document.getElementById('sourceTorrentDownloadPath').value = connection.source_torrent_download_path || '';
        document.getElementById('destinationDotTorrentTmpDir').value = connection.destination_dot_torrent_tmp_dir || '';
        document.getElementById('destinationTorrentDownloadPath').value = connection.destination_torrent_download_path || '';
        
        // Initially disable path configuration but test connection to possibly enable it
        disablePathConfiguration();
        
        // Show the modal
        document.getElementById('connectionModalTitle').textContent = 'Edit Connection';
        connectionModal.show();

        // When editing an existing connection, automatically test it to enable path configuration
        document.getElementById('testConnectionBtn2').click();
    });
}

// Populate client dropdown options
function populateClientDropdowns() {
    return new Promise((resolve, reject) => {
        fetch('/api/download_clients')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Server returned ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                const clients = data
                const fromClientDropdown = document.getElementById('fromClient');
                const toClientDropdown = document.getElementById('toClient');
                
                // Clear existing options
                fromClientDropdown.innerHTML = '';
                toClientDropdown.innerHTML = '';
                
                // Add options for each client
                for (const [name, client] of Object.entries(clients)) {
                    const fromOption = document.createElement('option');
                    fromOption.value = name;
                    fromOption.textContent = name;
                    fromClientDropdown.appendChild(fromOption);
                    
                    const toOption = document.createElement('option');
                    toOption.value = name;
                    toOption.textContent = name;
                    toClientDropdown.appendChild(toOption);
                }
                
                resolve();
            })
            .catch(error => {
                console.error('Error loading clients for dropdowns:', error);
                reject(error);
            });
    });
}

// Reset the connection form to default state
function resetConnectionForm() {
    document.getElementById('connectionForm').reset();
    document.getElementById('connectionId').value = '';
    document.getElementById('saveConnectionBtn').disabled = true;
    resetTestConnectionBtn();
    
    // Disable path configuration section
    disablePathConfiguration();
    
    // Reset visibility of config sections
    document.getElementById('fromSftpConfig').style.display = 'none';
    document.getElementById('toSftpConfig').style.display = 'none';
    document.getElementById('fromSshConfigSection').style.display = 'none';
    document.getElementById('toSshConfigSection').style.display = 'none';
    
    // Show all direct SFTP fields
    const fromDirectFields = document.querySelectorAll('#fromSftpConfig input:not([id^="fromSshConfig"])');
    for (let i = 0; i < fromDirectFields.length; i++) {
        if (fromDirectFields[i].id !== 'fromUseSshConfig') {
            fromDirectFields[i].parentElement.style.display = 'block';
        }
    }
    
    const toDirectFields = document.querySelectorAll('#toSftpConfig input:not([id^="toSshConfig"])');
    for (let i = 0; i < toDirectFields.length; i++) {
        if (toDirectFields[i].id !== 'toUseSshConfig') {
            toDirectFields[i].parentElement.style.display = 'block';
        }
    }

    document.getElementById('sourceDotTorrentPath').value = "";
    document.getElementById('sourceTorrentDownloadPath').value = "";
    document.getElementById('destinationDotTorrentTmpDir').value = "";
    document.getElementById('destinationTorrentDownloadPath').valu = "";
}

// Reset test connection button state
function resetTestConnectionBtn() {
    const testBtn = document.getElementById('testConnectionBtn2');
    testBtn.classList.remove('btn-danger');
    testBtn.classList.remove('btn-success');
    testBtn.classList.add('btn-info');
    testBtn.innerHTML = '<i class="fas fa-plug"></i> Test Connection';
}

// Enable the path configuration section
function enablePathConfiguration() {
    // Hide the overlay
    const overlay = document.getElementById('pathConfigDisabledOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
    
    // Enable all path input fields and browse buttons
    const pathInputs = document.querySelectorAll('.path-config-section input, .path-config-section button.browse-btn');
    pathInputs.forEach(input => {
        input.disabled = false;
    });
}

// Disable the path configuration section
function disablePathConfiguration() {
    // Show the overlay
    const overlay = document.getElementById('pathConfigDisabledOverlay');
    if (overlay) {
        overlay.style.display = 'flex';
    }
    
    // Disable all path input fields and browse buttons
    const pathInputs = document.querySelectorAll('.path-config-section input, .path-config-section button.browse-btn');
    pathInputs.forEach(input => {
        input.disabled = true;
    });
}

// Test connection functionality
function testConnection() {
    const testBtn = document.getElementById('testConnectionBtn2');
    const originalText = testBtn.innerHTML;
    
    // Show loading state
    testBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    testBtn.disabled = true;
    
    // Get selected clients and types
    const fromClient = document.getElementById('fromClient').value;
    const toClient = document.getElementById('toClient').value;
    const fromType = document.getElementById('fromType').value;
    const toType = document.getElementById('toType').value;
    
    // Validate selection
    if (!fromClient || !toClient) {
        testBtn.innerHTML = originalText;
        testBtn.disabled = false;
        TransferarrNotifications.error('Error', 'Please select both source and destination clients');
        return;
    }
    
    if (fromClient === toClient) {
        testBtn.innerHTML = originalText;
        testBtn.disabled = false;
        TransferarrNotifications.error('Error', 'Source and destination clients cannot be the same');
        return;
    }
    
    // Create connection test data
    const connectionData = {
        from: fromClient,
        to: toClient,
        transfer_config: {
            from: {
                type: fromType
            },
            to: {
                type: toType
            }
        }
    };
    
    // Add SFTP configuration if selected
    if (fromType === 'sftp') {
        const useFromSshConfig = document.getElementById('fromUseSshConfig').checked;
        
        if (useFromSshConfig) {
            connectionData.transfer_config.from.sftp = {
                ssh_config_file: document.getElementById('fromSshConfigFile').value,
                ssh_config_host: document.getElementById('fromSshConfigHost').value
            };
        } else {
            connectionData.transfer_config.from.sftp = {
                host: document.getElementById('fromSftpHost').value,
                port: parseInt(document.getElementById('fromSftpPort').value) || 22,
                username: document.getElementById('fromSftpUsername').value,
                password: document.getElementById('fromSftpPassword').value
            };
        }
    }
    
    if (toType === 'sftp') {
        const useToSshConfig = document.getElementById('toUseSshConfig').checked;
        
        if (useToSshConfig) {
            connectionData.transfer_config.to.sftp = {
                ssh_config_file: document.getElementById('toSshConfigFile').value,
                ssh_config_host: document.getElementById('toSshConfigHost').value
            };
        } else {
            connectionData.transfer_config.to.sftp = {
                host: document.getElementById('toSftpHost').value,
                port: parseInt(document.getElementById('toSftpPort').value) || 22,
                username: document.getElementById('toSftpUsername').value,
                password: document.getElementById('toSftpPassword').value
            };
        }
    }
    
    // Test connection
    fetch('/api/connections/test', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(connectionData)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(error => {
                throw new Error(error.error || 'Unknown error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        // Re-enable button
        testBtn.disabled = false;
        
        if (data.success) {
            // Success state
            testBtn.innerHTML = '<i class="fas fa-check"></i> Connection Successful';
            testBtn.classList.remove('btn-info');
            testBtn.classList.remove('btn-danger');
            testBtn.classList.add('btn-success');
            
            // Enable the save button on successful connection
            document.getElementById('saveConnectionBtn').disabled = false;
            
            // Enable path configuration
            enablePathConfiguration();
            
            // Show success notification
            TransferarrNotifications.success(
                'Connection Successful',
                `Successfully connected from ${fromClient} to ${toClient}.`
            );
        } else {
            // Error state
            testBtn.innerHTML = '<i class="fas fa-times"></i> Connection Failed';
            testBtn.classList.remove('btn-info');
            testBtn.classList.remove('btn-success');
            testBtn.classList.add('btn-danger');
            
            // Keep the save button disabled
            document.getElementById('saveConnectionBtn').disabled = true;
            
            // Ensure path configuration is disabled
            disablePathConfiguration();
            
            // Show error notification
            TransferarrNotifications.error(
                'Connection Failed',
                data.message || 'Failed to establish connection'
            );
        }
    })
    .catch(error => {
        // Re-enable button
        testBtn.disabled = false;
        
        // Error state
        testBtn.innerHTML = '<i class="fas fa-times"></i> Connection Failed';
        testBtn.classList.remove('btn-info');
        testBtn.classList.remove('btn-success');
        testBtn.classList.add('btn-danger');
        
        // Keep the save button disabled
        document.getElementById('saveConnectionBtn').disabled = true;
        
        // Ensure path configuration is disabled
        disablePathConfiguration();
        
        // Show error notification
        TransferarrNotifications.error(
            'Connection Failed',
            error.message
        );
        
        // Reset after 3 seconds
        setTimeout(function() {
            testBtn.innerHTML = originalText;
            testBtn.classList.remove('btn-danger');
            testBtn.classList.add('btn-info');
        }, 3000);
    });
}

// Save connection to server
function saveConnection() {
    // If the button is disabled, don't proceed
    if (document.getElementById('saveConnectionBtn').disabled) {
        return;
    }
    
    const connectionId = document.getElementById('connectionId').value;
    const fromClient = document.getElementById('fromClient').value;
    const toClient = document.getElementById('toClient').value;
    const fromType = document.getElementById('fromType').value;
    const toType = document.getElementById('toType').value;
    
    if (fromClient === toClient) {
        TransferarrNotifications.error(
            'Error Saving Connection',
            'Source and destination clients cannot be the same'
        );
        return;
    }
    
    // Prepare connection data
    const connectionData = {
        from: fromClient,
        to: toClient,
        transfer_config: {
            from: {
                type: fromType
            },
            to: {
                type: toType
            }
        },
        // Add path configuration
        source_dot_torrent_path: document.getElementById('sourceDotTorrentPath').value,
        source_torrent_download_path: document.getElementById('sourceTorrentDownloadPath').value,
        destination_dot_torrent_tmp_dir: document.getElementById('destinationDotTorrentTmpDir').value,
        destination_torrent_download_path: document.getElementById('destinationTorrentDownloadPath').value
    };
    
    // Add SFTP configuration if selected
    if (fromType === 'sftp') {
        const useFromSshConfig = document.getElementById('fromUseSshConfig').checked;
        
        if (useFromSshConfig) {
            connectionData.transfer_config.from.sftp = {
                ssh_config_file: document.getElementById('fromSshConfigFile').value,
                ssh_config_host: document.getElementById('fromSshConfigHost').value
            };
        } else {
            connectionData.transfer_config.from.sftp = {
                host: document.getElementById('fromSftpHost').value,
                port: parseInt(document.getElementById('fromSftpPort').value) || 22,
                username: document.getElementById('fromSftpUsername').value,
                password: document.getElementById('fromSftpPassword').value
            };
        }
    }
    
    if (toType === 'sftp') {
        const useToSshConfig = document.getElementById('toUseSshConfig').checked;
        
        if (useToSshConfig) {
            connectionData.transfer_config.to.sftp = {
                ssh_config_file: document.getElementById('toSshConfigFile').value,
                ssh_config_host: document.getElementById('toSshConfigHost').value
            };
        } else {
            connectionData.transfer_config.to.sftp = {
                host: document.getElementById('toSftpHost').value,
                port: parseInt(document.getElementById('toSftpPort').value) || 22,
                username: document.getElementById('toSftpUsername').value,
                password: document.getElementById('toSftpPassword').value
            };
        }
    }
    
    // Determine API endpoint and method
    let url = '/api/connections';
    let method = 'POST';
    
    if (connectionId) {
        url = `/api/connections/${connectionId}`;
        method = 'PUT';
    }
    
    // Call the API
    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(connectionData)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(error => {
                throw new Error(error.error || 'Unknown error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        connectionModal.hide();
        loadConnections();
        
        TransferarrNotifications.success(
            connectionId ? 'Connection Updated' : 'Connection Added',
            `The connection from ${fromClient} to ${toClient} has been ${connectionId ? 'updated' : 'added'} successfully.`
        );
    })
    .catch(error => {
        TransferarrNotifications.error(
            'Error Saving Connection',
            error.message
        );
    });
}

// Set up event listeners for the connection form inputs
function setupConnectionFormListeners() {
    // Main dropdowns
    const connectionDropdowns = ['fromClient', 'toClient', 'fromType', 'toType'];
    connectionDropdowns.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('change', () => {
                document.getElementById('saveConnectionBtn').disabled = true;
                resetTestConnectionBtn();
                disablePathConfiguration(); // Disable path config on field change
            });
        }
    });
    
    // SFTP fields for both from and to sections
    const sftpFieldSuffixes = ['SftpHost', 'SftpPort', 'SftpUsername', 'SftpPassword', 'UseSshConfig', 
                            'SshConfigFile', 'SshConfigHost'];
    const prefixes = ['from', 'to'];
    
    prefixes.forEach(prefix => {
        sftpFieldSuffixes.forEach(suffix => {
            const fieldId = prefix + suffix;
            const field = document.getElementById(fieldId);
            if (field) {
                ['change', 'input'].forEach(eventType => {
                    field.addEventListener(eventType, () => {
                        document.getElementById('saveConnectionBtn').disabled = true;
                        resetTestConnectionBtn();
                        disablePathConfiguration(); // Disable path config on field change
                    });
                });
            }
        });
    });
}

// Initialize connection form with event listeners
function initConnectionForm() {
    // Show/hide SFTP config sections based on selected type
    document.getElementById('fromType').addEventListener('change', function() {
        toggleConfigSection('from', this.value);
    });
    
    document.getElementById('toType').addEventListener('change', function() {
        toggleConfigSection('to', this.value);
    });
    
    // Toggle between direct SFTP and SSH config
    document.getElementById('fromUseSshConfig').addEventListener('change', function() {
        document.getElementById('fromSshConfigSection').style.display = 
            this.checked ? 'block' : 'none';
        
        // Toggle visibility of direct SFTP fields
        const directFields = document.querySelectorAll('#fromSftpConfig input:not([id^="fromSshConfig"])');
        for (let i = 0; i < directFields.length; i++) {
            if (directFields[i].id !== 'fromUseSshConfig') {
                directFields[i].parentElement.style.display = 
                    this.checked ? 'none' : 'block';
            }
        }
    });
    
    document.getElementById('toUseSshConfig').addEventListener('change', function() {
        document.getElementById('toSshConfigSection').style.display = 
            this.checked ? 'block' : 'none';
        
        // Toggle visibility of direct SFTP fields
        const directFields = document.querySelectorAll('#toSftpConfig input:not([id^="toSshConfig"])');
        for (let i = 0; i < directFields.length; i++) {
            if (directFields[i].id !== 'toUseSshConfig') {
                directFields[i].parentElement.style.display = 
                    this.checked ? 'none' : 'block';
            }
        }
    });
}

// Toggle config sections based on type
function toggleConfigSection(direction, type) {
    const sftpConfigId = `${direction}SftpConfig`;
    
    // Hide all config sections first
    document.getElementById(sftpConfigId).style.display = 'none';
    
    // Show the selected type's config section
    if (type === 'sftp') {
        document.getElementById(sftpConfigId).style.display = 'block';
    }
}

// Directory browser initialization
function initDirectoryBrowser() {
    // Initialize browse buttons
    document.querySelectorAll('.browse-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const targetInput = this.dataset.target;
            const side = this.dataset.side; // 'from' or 'to'
            
            // Set current browse context
            currentBrowseTarget = targetInput;
            currentBrowseSide = side;
            
            // Determine connection type based on side
            browseType = (side === 'from') ? 
                document.getElementById('fromType').value : 
                document.getElementById('toType').value;
                
            // Get current path from input if exists
            const currentValue = document.getElementById(targetInput).value;
            if (currentValue) {
                currentBrowsePath = currentValue;
            } else {
                // Default paths
                currentBrowsePath = browseType === 'local' ? '/' : '~';
            }
            
            // Prepare SFTP config if needed
            if (browseType === 'sftp') {
                browseSftpConfig = {};
                
                if (side === 'from') {
                    const useFromSshConfig = document.getElementById('fromUseSshConfig').checked;
                    
                    if (useFromSshConfig) {
                        browseSftpConfig.sftp = {
                            ssh_config_file: document.getElementById('fromSshConfigFile').value,
                            ssh_config_host: document.getElementById('fromSshConfigHost').value
                        };
                    } else {
                        browseSftpConfig.sftp = {
                            host: document.getElementById('fromSftpHost').value,
                            port: parseInt(document.getElementById('fromSftpPort').value) || 22,
                            username: document.getElementById('fromSftpUsername').value,
                            password: document.getElementById('fromSftpPassword').value
                        };
                    }
                } else { // side === 'to'
                    const useToSshConfig = document.getElementById('toUseSshConfig').checked;
                    
                    if (useToSshConfig) {
                        browseSftpConfig.sftp = {
                            ssh_config_file: document.getElementById('toSshConfigFile').value,
                            ssh_config_host: document.getElementById('toSshConfigHost').value
                        };
                    } else {
                        browseSftpConfig.sftp = {
                            host: document.getElementById('toSftpHost').value,
                            port: parseInt(document.getElementById('toSftpPort').value) || 22,
                            username: document.getElementById('toSftpUsername').value,
                            password: document.getElementById('toSftpPassword').value
                        };
                    }
                }
            }
            
            // Show browser modal and load directory contents
            openDirectoryBrowser();
        });
    });

    // Parent directory button
    document.getElementById('parentDirButton').addEventListener('click', function() {
        // Get current path and extract parent
        const path = currentBrowsePath;
        let parentPath;
        
        // Handle different path formats
        if (path === '/' || path === '~') {
            parentPath = path; // Stay at root
        } else {
            // Find parent directory
            parentPath = path.substring(0, path.lastIndexOf('/'));
            if (parentPath === '') {
                parentPath = '/';
            }
        }
        
        // Load parent directory
        loadDirectoryContents(parentPath);
    });
    
    // Select directory button
    document.getElementById('selectDirectoryBtn').addEventListener('click', function() {
        // Set selected path to target input
        document.getElementById(currentBrowseTarget).value = currentBrowsePath;
        
        // Close modal
        directoryBrowserModal.hide();
    });

    // Directory browser modal focus management
    const directoryBrowserModalElement = document.getElementById('directoryBrowserModal');
    if (directoryBrowserModalElement) {
        directoryBrowserModalElement.addEventListener('hidden.bs.modal', function() {
            // Return focus to the browse button that opened this modal
            setTimeout(() => {
                document.querySelector(`.browse-btn[data-target="${currentBrowseTarget}"]`)?.focus();
            }, 10);
        });
    }
}

// Open directory browser and load initial contents
function openDirectoryBrowser() {
    // Reset any error messages
    document.getElementById('directoryBrowserError').style.display = 'none';
    
    // Show the modal
    directoryBrowserModal.show();
    
    // Load directory contents
    loadDirectoryContents(currentBrowsePath);
}

// Load directory contents via API
function loadDirectoryContents(path) {
    // Show loading spinner
    document.getElementById('directoryLoadingSpinner').style.display = 'block';
    document.getElementById('directoryContents').innerHTML = '';
    document.getElementById('currentPath').value = path;
    
    // Prepare request data
    const requestData = {
        path: path,
        type: browseType
    };
    
    // Add config if SFTP
    if (browseType === 'sftp') {
        requestData.config = browseSftpConfig;
    }
    
    // Call API to get directory contents
    fetch('/api/browse', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        // Hide loading spinner
        document.getElementById('directoryLoadingSpinner').style.display = 'none';
        
        if (data.error) {
            // Show error message
            const errorElement = document.getElementById('directoryBrowserError');
            errorElement.textContent = data.error;
            errorElement.style.display = 'block';
            return;
        }
        
        // Update current path
        currentBrowsePath = data.current_path;
        document.getElementById('currentPath').value = data.current_path;
        
        // Clear existing entries
        const tableBody = document.getElementById('directoryContents');
        tableBody.innerHTML = '';
        
        // Add parent directory entry if not at root
        if (data.parent && data.parent !== data.current_path) {
            const parentRow = document.createElement('tr');
            parentRow.className = 'directory-entry parent-dir';
            parentRow.innerHTML = `
                <td>
                    <i class="fas fa-folder-open folder-icon"></i>
                    <span class="directory-entry-name">..</span>
                </td>
                <td>Directory</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary browse-dir-btn" data-path="${data.parent}">
                        Open
                    </button>
                </td>
            `;
            tableBody.appendChild(parentRow);
        }
        
        // Add entries
        data.entries.forEach(entry => {
            const row = document.createElement('tr');
            row.className = 'directory-entry';
            if (entry.is_dir) {
                row.innerHTML = `
                    <td>
                        <i class="fas fa-folder folder-icon"></i>
                        <span class="directory-entry-name">${entry.name}</span>
                    </td>
                    <td>Directory</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary browse-dir-btn" data-path="${entry.path}">
                            Open
                        </button>
                    </td>
                `;
            } else {
                row.innerHTML = `
                    <td>
                        <i class="fas fa-file file-icon"></i>
                        <span class="directory-entry-name">${entry.name}</span>
                    </td>
                    <td>File</td>
                    <td></td>
                `;
            }
            tableBody.appendChild(row);
        });
        
        // Add event listeners to directory open buttons
        document.querySelectorAll('.browse-dir-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                loadDirectoryContents(this.dataset.path);
            });
        });
    })
    .catch(error => {
        // Hide loading spinner
        document.getElementById('directoryLoadingSpinner').style.display = 'none';
        
        // Show error message
        const errorElement = document.getElementById('directoryBrowserError');
        errorElement.textContent = `Error loading directory: ${error.message}`;
        errorElement.style.display = 'block';
        
        console.error('Error loading directory:', error);
    });
}
