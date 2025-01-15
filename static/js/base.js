// static/js/base.js

document.addEventListener('DOMContentLoaded', function() {
    /*** Flash Message Handling ***/
    const flashMessages = document.querySelectorAll('[role="alert"]');
    flashMessages.forEach(message => {
        const dismissButton = message.querySelector('button');
        let timeoutId;

        const removeMessage = () => {
            if (message.style) {
                message.style.opacity = '0';
                message.style.transform = 'translateY(-10px)';
            }
            setTimeout(() => message.remove(), 300);
        };

        // Auto-dismiss after 5 seconds
        timeoutId = setTimeout(removeMessage, 5000);

        // Cancel auto-dismiss on hover
        message.addEventListener('mouseenter', () => clearTimeout(timeoutId));
        message.addEventListener('mouseleave', () => {
            timeoutId = setTimeout(removeMessage, 5000);
        });

        // Manual dismiss
        if (dismissButton) {
            dismissButton.addEventListener('click', () => {
                clearTimeout(timeoutId);
                removeMessage();
            });
        }
    });

    /*** Initialize Tooltips ***/
    function initializeTooltips() {
        const tooltipElements = document.querySelectorAll('[data-tooltip]');
        tooltipElements.forEach(element => {
            const tooltipText = element.getAttribute('data-tooltip');
            if (tooltipText) {
                const tooltip = document.createElement('div');
                tooltip.className = 'tooltip hidden bg-black text-white text-sm px-2 py-1 rounded absolute z-50';
                tooltip.textContent = tooltipText;
                element.appendChild(tooltip);

                element.addEventListener('mouseenter', () => {
                    tooltip.classList.remove('hidden');
                    const rect = element.getBoundingClientRect();
                    if (tooltip.style) {
                        tooltip.style.top = `${rect.bottom + window.scrollY}px`;
                        tooltip.style.left = `${rect.left + window.scrollX}px`;
                    }
                });

                element.addEventListener('mouseleave', () => {
                    tooltip.classList.add('hidden');
                });
            }
        });
    }

    /*** Initialize Modals ***/
    function initializeModals() {
        const modalTriggers = document.querySelectorAll('[data-modal-target]');
        modalTriggers.forEach(trigger => {
            const modalId = trigger.getAttribute('data-modal-target');
            if (!modalId) return;

            const modal = document.getElementById(modalId);
            if (!modal) return;

            // Open modal
            trigger.addEventListener('click', () => {
                modal.classList.remove('hidden');
                document.body.classList.add('overflow-hidden');
            });

            // Close modal
            const closeButtons = modal.querySelectorAll('[data-modal-close]');
            closeButtons.forEach(button => {
                button.addEventListener('click', () => {
                    modal.classList.add('hidden');
                    document.body.classList.remove('overflow-hidden');
                });
            });

            // Click outside modal to close
            modal.addEventListener('click', event => {
                if (event.target === modal) {
                    modal.classList.add('hidden');
                    document.body.classList.remove('overflow-hidden');
                }
            });

            // Close on ESC
            document.addEventListener('keydown', event => {
                if (event.key === 'Escape' && !modal.classList.contains('hidden')) {
                    modal.classList.add('hidden');
                    document.body.classList.remove('overflow-hidden');
                }
            });
        });
    }

    // Call initialization functions
    initializeTooltips();
    initializeModals();
});
