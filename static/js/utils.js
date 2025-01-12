(function() {
    console.log("Utils.js initialized");

    /**
     * Retrieves the CSRF token from a meta tag.
     * @function getCSRFToken
     * @returns {string} The CSRF token or an empty string if not found.
     */
    function getCSRFToken() {
        const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") || "" : "";
        console.debug("Retrieved CSRF token from meta tag:", csrfToken);  // Add this line for debugging
        return csrfToken;
    }

    // Set default CSRF token for axios if available
    if (typeof axios !== 'undefined') {
        axios.defaults.headers.common["X-CSRFToken"] = getCSRFToken();
    }

    /**
     * Fetches data from a URL with CSRF token included in the headers.
     * Handles non-JSON responses gracefully by checking the content type.
     * @function fetchWithCSRF
     * @param {string} url - The URL to fetch data from.
     * @param {object} [options={}] - Additional fetch options.
     * @returns {Promise<object>} The response data as a JSON object.
     * @throws {Error} If the response is not OK or not JSON.
     */
    async function fetchWithCSRF(url, options = {}) {
        const csrfToken = getCSRFToken();
        const headers = {
            'X-Requested-With': 'XMLHttpRequest',
            ...options.headers
        };

        // Include CSRF token in headers only if it's not a FormData request
        if (!(options.body instanceof FormData)) {
            headers['X-CSRFToken'] = csrfToken;
        }

        try {
            const response = await fetch(url, { ...options, headers });

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
     * Shows a feedback message to the user.
     * @function showFeedback
     * @param {string} message - The feedback message to display.
     * @param {('success'|'error'|'warning'|'info')} [type='success'] - The type of message.
     * @param {object} [options={}] - Additional options for the feedback.
     */
    function showFeedback(message, type = "success", options = {}) {
        const { duration = 5000, position = "top" } = options;
        let feedbackMessage = document.getElementById("feedback-message");

        // Create feedback element if it doesn't exist
        if (!feedbackMessage) {
            feedbackMessage = document.createElement("div");
            feedbackMessage.id = "feedback-message";
            feedbackMessage.setAttribute("role", "alert");
            feedbackMessage.setAttribute("aria-live", "assertive");
            document.body.appendChild(feedbackMessage);
        }

        // Set position classes
        const positionClasses = {
            top: "top-4 left-1/2 transform -translate-x-1/2",
            bottom: "bottom-4 left-1/2 transform -translate-x-1/2",
            "top-right": "top-4 right-4",
            "bottom-right": "bottom-4 right-4"
        };

        // Set color classes
        const colorClasses = {
            success: "bg-green-500 text-white",
            error: "bg-red-500 text-white",
            warning: "bg-yellow-500 text-black",
            info: "bg-blue-500 text-white"
        };

        // Build message content
        feedbackMessage.innerHTML = `
            <div class="flex items-center justify-between p-4 rounded-lg shadow-lg max-w-md w-full text-center ${
                colorClasses[type] || colorClasses.info
            }">
                <span>${message}</span>
                <button id="feedback-close" class="ml-4 text-lg" aria-label="Close">&times;</button>
            </div>
        `;

        // Apply position and visibility
        feedbackMessage.className = `fixed z-50 ${positionClasses[position] || positionClasses.top}`;
        feedbackMessage.classList.remove("hidden");

        // Handle close button
        const closeButton = feedbackMessage.querySelector("#feedback-close");
        if (closeButton) {
            closeButton.addEventListener("click", () => {
                feedbackMessage.classList.add("hidden");
            });
        }

        // Auto-hide for non-error messages
        if (type !== "error" && duration > 0) {
            setTimeout(() => {
                feedbackMessage.classList.add("hidden");
            }, duration);
        }
    }

    /**
     * Converts a FormData object to a plain JavaScript object.
     * @function formDataToObject
     * @param {FormData} formData - The FormData object to convert.
     * @returns {object} A plain JavaScript object with key-value pairs.
     */
    function formDataToObject(formData) {
        const object = {};
        for (const [key, value] of formData.entries()) {
            object[key] = value;
        }
        return object;
    }

    /**
     * Formats a date string into a human-readable format.
     * @function formatDate
     * @param {string} dateString - The date string to format.
     * @returns {string} The formatted date (e.g., "January 1, 2023").
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
     * Debounces a function to limit its execution rate.
     * @function debounce
     * @param {function} func - The function to debounce.
     * @param {number} wait - The wait time in milliseconds.
     * @returns {function} The debounced function.
     */
    function debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    /**
     * Throttles a function to limit its execution rate.
     * @function throttle
     * @param {function} func - The function to throttle.
     * @param {number} limit - The time limit in milliseconds.
     * @returns {function} The throttled function.
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
     * Shows a loading spinner on an element.
     * @function showLoading
     * @param {HTMLElement} element - The element to show the loading spinner on.
     * @param {object} [options={}] - Additional options for the spinner.
     */
    function showLoading(element, options = {}) {
        const { text = "Loading...", size = "1.5rem" } = options;
        element.disabled = true;
        element.innerHTML = `
            <div class="flex items-center justify-center">
                <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-white" style="width: ${size}; height: ${size}"></div>
                ${text ? `<span class="ml-2">${text}</span>` : ''}
            </div>
        `;
    }

    /**
     * Hides the loading spinner on an element.
     * @function hideLoading
     * @param {HTMLElement} element - The element to hide the loading spinner on.
     * @param {string} originalContent - The original content of the element.
     */
    function hideLoading(element, originalContent) {
        element.disabled = false;
        element.innerHTML = originalContent;
    }

    /**
     * Wraps a function with a loading spinner.
     * @function withLoading
     * @param {HTMLElement} element - The element to show the loading spinner on.
     * @param {function} callback - The function to execute while showing the spinner.
     * @param {object} [options={}] - Additional options for the spinner.
     * @returns {Promise} The result of the callback function.
     */
    function withLoading(element, callback, options = {}) {
        const originalContent = element.innerHTML;
        showLoading(element, options);
        return Promise.resolve(callback())
            .finally(() => hideLoading(element, originalContent));
    }

    // Export functions that need to be globally accessible
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
})();
