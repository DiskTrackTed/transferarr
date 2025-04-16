/**
 * Notification System for Transferarr
 */
const TransferarrNotifications = (function() {
    // Container for all notifications
    let container = null;
    let notificationCount = 0;
    let dismissAllButton = null;
    let activeNotifications = 0;
    
    // Initialize the notification container and dismiss all button
    function initialize() {
        if (!container) {
            container = document.createElement('div');
            container.className = 'notification-container';
            document.body.appendChild(container);
        }
        
        if (!dismissAllButton) {
            dismissAllButton = document.createElement('button');
            dismissAllButton.className = 'dismiss-all-button';
            dismissAllButton.innerHTML = '<i class="fas fa-times"></i> Dismiss All';
            dismissAllButton.addEventListener('click', dismissAll);
            document.body.appendChild(dismissAllButton);
        }
    }
    
    // Show or hide the dismiss all button based on active notifications
    function updateDismissAllButton() {
        if (!dismissAllButton) return;
        
        if (activeNotifications > 0 && !dismissAllButton.classList.contains('visible')) {
            const refWidth = container.offsetWidth + 30;
            dismissAllButton.style.right = `${refWidth}px`;

            dismissAllButton.classList.add('appearing');
            dismissAllButton.classList.add('visible');
            
            // Remove the animation class after it completes
            setTimeout(() => {
                dismissAllButton.classList.remove('appearing');
            }, 300);
        } else if (activeNotifications > 0 && dismissAllButton.classList.contains('visible')){
            const refWidth = container.offsetWidth + 30;
            
            dismissAllButton.style.right = `${refWidth}px`;
        } else if (activeNotifications === 0 && dismissAllButton.classList.contains('visible')) {
            dismissAllButton.classList.add('disappearing');
            
            // Remove the button after animation completes
            setTimeout(() => {
                dismissAllButton.classList.remove('visible');
                dismissAllButton.classList.remove('disappearing');
            }, 300);
        }
    }
    
    // Create a new notification
    function create(options) {
        initialize();
        
        const id = `notification-${Date.now()}-${notificationCount++}`;
        const type = options.type || 'info';
        
        // Create the notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.id = id;
        
        // Icon based on notification type
        let iconClass = '';
        switch (type) {
            case 'success':
                iconClass = 'fas fa-check-circle';
                break;
            case 'error':
                iconClass = 'fas fa-times-circle';
                break;
            case 'warning':
                iconClass = 'fas fa-exclamation-triangle';
                break;
            case 'info':
                iconClass = 'fas fa-info-circle';
            default:
                iconClass = 'fas fa-info-circle';
        }
        
        // Build notification HTML
        notification.innerHTML = `
            <div class="notification-icon">
                <i class="${iconClass}"></i>
            </div>
            <div class="notification-content">
                <h4 class="notification-title">${options.title || 'Notification'}</h4>
                <p class="notification-message">${options.message || ''}</p>
            </div>
            <button class="notification-close" aria-label="Close">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add to container
        container.appendChild(notification);

        container.scrollTo({
            top: notification.offsetTop - container.offsetTop,
            // behavior: 'smooth'
        })
        
        // container.scrollTo({
        //     top: 0,
        //     behavior: 'auto'
        // });
        
        // Add event listener for close button
        const closeButton = notification.querySelector('.notification-close');
        closeButton.addEventListener('click', () => {
            dismiss(id);
        });
        
        // Trigger animation to show notification
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
        
        // Increment active notifications count and update button
        activeNotifications++;
        updateDismissAllButton();
        
        // Return the ID so it can be dismissed programmatically
        return id;
    }
    
    // Dismiss a notification
    function dismiss(id) {
        const notification = document.getElementById(id);
        if (notification) {
            notification.classList.add('removing');
            notification.classList.remove('show');
            
            // Remove from DOM after animation completes
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                    
                    // Decrement active notifications count and update button
                    activeNotifications--;
                    updateDismissAllButton();
                }
            }, 300); // Match animation duration
        }
    }
    
    // Dismiss all notifications
    function dismissAll() {
        const notifications = document.querySelectorAll('.notification');
        if (notifications.length === 0) return;
        
        notifications.forEach(notification => {
            dismiss(notification.id);
        });
    }
    
    // Public API
    return {
        /**
         * Show a success notification
         * @param {string} title - The notification title
         * @param {string} message - The notification message
         * @returns {string} Notification ID
         */
        success: function(title, message) {
            return create({
                type: 'success',
                title: title,
                message: message
            });
        },
        
        /**
         * Show an error notification
         * @param {string} title - The notification title
         * @param {string} message - The notification message
         * @returns {string} Notification ID
         */
        error: function(title, message) {
            return create({
                type: 'error',
                title: title,
                message: message
            });
        },
        
        /**
         * Show a warning notification
         * @param {string} title - The notification title
         * @param {string} message - The notification message
         * @returns {string} Notification ID
         */
        warning: function(title, message) {
            return create({
                type: 'warning',
                title: title,
                message: message
            });
        },

        /**
         * Show an info notification
         * @param {string} title - The notification title
         * @param {string} message - The notification message
         * @returns {string} Notification ID
         */
        info: function(title, message) {
            return create({
                type: 'info',
                title: title,
                message: message
            });
        },
        
        /**
         * Dismiss a specific notification
         * @param {string} id - The notification ID
         */
        dismiss: dismiss,
        
        /**
         * Dismiss all notifications
         */
        dismissAll: dismissAll
    };
})();
