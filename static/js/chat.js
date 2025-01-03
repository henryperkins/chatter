export { showFeedback, getCSRFToken };
/**
 * Display feedback messages to the user.
 * @param {string} message - The message to display.
 * @param {string} type - The type of message ('success' or 'error').
 */
function showFeedback(message, type) {
    const feedbackDiv = document.getElementById('feedback-message');
    if (!feedbackDiv) return; // Ensure the feedback div exists
    feedbackDiv.textContent = message;
    feedbackDiv.className = `fixed bottom-4 right-4 p-4 rounded-lg ${type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`;
    feedbackDiv.classList.remove('hidden');
    setTimeout(() => feedbackDiv.classList.add('hidden'), 5000);
}

/**
 * Retrieve the CSRF token from the meta tag.
 * @returns {string} - The CSRF token.
 */
function getCSRFToken() {
    const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    return csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : '';
}

// Export functions for use in other scripts
export { showFeedback, getCSRFToken };
