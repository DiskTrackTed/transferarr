/**
 * Directory browser module - handles directory browsing for both local and SFTP paths
 */

// Module-level variables
let directoryBrowserModal;
let currentBrowseTarget = null;
let currentBrowseSide = null;
let currentBrowsePath = '/';
let browseSftpConfig = null;
let browseType = 'local';
let onPathSelectedCallback = null;

/**
 * Initialize the directory browser
 * @param {Object} modals - Modal instances
 */
export function initDirectoryBrowser(modals) {
    directoryBrowserModal = modals.directoryBrowserModal;
    
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
                browseSftpConfig = prepareSftpConfig(side);
            }
            
            // Show browser modal and load directory contents
            openBrowser();
        });
    });

    // Parent directory button
    document.getElementById('parentDirButton').addEventListener('click', function() {
        navigateToParentDirectory();
    });
    
    // Select directory button
    document.getElementById('selectDirectoryBtn').addEventListener('click', function() {
        selectCurrentDirectory();
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

/**
 * Prepare SFTP configuration based on the side (from/to)
 * @param {string} side - 'from' or 'to' 
 * @returns {Object} SFTP configuration
 */
function prepareSftpConfig(side) {
    const config = {};
    
    if (side === 'from') {
        const useFromSshConfig = document.getElementById('fromUseSshConfig').checked;
        
        if (useFromSshConfig) {
            config.sftp = {
                ssh_config_file: document.getElementById('fromSshConfigFile').value,
                ssh_config_host: document.getElementById('fromSshConfigHost').value
            };
        } else {
            config.sftp = {
                host: document.getElementById('fromSftpHost').value,
                port: parseInt(document.getElementById('fromSftpPort').value) || 22,
                username: document.getElementById('fromSftpUsername').value,
                password: document.getElementById('fromSftpPassword').value
            };
        }
    } else { // side === 'to'
        const useToSshConfig = document.getElementById('toUseSshConfig').checked;
        
        if (useToSshConfig) {
            config.sftp = {
                ssh_config_file: document.getElementById('toSshConfigFile').value,
                ssh_config_host: document.getElementById('toSshConfigHost').value
            };
        } else {
            config.sftp = {
                host: document.getElementById('toSftpHost').value,
                port: parseInt(document.getElementById('toSftpPort').value) || 22,
                username: document.getElementById('toSftpUsername').value,
                password: document.getElementById('toSftpPassword').value
            };
        }
    }
    
    return config;
}

/**
 * Navigate to parent directory
 */
function navigateToParentDirectory() {
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
}

/**
 * Select the current directory and update the target input field
 */
function selectCurrentDirectory() {
    // Set selected path to target input
    document.getElementById(currentBrowseTarget).value = currentBrowsePath;
    
    // Close modal
    directoryBrowserModal.hide();
    
    // Call the callback if set
    if (typeof onPathSelectedCallback === 'function') {
        onPathSelectedCallback(currentBrowsePath, currentBrowseTarget);
    }
}

/**
 * Open directory browser and load initial contents
 */
function openBrowser() {
    // Reset any error messages
    document.getElementById('directoryBrowserError').style.display = 'none';
    
    // Show the modal
    directoryBrowserModal.show();
    
    // Load directory contents
    loadDirectoryContents(currentBrowsePath);
}

/**
 * Load directory contents via API
 * @param {string} path - Path to load
 */
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
    fetch('/api/v1/browse', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(responseData => {
        // Hide loading spinner
        document.getElementById('directoryLoadingSpinner').style.display = 'none';
        
        // Unwrap data envelope (supports both old and new format)
        const data = responseData.data || responseData;
        
        // Check for error in data or in error envelope
        const errorMsg = data.error || responseData.error?.message;
        if (errorMsg) {
            // Show error message
            const errorElement = document.getElementById('directoryBrowserError');
            errorElement.textContent = errorMsg;
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

/**
 * Set callback function to be called when a path is selected
 * @param {Function} callback - Callback function
 */
export function setOnPathSelectedCallback(callback) {
    onPathSelectedCallback = callback;
}
