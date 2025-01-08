// Global feedback message handler
window.showFeedback = function(message, type = 'success') {
    const feedbackDiv = document.getElementById('feedback-message');
    if (!feedbackDiv) return;

    feedbackDiv.textContent = message;
    feedbackDiv.className = `fixed bottom-4 right-4 p-4 rounded-lg ${
        type === 'success' 
            ? 'bg-green-500 text-white' 
            : 'bg-red-500 text-white'
    }`;
    feedbackDiv.classList.remove('hidden');

    // Hide after 3 seconds
    setTimeout(() => {
        feedbackDiv.classList.add('hidden');
    }, 3000);
};