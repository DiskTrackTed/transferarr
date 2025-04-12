/**
 * Client management module - handles all download client CRUD operations
 */

let clientModal;
let deleteModal;

// Initialize the client module
export function initClients(modals) {
    clientModal = modals.clientModal;
    deleteModal = modals.deleteModal;
    
    // Add client button event
    document.getElementById('addClientBtn').addEventListener('click', function() {
        resetClientForm();
        document.getElementById('editMode').value = 'false';
        document.getElementById('clientModalTitle').textContent = 'Add Download Client';
        clientModal.show();
    });
    
    // Save client button event
    document.getElementById('saveClientBtn').addEventListener('click', saveClient);
    
    // Make the save button disabled by default
    document.getElementById('saveClientBtn').disabled = true;
    
    // Confirm delete button event
    document.getElementById('confirmDeleteBtn').addEventListener('click', function() {
        const clientName = document.getElementById('deleteClientName').textContent;
        deleteClient(clientName);
    });
    
    // Test connection button event
    document.getElementById('testConnectionBtn').addEventListener('click', testConnection);
    
    // Add event listeners to all form input fields to disable save button when changed
    const connectionFields = ['clientType', 'clientHost', 'clientPort', 'clientUsername', 'clientPassword'];
    connectionFields.forEach(fieldId => {
        document.getElementById(fieldId).addEventListener('change', () => {
            document.getElementById('saveClientBtn').disabled = true;
            resetTestConnectionButton();
        });
        document.getElementById(fieldId).addEventListener('input', () => {
            document.getElementById('saveClientBtn').disabled = true;
            resetTestConnectionButton();
        });
    });
}

