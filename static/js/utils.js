/**
 * Retrieve the CSRF token from a meta tag named "csrf-token".
 */
function getCSRFToken() {
    const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") || "" : "";
    console.debug("Retrieved CSRF token from meta tag:", csrfToken);
    return csrfToken;
}

/**
 * Fetch data from a URL with a CSRF token in headers (or FormData).
 * Rejects if response is not OK or not JSON.
 */
async function fetchWithCSRF(url, options = {}) {
    const csrfToken = getCSRFToken();
    const headers = {
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers
    };

    // Include CSRF token
    if (!(options.body instanceof FormData)) {
        headers['X-CSRFToken'] = csrfToken;
    } else {
        // If body is FormData, append the token instead
        options.body.append('csrf_token', csrfToken);
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers,
            credentials: 'same-origin'
        });
        const contentType = response.headers.get('content-type');
        let data;

        if (contentType && contentType.includes('application/json')) {
            data = await response.json();
        } else {
            const text = await response.text();
            throw new Error(`Invalid response from server: ${text}`);
        }

        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        return data;
    } catch (error) {
        console.error('Error in fetchWithCSRF:', error);
        throw error;
    }
}

/**
 * Display a feedback message (success, error, etc.) at the top of the page.
 */
function showFeedback(message, type = "success", options = {}) {
    const { duration = 5000, position = "top" } = options;
    let feedbackMessage = document.getElementById("feedback-message");

    // Create an element if one doesn't exist
    if (!feedbackMessage) {
        feedbackMessage = document.createElement("div");
        feedbackMessage.id = "feedback-message";
        feedbackMessage.setAttribute("role", "alert");
        feedbackMessage.setAttribute("aria-live", "assertive");
        document.body.appendChild(feedbackMessage);
    }

    // Position classes
    const positionClasses = {
        top: "top-4 left-1/2 transform -translate-x-1/2",
        bottom: "bottom-4 left-1/2 transform -translate-x-1/2",
        "top-right": "top-4 right-4",
        "bottom-right": "bottom-4 right-4"
    };

    // Color classes
    const colorClasses = {
        success: "bg-green-500 text-white",
        error: "bg-red-500 text-white",
        warning: "bg-yellow-500 text-black",
        info: "bg-blue-500 text-white"
    };

    feedbackMessage.innerHTML = `
        <div class="flex items-center justify-between p-4 rounded-lg shadow-lg max-w-md w-full text-center ${
            colorClasses[type] || colorClasses.info
        }">
            <span>${message}</span>
            <button id="feedback-close" class="ml-4 text-lg" aria-label="Close">&times;</button>
        </div>
    `;
    feedbackMessage.className = `fixed z-50 ${positionClasses[position] || positionClasses.top}`;
    feedbackMessage.classList.remove("hidden");

    // Handle manual close
    const closeButton = feedbackMessage.querySelector("#feedback-close");
    if (closeButton) {
        closeButton.addEventListener("click", () => {
            feedbackMessage.classList.add("hidden");
        });
    }

    // Auto-hide if not an error
    if (type !== "error" && duration > 0) {
        setTimeout(() => {
            feedbackMessage.classList.add("hidden");
        }, duration);
    }
}

/**
 * Convert a FormData object into a plain JS object.
 */
function formDataToObject(formData) {
    const object = {};
    for (const [key, value] of formData.entries()) {
        object[key] = value;
    }
    return object;
}

/**
 * Format a date string like "2025-01-01" into a more readable form.
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
    });
}

/**
 * Debounce a function to limit its rate of execution.
 */
function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

/**
 * Throttle a function to limit its frequency of execution.
 */
function throttle(func, limit) {
    let inThrottle;
    return function (...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => (inThrottle = false), limit);
        }
    };
}

/**
 * Show a loading spinner on a button element.
 */
function showLoading(element, options = {}) {
    const { text = "Loading...", size = "1.5rem" } = options;
    element.disabled = true;
    element.innerHTML = `
        <div class="flex items-center justify-center">
            <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-white"
                 style="width: ${size}; height: ${size}"></div>
            ${text ? `<span class="ml-2">${text}</span>` : ''}
        </div>
    `;
}

/**
 * Hide a loading spinner, restoring the original content.
 */
function hideLoading(element, originalContent) {
    element.disabled = false;
    element.innerHTML = originalContent;
}

/**
 * Wrap a callback with loading spinner logic.
 */
function withLoading(element, callback, options = {}) {
    const originalContent = element.innerHTML;
    showLoading(element, options);
    return Promise.resolve(callback())
        .finally(() => hideLoading(element, originalContent));
}

// Attach functions to window.utils so they're globally available
window.utils = {
    getCSRFToken,
    fetchWithCSRF,
    showFeedback,
    formDataToObject,
    formatDate,
    debounce,
    throttle,
    showLoading,
    hideLoading,
    withLoading
};
