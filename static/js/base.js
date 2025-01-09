// static/js/base.js

// Function to get CSRF token from meta tag
function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

// Configure Axios to include CSRF token in all requests
axios.defaults.headers.common['X-CSRFToken'] = getCSRFToken();

// Add CSRF token to all fetch requests
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    if (!options.headers) {
        options.headers = {};
    }
    
    // Add CSRF token if not already present
    if (!options.headers['X-CSRFToken']) {
        options.headers['X-CSRFToken'] = getCSRFToken();
    }
    
    return originalFetch(url, options);
};

// Handle feedback messages
function showFeedback(message, type = 'info') {
    const feedbackDiv = document.getElementById('feedback-message');
    if (feedbackDiv) {
        feedbackDiv.textContent = message;
        feedbackDiv.className = `fixed top-4 left-1/2 transform -translate-x-1/2 p-4 rounded-lg shadow-lg z-50 max-w-md w-full text-center ${
            type === 'error' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
        }`;
        feedbackDiv.classList.remove('hidden');
        
        // Hide the message after 5 seconds
        setTimeout(() => {
            feedbackDiv.classList.add('hidden');
        }, 5000);
    }
}

// Initialize mobile menu functionality
document.addEventListener('DOMContentLoaded', () => {
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const offCanvasMenu = document.getElementById('off-canvas-menu');
    const overlay = document.getElementById('overlay');
    const closeButton = document.getElementById('off-canvas-close');

    function toggleMenu() {
        offCanvasMenu.classList.toggle('hidden');
        overlay.classList.toggle('hidden');
        document.body.classList.toggle('overflow-hidden');
    }

    if (sidebarToggle && offCanvasMenu && overlay && closeButton) {
        sidebarToggle.addEventListener('click', toggleMenu);
        closeButton.addEventListener('click', toggleMenu);
        overlay.addEventListener('click', toggleMenu);
    }
});