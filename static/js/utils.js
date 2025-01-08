// static/js/utils.js

// Get CSRF Token from meta tag
function getCSRFToken() {
    const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
    return csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") : "";
}

// Show user feedback messages
function showFeedback(message, type = "success") {
    const feedbackMessage = document.getElementById("feedback-message");
    feedbackMessage.innerHTML = `
        <div class="flex items-center justify-between">
            <span>${message}</span>
            ${(type === "error" || type === "warning") ? '<button id="feedback-close" class="ml-4 text-lg" aria-label="Close">&times;</button>' : ''}
        </div>
    `;
    feedbackMessage.setAttribute('role', 'alert');
    feedbackMessage.setAttribute('aria-live', 'assertive');
    feedbackMessage.className = `fixed top-4 left-1/2 transform -translate-x-1/2 p-4 rounded-md shadow-lg z-50 max-w-md w-full text-center ${
        type === "success" ? "bg-green-500 text-white" :
        type === "error" ? "bg-red-500 text-white" :
        type === "warning" ? "bg-yellow-500 text-black" :
        "bg-blue-500 text-white"
    }`;
    feedbackMessage.classList.remove("hidden");

    if (type === "success") {
        setTimeout(() => feedbackMessage.classList.add("hidden"), 5000);
    } else {
        const closeButton = document.getElementById("feedback-close");
        if (closeButton) {
            closeButton.addEventListener("click", () => {
                feedbackMessage.classList.add("hidden");
            });
        }
    }
}