/**
 * Provides base JavaScript functionality for handling CSRF tokens, feedback messages, and mobile menu interactions.
 * This script manages CSRF token injection into Axios and fetch requests, displays feedback messages to the user, and implements a mobile menu toggle.
 * @module base
 */

/**
 * Retrieves the CSRF token from a meta tag.
 * @function getCSRFToken
 * @returns {string} The CSRF token or an empty string if not found.
 */
function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

/**
 * Sets the default CSRF token header for Axios requests.
 * @see {@link getCSRFToken}
 */
axios.defaults.headers.common['X-CSRFToken'] = getCSRFToken();

/**
 * Overrides the native fetch function to include the CSRF token in all requests.
 * @function fetch
 * @param {string | URL | Request} url - The URL or Request object.
 * @param {object} [options] - The fetch options.
 * @param {object} [options.headers] - The request headers.
 * @returns {Promise<Response>} The fetch promise.
 * @see {@link getCSRFToken}
 */
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

/**
 * Displays a feedback message to the user.
 * @function showFeedback
 * @param {string} message - The feedback message to display.
 * @param {string} [type='info'] - The type of message ('info' or 'error').
 */
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

/**
 * Initializes the mobile menu toggle functionality.
 * @function initializeMobileMenu
 * @listens DOMContentLoaded
 */
document.addEventListener('DOMContentLoaded', () => {
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const offCanvasMenu = document.getElementById('off-canvas-menu');
    const overlay = document.getElementById('overlay');
    const closeButton = document.getElementById('off-canvas-close');

    /**
     * Toggles the visibility of the mobile menu and overlay.
     * @function toggleMenu
     */
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
