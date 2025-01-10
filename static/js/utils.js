// static/js/utils.js

/**
 * Retrieves the CSRF token from a meta tag.
 * @function getCSRFToken
 * @returns {string} The CSRF token or an empty string if not found.
 */
// CSRF Token Management
let csrfToken = null;

function getCSRFToken() {
  if (!csrfToken) {
    const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
    csrfToken = csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") : "";
  }
  return csrfToken;
}

document.addEventListener("DOMContentLoaded", () => {
  const token = getCSRFToken();
  if (token) {
    axios.defaults.headers.common["X-CSRFToken"] = token;
    const originalFetch = window.fetch;
    window.fetch = (url, options = {}) => {
      if (!options.headers) options.headers = {};
      if (!options.headers["X-CSRFToken"]) {
        options.headers["X-CSRFToken"] = token;
      }
      if (!options.credentials) {
        options.credentials = 'same-origin';
      }
    };
    return originalFetch(url, options);
  }
});
      return originalFetch(url, options);
    };
  }
});

/**
 * Shows a feedback message to the user.
 * @function showFeedback
 * @param {string} message - The feedback message to display.
 * @param {string} [type='success'] - The type of message ('success', 'error', 'warning', or 'info').
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
 * @returns {Object} A plain JavaScript object with key-value pairs.
 */
function formDataToObject(formData) {
  const object = {};
  for (const [key, value] of formData.entries()) {
    object[key] = value;
  }
  return object;
}

/**
 * Validates an email address.
 * @function validateEmail
 * @param {string} email - The email address to validate.
 * @returns {boolean} True if the email is valid, false otherwise.
 */
function validateEmail(email) {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return regex.test(email);
}

/**
 * Validates a password (minimum 8 characters, at least one letter and one number).
 * @function validatePassword
 * @param {string} password - The password to validate.
 * @returns {boolean} True if the password is valid, false otherwise.
 */
function validatePassword(password) {
  const regex = /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$/;
  return regex.test(password);
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
 * @param {Function} func - The function to debounce.
 * @param {number} wait - The wait time in milliseconds.
 * @returns {Function} The debounced function.
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
 * @param {Function} func - The function to throttle.
 * @param {number} limit - The time limit in milliseconds.
 * @returns {Function} The throttled function.
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

// Loading State Management
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

function hideLoading(element, originalContent) {
  element.disabled = false;
  element.innerHTML = originalContent;
}

function withLoading(element, callback, options = {}) {
  const originalContent = element.innerHTML;
  showLoading(element, options);
  return Promise.resolve(callback())
    .finally(() => hideLoading(element, originalContent));
}
