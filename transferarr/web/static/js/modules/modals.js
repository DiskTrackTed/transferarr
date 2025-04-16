/**
 * Modal management module
 */

// Initialize Bootstrap modals and return them
export function initModals() {
    const modals = {
        clientModal: new bootstrap.Modal(document.getElementById('clientModal')),
        connectionModal: new bootstrap.Modal(document.getElementById('connectionModal')),
        deleteModal: new bootstrap.Modal(document.getElementById('deleteModal')),
        directoryBrowserModal: new bootstrap.Modal(document.getElementById('directoryBrowserModal'))
    };

    // Add proper focus management to all modals
    const modalElements = document.querySelectorAll('.modal');
    modalElements.forEach(modalElement => {
        // Before the modal starts hiding, remove focus from any elements inside
        modalElement.addEventListener('hide.bs.modal', function(event) {
            // Find all focusable elements within the modal and blur them
            const focusableElements = modalElement.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            focusableElements.forEach(el => {
                el.blur();
            });
            
            // Move focus to body as a neutral element
            document.body.focus();
            
            // Keep track of which button opened this modal to return focus to it later
            if (!modalElement.hasAttribute('data-opener-id') && event.relatedTarget) {
                modalElement.setAttribute('data-opener-id', event.relatedTarget.id);
            }
        });
        
        // After the modal is fully hidden
        modalElement.addEventListener('hidden.bs.modal', function() {
            // Try to return focus to the opener button if we know it
            const openerId = modalElement.getAttribute('data-opener-id');
            if (openerId) {
                const opener = document.getElementById(openerId);
                if (opener) {
                    setTimeout(() => opener.focus(), 0);
                }
            }
        });
        
        // Before showing the modal, store which element had focus
        modalElement.addEventListener('show.bs.modal', function(event) {
            if (event.relatedTarget) {
                modalElement.setAttribute('data-opener-id', event.relatedTarget.id);
            }
        });
    });
    
    // Fix for cancel buttons to ensure they handle focus properly
    const cancelButtons = document.querySelectorAll('[data-bs-dismiss="modal"]');
    cancelButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove focus from the button before the modal closes
            button.blur();
            document.body.focus();
        });
    });
    
    // Connection modal specific focus management
    const connectionModalElement = document.getElementById('connectionModal');
    if (connectionModalElement) {
        connectionModalElement.addEventListener('hidden.bs.modal', function() {
            // Remove focus from any elements within modal to avoid accessibility warnings
            if (document.activeElement) {
                document.activeElement.blur();
            }
            
            // Set focus back to add connection button
            const addConnectionBtn = document.getElementById('addConnectionBtn');
            if (addConnectionBtn) {
                setTimeout(() => {
                    addConnectionBtn.focus();
                }, 10);
            }
        });
    }

    return modals;
}
