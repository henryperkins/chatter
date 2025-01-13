(function() {
    // We can still use showFeedback from utils if needed
    const { showFeedback, fetchWithCSRF } = window.utils;

    /**
     * Merges the old `initializeMobileMenu` with chat's `setupMobileLayout`.
     * We now handle:
     * 1) Toggling the mobile sidebar or menu
     * 2) Toggling body overflow (for mobile)
     * 3) Handling outside clicks
     * 4) Checking if screen is below a certain width
     * 5) Possibly toggling a separate 'mobileMenu' or 'sidebar'
     */
    function initializeMobileLayout() {
        // If desktop, skip
        if (window.innerWidth >= 768) return;

        // Grab your elements
        const mobileMenuToggle = document.getElementById('mobile-menu-toggle'); 
        const mobileMenu       = document.getElementById('mobile-menu');
        const sidebarToggle    = document.getElementById('sidebar-toggle');
        const sidebar          = document.getElementById('sidebar');
        const mobileMenuClose  = document.getElementById('mobile-menu-close');

        // Basic check that we have at least one toggle
        if (!mobileMenuToggle && !sidebarToggle) {
            return; // nothing to do
        }

        // Toggle function for the "mobile-menu"
        function toggleMobileMenu() {
            if (!mobileMenu) return;
            const expanded = mobileMenuToggle.getAttribute('aria-expanded') === 'true';
            mobileMenu.classList.toggle('-translate-x-full');
            mobileMenuToggle.setAttribute('aria-expanded', !expanded);
        }

        // Toggle function for the "sidebar"
        function toggleSidebar() {
            if (!sidebar) return;
            sidebar.classList.toggle('-translate-x-full');
            document.body.classList.toggle('overflow-hidden'); // from the chat code
        }

        // Wire up clicks
        mobileMenuToggle?.addEventListener('click', toggleMobileMenu);
        sidebarToggle?.addEventListener('click', toggleSidebar);

        if (mobileMenuClose) {
            mobileMenuClose.addEventListener('click', toggleMobileMenu);
        }

        // Close if user clicks outside
        document.addEventListener('click', (e) => {
            // If clicking outside mobileMenu & toggles
            if (mobileMenu && !mobileMenu.contains(e.target) && !mobileMenuToggle?.contains(e.target)) {
                mobileMenu.classList.add('-translate-x-full');
            }
            // If clicking outside sidebar & toggles
            if (sidebar && !sidebar.contains(e.target) && !sidebarToggle?.contains(e.target)) {
                sidebar.classList.add('-translate-x-full');
                document.body.classList.remove('overflow-hidden');
            }
        });
    }

    /**
     * Tooltips initialization
     */
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

    /**
     * Dropdown initialization
     */
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

    /**
     * Modals initialization
     */
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

    /**
     * Main entry point for base.js
     */
    function initializeBase() {
        try {
            // Merge old mobile menu + new chat mobile logic
            initializeMobileLayout();
            initializeTooltips();
            initializeDropdowns();
            initializeModals();
            // Other sitewide or layout initialization...
        } catch (error) {
            console.error('Error during base initialization:', error);
            showFeedback('An error occurred during initialization. Please reload the page.', 'error');
        }
    }

    // Initialize once DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeBase);
    } else {
        initializeBase();
    }
})();
