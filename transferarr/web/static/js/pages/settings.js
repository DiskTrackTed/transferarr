/**
 * Settings page main entry point
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Settings.js loaded');
    
    // Make sure Bootstrap is loaded
    if (typeof bootstrap === 'undefined') {
        console.error('Bootstrap is not loaded');
        alert('Error: Bootstrap is not loaded. Please refresh the page.');
        return;
    }

    let connectionsLoaded = false;
    
    // Import required modules
    import('../modules/modals.js').then(modalsModule => {
        // Initialize all modals
        const modals = modalsModule.initModals();
        
        // Initialize password fields
        initPasswordFields();

        // Load clients module
        import('../modules/clients.js').then(clientsModule => {
            // Initialize clients module
            clientsModule.initClients(modals);
            
            // Load client data
            clientsModule.loadClients();
        }).catch(error => {
            console.error('Error loading clients module:', error);
            alert('Failed to load clients module: ' + error.message);
        });
        
        // Load connections module - this will also initialize the directory browser
        import('../modules/connections.js').then(connectionsModule => {
            // Initialize connections module
            connectionsModule.initConnections(modals);
            
            // Only load connections if the connections tab is active on page load
            if ((window.location.hash === '#connections' || 
                document.querySelector('#settings-tabs .client-tab[data-tab="connections"]').classList.contains('active'))) {
                connectionsModule.loadConnections();
                connectionsLoaded = true;
            }
            
            // Store module for later use
            window.connectionsModule = connectionsModule;
        }).catch(error => {
            console.error('Error loading connections module:', error);
            alert('Failed to load connections module: ' + error.message);
        });

        // Initialize tab switching
        initTabs();
        
    }).catch(error => {
        console.error('Error loading modals module:', error);
        alert('Failed to load modals module: ' + error.message);
    });
    
    // Initialize tab switching
    function initTabs() {
        const tabElements = document.querySelectorAll('#settings-tabs .client-tab');
        if (tabElements.length > 0) {
            tabElements.forEach(tab => {
                tab.addEventListener('click', function() {
                    // Remove active class from all tabs and content
                    document.querySelectorAll('#settings-tabs .client-tab').forEach(t => 
                        t.classList.remove('active'));
                    document.querySelectorAll('.client-tab-content').forEach(c => 
                        c.classList.remove('active'));
                    
                    // Add active class to clicked tab and corresponding content
                    this.classList.add('active');
                    const tabId = this.getAttribute('data-tab');
                    document.getElementById(`${tabId}-tab-content`).classList.add('active');
                    
                    // Save active tab in URL hash
                    window.location.hash = tabId;

                    // Load data for the selected tab if needed
                    if (tabId === 'connections' && !connectionsLoaded) {
                        if (window.connectionsModule) {
                            window.connectionsModule.loadConnections();
                            connectionsLoaded = true;
                        }
                    }
                });
            });
            
            // Check URL hash to restore active tab on page load
            const hash = window.location.hash.substring(1);
            if (hash) {
                const tabToActivate = document.querySelector(`#settings-tabs .client-tab[data-tab="${hash}"]`);
                if (tabToActivate) {
                    tabToActivate.click();
                }
            }
        }
    }
    
    // Initialize password field visibility toggles
    function initPasswordFields() {
        const toggleButtons = document.querySelectorAll('.toggle-visibility');
        toggleButtons.forEach(button => {
            button.addEventListener('click', function() {
                const passwordField = this.parentElement.querySelector('.obfuscated-field');
                const icon = this.querySelector('i');
                
                if (passwordField.classList.contains('visible')) {
                    // Switch back to obfuscated mode
                    passwordField.classList.remove('visible');
                    passwordField.style.webkitTextSecurity = 'disc';
                    passwordField.style.textSecurity = 'disc';
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                } else {
                    // Switch to visible mode
                    passwordField.classList.add('visible');
                    passwordField.style.webkitTextSecurity = 'none';
                    passwordField.style.textSecurity = 'none';
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                }
            });
        });
    }
});
