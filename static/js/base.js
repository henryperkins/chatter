(function() {
    // Utility function to get CSRF token
    function getCSRFToken() {
        const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
        if (!csrfTokenMetaTag) {
            console.error('CSRF token meta tag not found.');
            return '';
        }
        return csrfTokenMetaTag.getAttribute('content') || '';
    }

    // Utility function to show feedback messages
    function showFeedback(message, type = 'info') {
        const feedbackDiv = document.getElementById('feedback-message') || createFeedbackElement();
        feedbackDiv.className = `fixed top-4 left-1/2 transform -translate-x-1/2 p-4 rounded-lg shadow-lg z-50 ${
            type === 'error' ? 'bg-red-500 text-white' : type === 'success' ? 'bg-green-500 text-white' : 'bg-blue-500 text-white'
        }`;
        feedbackDiv.textContent = message;
        feedbackDiv.classList.remove('hidden');

        setTimeout(() => {
            feedbackDiv.classList.add('hidden');
        }, 3000);
    }

    function createFeedbackElement() {
        const div = document.createElement('div');
        div.id = 'feedback-message';
        document.body.appendChild(div);
        return div;
    }

    // Fetch with CSRF token
    async function fetchWithCSRF(url, options = {}) {
        const csrfToken = getCSRFToken();
        const headers = {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest',
            ...options.headers
        };

        try {
            const response = await fetch(url, { ...options, headers });

            const contentType = response.headers.get('content-type');
            let data;

            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = await response.text();
                throw new Error(`Invalid response from server: ${text}`);
            }

            if (!response.ok) {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }

            return data;
        } catch (error) {
            console.error('Error in fetchWithCSRF:', error);
            throw error;
        }
    }

    // Initialize mobile menu toggle
    function initializeMobileMenu() {
        const sidebarToggle = document.getElementById('sidebar-toggle');
        const mobileMenu = document.getElementById('mobile-menu');
        const overlay = document.getElementById('overlay');
        const closeButton = document.getElementById('off-canvas-close');

        function toggleMenu() {
            mobileMenu?.classList.toggle('hidden');
            overlay?.classList.toggle('hidden');
            document.body.classList.toggle('overflow-hidden');
        }

        if (sidebarToggle && mobileMenu) {
            sidebarToggle.addEventListener('click', toggleMenu);
            // Close menu when clicking outside
            document.addEventListener('click', (event) => {
                if (!mobileMenu.contains(event.target) && !sidebarToggle.contains(event.target)) {
                    mobileMenu.classList.add('hidden');
                }
            });
        }
    }

    // Initialize dark mode toggle
    function initializeDarkMode() {
        const darkModeToggle = document.getElementById('dark-mode-toggle');
        const rootElement = document.documentElement;
        const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

        let savedTheme;
        try {
            savedTheme = localStorage.getItem('theme');
        } catch (error) {
            console.warn('localStorage is not available. Falling back to system preferences.');
        }

        const isDarkMode = savedTheme === 'dark' || (!savedTheme && systemPrefersDark);
        rootElement.classList.toggle('dark', isDarkMode);

        if (darkModeToggle) {
            darkModeToggle.addEventListener('click', () => {
                const newTheme = rootElement.classList.toggle('dark') ? 'dark' : 'light';
                try {
                    localStorage.setItem('theme', newTheme);
                } catch (error) {
                    console.warn('Failed to save theme to localStorage.');
                }
            });
        }
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
            initializeDarkMode();
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

    // Expose utility functions if needed
    window.baseUtils = {
        getCSRFToken,
        showFeedback,
        fetchWithCSRF
    };
})();
