(function() {
    console.log("Utils.js initialized");

    /**
     * Retrieves the CSRF token from a meta tag in the HTML document.
     * @returns {string} The CSRF token value, or an empty string if no token is found.
     * @description Searches the document for a meta tag with the name "csrf-token" and extracts its content.
     * Logs the retrieved token to the console for debugging purposes.
     */
    function getCSRFToken() {
        const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") || "" : "";
        console.debug("Retrieved CSRF token from meta tag:", csrfToken);
        return csrfToken;
    }

    // Set default CSRF token for axios if available
    if (typeof axios !== 'undefined') {
        axios.defaults.headers.common["X-CSRFToken"] = getCSRFToken();
    }

    /**
     * Fetches data from a URL with CSRF token included in the headers.
     * 
     * @param {string} url - The URL to fetch data from.
     * @param {object} [options={}] - Additional fetch options for the request.
     * @returns {Promise<object>} The JSON response data from the server.
     * @throws {Error} If the response is not successful or cannot be parsed as JSON.
     * @description Performs a fetch request with automatic CSRF token handling. 
     * Supports both JSON payloads and FormData, dynamically including the CSRF token 
     * in request headers or form data. Validates response content type and handles 
     * potential server errors with detailed error logging.
     * 
     * @example
     * // Fetch user data
     * const userData = await fetchWithCSRF('/api/user', {
     *   method: 'GET'
     * });
     * 
     * @example
     * // Post form data with CSRF token
     * const formData = new FormData();
     * formData.append('username', 'johndoe');
     * const result = await fetchWithCSRF('/api/update', {
     *   method: 'POST',
     *   body: formData
     * });
     */
    async function fetchWithCSRF(url, options = {}) {
        const csrfToken = getCSRFToken();
        const headers = {
            'X-Requested-With': 'XMLHttpRequest',
            ...options.headers
        };

        // Include CSRF token in headers if possible
        if (!(options.body instanceof FormData)) {
            headers['X-CSRFToken'] = csrfToken;
        } else {
            // If body is FormData, append CSRF token to it
            options.body.append('csrf_token', csrfToken);
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
     * Shows a loading spinner on an element, disabling the element and replacing its content with a spinner.
     * @param {HTMLElement} element - The DOM element to display the loading spinner on.
     * @param {object} [options={}] - Optional configuration for the loading spinner.
     * @param {string} [options.text="Loading..."] - Custom text to display alongside the spinner.
     * @param {string} [options.size="1.5rem"] - Size of the spinner, specified as a CSS dimension.
     */
    function showLoading(element, options = {}) {
        const { text = "Loading...", size = "1.5rem" } = options;
        element.disabled = true;
        element.innerHTML = `
            <div class="flex items-center justify-center">
                <div class="animate-spin rounded-full border-b-2 border-white"
                     style="width: ${size}; height: ${size}"></div>
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

    // Export everything that might be needed by the rest of the app
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
