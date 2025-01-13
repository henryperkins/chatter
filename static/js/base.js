(function() {
    // We can still use showFeedback from utils if needed
    const { showFeedback, fetchWithCSRF } = window.utils;

    /**
     * Initializes mobile layout interactions for responsive design.
     * 
     * Handles mobile menu and sidebar interactions on screens smaller than 768px, including:
     * - Toggling mobile menu visibility
     * - Toggling sidebar visibility
     * - Managing body overflow for mobile views
     * - Handling outside clicks to close menus
     * 
     * @description
     * This function is only active on mobile screen sizes (width < 768px). It sets up
     * event listeners for mobile menu and sidebar toggle buttons, allowing users to
     * open and close these UI components. Clicking outside the menu or sidebar will
     * automatically close them.
     * 
     * @requires DOM elements with IDs:
     * - 'mobile-menu-toggle'
     * - 'mobile-menu'
     * - 'sidebar-toggle'
     * - 'sidebar'
     * - 'mobile-menu-close' (optional)
     * 
     * @example
     * // Automatically called during page initialization
     * initializeMobileLayout();
     * 
     * @throws {Error} If required DOM elements are missing
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

        /**
         * Toggles the visibility of the mobile menu.
         * 
         * @description Switches the mobile menu's display state between shown and hidden.
         * Handles the aria-expanded attribute for accessibility and applies a CSS translation
         * to slide the menu in or out.
         * 
         * @returns {void}
         * 
         * @throws {Error} If the mobile menu toggle element is not found.
         * 
         * @example
         * // Clicking a menu button will toggle the mobile menu's visibility
         * mobileMenuToggle.addEventListener('click', toggleMobileMenu);
         */
        function toggleMobileMenu() {
            if (!mobileMenu) return;
            const expanded = mobileMenuToggle.getAttribute('aria-expanded') === 'true';
            mobileMenu.classList.toggle('-translate-x-full');
            mobileMenuToggle.setAttribute('aria-expanded', !expanded);
        }

        /**
         * Toggles the visibility of the sidebar by translating its position and managing body overflow.
         * 
         * @description
         * - Checks if the sidebar element exists before performing any actions
         * - Toggles a CSS translation class to slide the sidebar in/out
         * - Prevents body scrolling when sidebar is open by adding/removing 'overflow-hidden' class
         * 
         * @returns {void}
         */
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
     * Initializes tooltips for elements with a 'data-tooltip' attribute.
     * 
     * Creates and positions tooltips dynamically when users hover over elements.
     * Tooltips are positioned relative to the triggering element and include
     * the text specified in the 'data-tooltip' attribute.
     * 
     * @description
     * - Selects all elements with a 'data-tooltip' attribute
     * - Creates a tooltip div for each element
     * - Adds event listeners to show/hide tooltips on mouse enter/leave
     * - Positions tooltips dynamically based on element's bounding rectangle
     * 
     * @example
     * <div data-tooltip="Helpful information">Hover me</div>
     * 
     * @throws {Error} If tooltip creation or event listener attachment fails
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
     * Initializes dropdown functionality for elements with the 'data-dropdown' attribute.
     * 
     * This function selects all dropdown elements and sets up event listeners to:
     * - Toggle dropdown menu visibility when the dropdown element is clicked
     * - Close dropdown menus when clicking outside of them
     * 
     * @description
     * - Finds all elements with the 'data-dropdown' attribute
     * - Adds click event listeners to toggle dropdown menu visibility
     * - Prevents event propagation to avoid immediate closing
     * - Implements a document-wide click listener to close dropdowns when clicking outside
     * 
     * @example
     * // HTML: <div data-dropdown><button>Dropdown</button><div class="dropdown-menu hidden">...</div></div>
     * 
     * @throws {Error} Silently handles cases where dropdown menu is not found
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
     * Initializes modal functionality for all modal triggers on the page.
     * 
     * This function sets up event listeners for modal triggers, close buttons, 
     * and provides methods to open and close modals through user interactions.
     * 
     * @description
     * - Finds all elements with a `data-modal-target` attribute
     * - Adds click event to trigger buttons to show corresponding modals
     * - Adds click event to close buttons to hide modals
     * - Allows closing modal by clicking outside the modal content
     * - Enables closing modal using the Escape key
     * 
     * @example
     * // HTML structure
     * <button data-modal-target="myModal">Open Modal</button>
     * <div id="myModal" class="modal hidden">
     *   <button data-modal-close>Close</button>
     * </div>
     * 
     * @throws {Error} If modal elements cannot be found or event listeners fail to attach
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
     * Initializes core UI components and layout for the web application.
     * 
     * @description Serves as the main entry point for setting up interactive UI elements,
     * including mobile layout, tooltips, dropdowns, and modals. Provides comprehensive
     * error handling to ensure graceful initialization and user feedback.
     * 
     * @throws {Error} Logs any initialization errors and displays user-friendly error feedback.
     * 
     * @example
     * // Automatically called when DOM is ready
     * initializeBase();
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
