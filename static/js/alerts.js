// Alert System
const alertContainer = document.getElementById('alert-container');
const successTemplate = document.getElementById('success-alert');
const errorTemplate = document.getElementById('error-alert');

function showAlert(message, type = 'success', duration = 5000) {
    if (!alertContainer) return;

    const template = type === 'success' ? successTemplate : errorTemplate;
    if (!template) return;

    const alert = template.content.cloneNode(true);
    const messageEl = alert.querySelector('p');
    if (messageEl) {
        messageEl.textContent = message;
    }

    const alertEl = alert.firstElementChild;
    alertContainer.appendChild(alertEl);

    // Add entrance animation classes
    alertEl.classList.add('animate-in');
    alertEl.style.opacity = '0';
    alertEl.style.transform = 'translate(-50%, 1rem)';

    // Trigger animation
    setTimeout(() => {
        alertEl.style.opacity = '1';
        alertEl.style.transform = 'translate(-50%, 0)';
    }, 10);

    // Auto dismiss
    if (duration > 0) {
        setTimeout(() => {
            // Exit animation
            alertEl.style.opacity = '0';
            alertEl.style.transform = 'translate(-50%, -1rem)';
            setTimeout(() => alertEl.remove(), 300);
        }, duration);
    }

    // Click to dismiss
    const dismissBtn = alertEl.querySelector('button');
    if (dismissBtn) {
        dismissBtn.onclick = () => {
            alertEl.style.opacity = '0';
            alertEl.style.transform = 'translate(-50%, -1rem)';
            setTimeout(() => alertEl.remove(), 300);
        };
    }
}

// Export functions to global scope
window.showAlert = showAlert;
