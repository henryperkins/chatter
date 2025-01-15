// static/js/base.js

/*** Mobile Menu Handling ***/
function initializeMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileMenu = document.getElementById('mobile-menu');
    const mobileMenuBackdrop = document.getElementById('mobile-menu-backdrop');

    if (mobileMenuToggle && mobileMenu && mobileMenuBackdrop) {
        function openMenu() {
            mobileMenu.classList.remove('-translate-x-full');
            mobileMenuBackdrop.classList.remove('hidden');
            mobileMenuToggle.setAttribute('aria-expanded', 'true');
            document.body.classList.add('overflow-hidden');
        }

        function closeMenu() {
            mobileMenu.classList.add('-translate-x-full');
            mobileMenuBackdrop.classList.add('hidden');
            mobileMenuToggle.setAttribute('aria-expanded', 'false');
            document.body.classList.remove('overflow-hidden');
        }

        mobileMenuToggle.addEventListener('click', () => {
            if (mobileMenu.classList.contains('-translate-x-full')) {
                openMenu();
            } else {
                closeMenu();
            }
        });

        // Close the menu when clicking on the backdrop
        mobileMenuBackdrop.addEventListener('click', () => {
            closeMenu();
        });

        // Optional: Close the menu when pressing the Escape key
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && !mobileMenu.classList.contains('-translate-x-full')) {
                closeMenu();
            }
        });

        // Close if resized to desktop
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768) {
                closeMenu();
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    /*** Initialize Mobile Menu ***/
    initializeMobileMenu();
    
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
    initializeFontSizeAdjuster();
});

/*** Font Size Adjustment Handling ***/
function initializeFontSizeAdjuster() {
    const decreaseBtn = document.getElementById('decrease-font-size');
    const increaseBtn = document.getElementById('increase-font-size');
    const resetBtn = document.getElementById('reset-font-size');

    let currentFontSize = parseFloat(localStorage.getItem('fontSize')) || 1.0;
    applyFontSize(currentFontSize);

    if (decreaseBtn && increaseBtn && resetBtn) {
        decreaseBtn.addEventListener('click', () => {
            currentFontSize = Math.max(0.8, currentFontSize - 0.1);
            applyFontSize(currentFontSize);
        });

        increaseBtn.addEventListener('click', () => {
            currentFontSize = Math.min(1.5, currentFontSize + 0.1);
            applyFontSize(currentFontSize);
        });

        resetBtn.addEventListener('click', () => {
            currentFontSize = 1.0;
            applyFontSize(currentFontSize);
        });
    }
}

function applyFontSize(fontSize) {
    document.documentElement.style.fontSize = fontSize + 'em';
    localStorage.setItem('fontSize', fontSize);
}
