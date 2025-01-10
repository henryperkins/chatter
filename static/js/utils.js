// static/js/utils.js

/**
 * Retrieves the CSRF token from a meta tag.
 * @function getCSRFToken
 * @returns {string} The CSRF token or an empty string if not found.
 */
function getCSRFToken() {
  const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
  return csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") : "";
}

/**
 * Shows a feedback message to the user.
 * @function showFeedback
 * @param {string} message - The feedback message to display.
 * @param {string} [type='success'] - The type of message ('success', 'error', 'warning', or 'info').
 */
function showFeedback(message, type = "success") {
  const feedbackMessage = document.getElementById("feedback-message");
  if (!feedbackMessage) {
    console.warn("Feedback message element not found.");
    return;
  }

  // Set the message content and styling based on the type
  feedbackMessage.innerHTML = `
    <div class="flex items-center justify-between">
      <span>${message}</span>
      ${
        type === "error" || type === "warning"
          ? '<button id="feedback-close" class="ml-4 text-lg" aria-label="Close">&times;</button>'
          : ""
      }
    </div>
  `;

  // Set accessibility attributes
  feedbackMessage.setAttribute("role", "alert");
  feedbackMessage.setAttribute("aria-live", "assertive");

  // Apply styling based on the type
  feedbackMessage.className = `
    fixed top-4 left-1/2 transform -translate-x-1/2 p-4 rounded-md shadow-lg z-50 max-w-md w-full text-center
    ${
      type === "success"
        ? "bg-green-500 text-white"
        : type === "error"
        ? "bg-red-500 text-white"
        : type === "warning"
        ? "bg-yellow-500 text-black"
        : "bg-blue-500 text-white"
    }
  `;

  // Show the feedback message
  feedbackMessage.classList.remove("hidden");

  // Automatically hide the message after 5 seconds for success/feedback
  if (type === "success" || type === "info") {
    setTimeout(() => {
      feedbackMessage.classList.add("hidden");
    }, 5000);
  } else if (type === "error" || type === "warning") {
    // Add a close button for errors/warnings
    const closeButton = document.getElementById("feedback-close");
    if (closeButton) {
      closeButton.addEventListener("click", () => {
        feedbackMessage.classList.add("hidden");
      });
    }
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