// Load clients from the API
export function loadClients() {
    console.log('Loading clients...');
    // Show loading indicator
    const loadingElement = document.getElementById('loadingClients');
    if (loadingElement) {
        loadingElement.style.display = 'flex';
    }
    
    const clientsListElement = document.getElementById('clientsList');
    if (clientsListElement) {
        clientsListElement.innerHTML = '';
    }
    
    console.log('Fetching clients from /api/config...');
    fetch('/api/config')
        .then(response => {
            console.log('Response received:', response.status);
            if (!response.ok) {
                throw new Error(`Server returned ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Data received:', data);
            
            if (!clientsListElement) {
                console.error('clientsList element not found');
                return;
            }
            
            const clients = data.download_clients || {};
            console.log(`Found ${Object.keys(clients).length} clients`);
            
            if (Object.keys(clients).length === 0) {
                // Show empty state
                const emptyState = document.createElement('div');
                emptyState.className = 'empty-state';
                emptyState.innerHTML = `
                    <i class="fas fa-server"></i>
                    <h4>No Download Clients</h4>
                    <p>Add a download client to get started</p>
                `;
                clientsListElement.appendChild(emptyState);
            } else {
                // Create client cards
                for (const [name, client] of Object.entries(clients)) {
                    clientsListElement.appendChild(createClientCard(name, client));
                }
            }
            
            // Hide loading indicator
            if (loadingElement) {
                loadingElement.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error loading clients:', error);
            
            if (clientsListElement) {
                clientsListElement.innerHTML = `
                    <div class="alert alert-danger">
                        Error loading download clients: ${error.message}
                    </div>
                `;
            }
            
            if (loadingElement) {
                loadingElement.style.display = 'none';
            }
            
            alert('Failed to load clients: ' + error.message);
        });
}

// Create a client card element
function createClientCard(name, client) {
    const card = document.createElement('div');
    card.className = 'client-card';
    
    // Create card header
    const cardHeader = document.createElement('div');
    cardHeader.className = 'card-header';
    cardHeader.textContent = name;
    
    // Create card body
    const cardBody = document.createElement('div');
    cardBody.className = 'card-body';
    
    // Create client info
    const clientInfo = document.createElement('div');
    clientInfo.className = 'client-info';
    
    // Add client details
    clientInfo.innerHTML = `
        <p><strong>Type:</strong> ${client.type}</p>
        <p><strong>Host:</strong> ${client.host}:${client.port}</p>
        <p><strong>Username:</strong> ${client.username}</p>
    `;
    
    // Create actions div
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'client-actions';
    
    // Create edit button
    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-sm btn-primary';
    editBtn.innerHTML = '<i class="fas fa-edit"></i> Edit';
    editBtn.addEventListener('click', function() {
        editClient(name, client);
    });
    
    // Create delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-sm btn-danger';
    deleteBtn.innerHTML = '<i class="fas fa-trash"></i> Delete';
    deleteBtn.addEventListener('click', function() {
        showDeleteConfirmation(name);
    });
    
    // Add buttons to actions div
    actionsDiv.appendChild(editBtn);
    actionsDiv.appendChild(deleteBtn);
    
    // Add info and actions to card body
    cardBody.appendChild(clientInfo);
    cardBody.appendChild(actionsDiv);
    
    // Add header and body to card
    card.appendChild(cardHeader);
    card.appendChild(cardBody);
    
    return card;
}

// Edit a client
function editClient(name, client) {
    resetClientForm();
    
    document.getElementById('editMode').value = 'true';
    document.getElementById('originalName').value = name;
    document.getElementById('clientName').value = name;
    document.getElementById('clientType').value = client.type;
    document.getElementById('clientHost').value = client.host;
    document.getElementById('clientPort').value = client.port;
    document.getElementById('clientUsername').value = client.username;
    document.getElementById('clientPassword').value = client.password;
    
    document.getElementById('clientModalTitle').textContent = 'Edit Download Client';
    resetTestConnectionButton();
    // Keep save button disabled until connection is tested
    document.getElementById('saveClientBtn').disabled = true;
    clientModal.show();
}

// Reset the test connection button state
function resetTestConnectionButton() {
    document.getElementById('testConnectionBtn').classList.remove('btn-danger');
    document.getElementById('testConnectionBtn').classList.remove('btn-success');
    document.getElementById('testConnectionBtn').classList.add('btn-info');
    document.getElementById('testConnectionBtn').innerHTML = '<i class="fas fa-plug"></i> Test Connection';
}

// Show the delete confirmation modal
function showDeleteConfirmation(name) {
    document.getElementById('deleteClientName').textContent = name;
    deleteModal.show();
}

// Reset the client form
function resetClientForm() {
    document.getElementById('clientForm').reset();
    document.getElementById('editMode').value = 'false';
    document.getElementById('originalName').value = '';
    document.getElementById('saveClientBtn').disabled = true;
}

// Save a client
function saveClient() {
    // If the button is disabled, don't proceed
    if (document.getElementById('saveClientBtn').disabled) {
        return;
    }
    
    const isEditMode = document.getElementById('editMode').value === 'true';
    const originalName = document.getElementById('originalName').value;
    const name = document.getElementById('clientName').value.trim();
    
    if (!name) {
        alert('Client name is required');
        return;
    }
    
    const clientData = {
        name: name,
        type: document.getElementById('clientType').value,
        host: document.getElementById('clientHost').value,
        port: parseInt(document.getElementById('clientPort').value),
        username: document.getElementById('clientUsername').value,
        password: document.getElementById('clientPassword').value
    };
    
    let url = '/api/download_clients';
    let method = 'POST';
    
    if (isEditMode) {
        url = `/api/download_clients/${originalName}`;
        method = 'PUT';
        delete clientData.name; // Don't need name in PUT request
    }
    
    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(clientData)
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
        clientModal.hide();
        loadClients();
        
        // Show success notification
        TransferarrNotifications.success(
            isEditMode ? 'Client Updated' : 'Client Added',
            `The download client "${name}" has been ${isEditMode ? 'updated' : 'added'} successfully.`
        );
    })
    .catch(error => {
        // Show error notification instead of alert
        TransferarrNotifications.error(
            'Error Saving Client',
            error.message
        );
    });
}

// Delete a client
function deleteClient(name) {
    fetch(`/api/download_clients/${name}`, {
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
        deleteModal.hide();
        loadClients();
        
        // Show success notification
        TransferarrNotifications.success(
            'Client Deleted',
            `The download client "${name}" has been deleted successfully.`
        );
    })
    .catch(error => {
        // Show error notification
        TransferarrNotifications.error(
            'Error Deleting Client',
            error.message
        );
        deleteModal.hide();
    });
}

// Test client connection
function testConnection() {
    const testBtn = document.getElementById('testConnectionBtn');
    const originalText = testBtn.innerHTML;
    
    // Show loading state
    testBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    testBtn.disabled = true;
    
    // Collect client data from the form
    const clientData = {
        type: document.getElementById('clientType').value,
        host: document.getElementById('clientHost').value,
        port: parseInt(document.getElementById('clientPort').value),
        username: document.getElementById('clientUsername').value,
        password: document.getElementById('clientPassword').value
    };
    
    // Validate fields before test
    if (!clientData.host || !clientData.port || !clientData.username || !clientData.password) {
        // Reset button
        testBtn.innerHTML = originalText;
        testBtn.disabled = false;
        alert('Please fill in all fields before testing the connection');
        return;
    }
    
    // Test connection
    fetch('/api/download_clients/test', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(clientData)
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
            document.getElementById('saveClientBtn').disabled = false;
            
            // Show success notification
            TransferarrNotifications.success(
                'Connection Successful',
                `Successfully connected to ${clientData.host}:${clientData.port}.`
            );
        } else {
            // Error state
            testBtn.innerHTML = '<i class="fas fa-times"></i> Connection Failed';
            testBtn.classList.remove('btn-info');
            testBtn.classList.remove('btn-success');
            testBtn.classList.add('btn-danger');
            
            // Keep the save button disabled
            document.getElementById('saveClientBtn').disabled = true;
            
            // Show error notification
            TransferarrNotifications.error(
                'Connection Failed',
                data.message
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
        document.getElementById('saveClientBtn').disabled = true;
        
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
