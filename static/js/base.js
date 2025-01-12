(function() {
    // Use showFeedback utility from utils.js
    const { showFeedback } = window.utils;

    // Initialize mobile menu toggle
    function initializeMobileMenu() {
        const mobileMenu = document.getElementById('mobile-menu');
        const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        const mobileMenuClose = document.getElementById('mobile-menu-close');
        const sidebar = document.getElementById('sidebar');

        function toggleMobileMenu() {
            mobileMenu.classList.toggle('-translate-x-full');
        }

        function toggleSidebar() {
            sidebar.classList.toggle('-translate-x-full');
        }

        if (mobileMenuToggle) {
            mobileMenuToggle.addEventListener('click', toggleSidebar);
        }

        if (mobileMenuClose) {
            mobileMenuClose.addEventListener('click', toggleMobileMenu);
        }

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!mobileMenu.contains(e.target) && !mobileMenuToggle.contains(e.target)) {
                mobileMenu.classList.add('-translate-x-full');
            }
            if (!sidebar.contains(e.target) && !mobileMenuToggle.contains(e.target)) {
                sidebar.classList.add('-translate-x-full');
            }
        });
    }

    // Initialize tooltips
    function initializeTooltips() {
        const tooltipElements = document.querySelectorAll('[data-tooltip]');
        tooltipElements.forEach(element => {
            const tooltipText = element.getAttribute('data-tooltip');
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip hidden bg-black text-white text-sm px-2 py-1 rounded absolute z-50';
            tooltip.textContent = tooltipText;
            element.appendChild(tooltip);

            element.addEventListener('mouseenter', () => {
                tooltip.classList.remove('hidden');
                const rect = element.getBoundingClientRect();
                tooltip.style.top = `${rect.bottom + window.scrollY}px`;
                tooltip.style.left = `${rect.left + window.scrollX}px`;
            });

            element.addEventListener('mouseleave', () => {
                tooltip.classList.add('hidden');
            });
        });
    }

    // Initialize dropdowns
    function initializeDropdowns() {
        const dropdownElements = document.querySelectorAll('[data-dropdown]');
        dropdownElements.forEach(element => {
            const dropdownMenu = element.querySelector('.dropdown-menu');
            if (dropdownMenu) {
                element.addEventListener('click', event => {
                    event.stopPropagation();
                    dropdownMenu.classList.toggle('hidden');
                });

                document.addEventListener('click', event => {
                    if (!event.target.closest('[data-dropdown]')) {
                        dropdownMenu.classList.add('hidden');
                    }
                });
            }
        });
    }

    // Initialize modals
    function initializeModals() {
        const modalTriggers = document.querySelectorAll('[data-modal-target]');
        modalTriggers.forEach(trigger => {
            const modalId = trigger.getAttribute('data-modal-target');
            const modal = document.getElementById(modalId);
            if (modal) {
                trigger.addEventListener('click', () => {
                    modal.classList.remove('hidden');
                });

                const closeButtons = modal.querySelectorAll('[data-modal-close]');
                closeButtons.forEach(button => {
                    button.addEventListener('click', () => {
                        modal.classList.add('hidden');
                    });
                });

                modal.addEventListener('click', event => {
                    if (event.target === modal) {
                        modal.classList.add('hidden');
                    }
                });

                document.addEventListener('keydown', event => {
                    if (event.key === 'Escape' && !modal.classList.contains('hidden')) {
                        modal.classList.add('hidden');
                    }
                });
            }
        });
    }

    // Combine all initialization logic
    function initializeBase() {
        try {
            initializeMobileMenu();
            initializeTooltips();
            initializeDropdowns();
            initializeModals();
            // Other initialization functions can be added here
        } catch (error) {
            console.error('Error during base initialization:', error);
            showFeedback('An error occurred during initialization. Please reload the page.', 'error');
        }
    }

    // Only initialize once when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeBase);
    } else {
        initializeBase();
    }

    // No need to expose utilities as they're already available through window.utils
})();
