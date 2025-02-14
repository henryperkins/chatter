// static/js/base.js

class MobileMenuManager {
    constructor() {
        this.mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        this.mobileMenu = document.getElementById('mobile-menu');
        this.mobileMenuBackdrop = document.getElementById('mobile-menu-backdrop');
        this.isOpen = false;
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.currentTranslateX = 0;
        this.isDragging = false;
        this.darkModeEnabled = document.documentElement.classList.contains('dark');

        if (this.mobileMenuToggle && this.mobileMenu && this.mobileMenuBackdrop) {
            this.initialize();
        }
    }

    initialize() {
        this.setupEventListeners();
        this.setupAccessibility();
        this.setupGestureHandling();
    }

    setupEventListeners() {
        // Toggle button click
        this.mobileMenuToggle.addEventListener('click', () => this.toggleMenu());

        // Backdrop click
        this.mobileMenuBackdrop.addEventListener('click', () => this.closeMenu());

        // Close on navigation
        this.mobileMenu.addEventListener('click', (event) => {
            if (event.target.tagName === 'A') {
                this.closeMenu();
            }
        });

        // Keyboard navigation
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.isOpen) {
                this.closeMenu();
            }
        });

        // Resize handling
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768 && this.isOpen) {
                this.closeMenu();
            }
        });

        // Handle safe area changes
        window.addEventListener('resize', this.updateSafeArea.bind(this));

        // Handle dark mode changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            this.darkModeEnabled = e.matches;
        });
    }

    setupAccessibility() {
        this.mobileMenuToggle.setAttribute('role', 'button');
        this.mobileMenuToggle.setAttribute('aria-haspopup', 'true');
        this.mobileMenuToggle.setAttribute('aria-expanded', 'false');
        this.mobileMenu.setAttribute('role', 'navigation');
        this.mobileMenu.setAttribute('aria-label', 'Mobile navigation menu');
    }

    setupGestureHandling() {
        // Touch start
        this.mobileMenu.addEventListener('touchstart', (e) => {
            this.touchStartX = e.touches[0].clientX;
            this.touchStartY = e.touches[0].clientY;
            this.isDragging = true;
            this.mobileMenu.style.transition = 'none';
        }, { passive: true });

        // Touch move
        this.mobileMenu.addEventListener('touchmove', (e) => {
            if (!this.isDragging) return;

            const touchX = e.touches[0].clientX;
            const touchY = e.touches[0].clientY;
            const deltaX = touchX - this.touchStartX;
            const deltaY = Math.abs(touchY - this.touchStartY);

            // Prevent vertical scrolling while dragging horizontally
            if (Math.abs(deltaX) > deltaY && e.cancelable) {
                e.preventDefault();
            }

            if (deltaX < 0) {
                this.currentTranslateX = deltaX;
                this.mobileMenu.style.transform = `translateX(${deltaX}px)`;

                // Update backdrop opacity based on drag
                const opacity = Math.max(0, 0.5 + (deltaX / this.mobileMenu.offsetWidth) * 0.5);
                this.mobileMenuBackdrop.style.opacity = opacity;
            }
        }, { passive: false });

        // Touch end
        this.mobileMenu.addEventListener('touchend', (e) => {
            if (!this.isDragging) return;

            this.isDragging = false;
            this.mobileMenu.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';

            if (Math.abs(this.currentTranslateX) > this.mobileMenu.offsetWidth * 0.3) {
                this.closeMenu();
            } else {
                this.mobileMenu.style.transform = 'translateX(0)';
                this.mobileMenuBackdrop.style.opacity = '0.5';
            }

            this.currentTranslateX = 0;
        });
    }

    async toggleMenu() {
        const csrfToken = window.utils.getCSRFToken();
        if (!csrfToken) {
            console.error('CSRF token not found');
            return;
        }
        
        try {
            await fetch('/api/menu/state', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    isOpen: !this.isOpen
                })
            });
            this.isOpen ? this.closeMenu() : this.openMenu();
        } catch (error) {
            console.error('Failed to save menu state:', error);
            // Still toggle menu even if save fails
            this.isOpen ? this.closeMenu() : this.openMenu();
        }
    }

    openMenu() {
        this.isOpen = true;
        
        // Apply backdrop blur with dark mode consideration
        const backdropClass = this.darkModeEnabled ? 'bg-gray-900/70' : 'bg-gray-800/60';
        this.mobileMenuBackdrop.classList.add(backdropClass, 'backdrop-blur-sm');
        
        this.mobileMenu.classList.remove('-translate-x-full');
        this.mobileMenu.classList.add('translate-x-0');
        this.mobileMenuBackdrop.classList.remove('hidden');
        this.mobileMenuBackdrop.classList.add('opacity-100');
        this.mobileMenuToggle.setAttribute('aria-expanded', 'true');
        document.body.classList.add('overflow-hidden');
        
        this.updateMenuColors();

        // Announce to screen readers
        this.announceMenuState('Menu opened');
    }

    closeMenu() {
        this.isOpen = false;
        
        // Remove backdrop effects
        this.mobileMenuBackdrop.className = 'fixed inset-0 z-[2000] hidden transition-all duration-300 ease-in-out opacity-0';
        
        this.mobileMenu.classList.add('-translate-x-full');
        this.mobileMenu.classList.remove('translate-x-0');
        this.mobileMenuBackdrop.classList.add('hidden');
        this.mobileMenuBackdrop.classList.remove('opacity-100');
        this.mobileMenuToggle.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('overflow-hidden');

        // Announce to screen readers
        this.announceMenuState('Menu closed');
    }

    updateMenuColors() {
        if (this.darkModeEnabled) {
            this.mobileMenu.classList.remove('bg-white/98');
            this.mobileMenu.classList.add('bg-gray-800/98');
            this.mobileMenuBackdrop.classList.remove('bg-gray-800/60');
            this.mobileMenuBackdrop.classList.add('bg-gray-900/70');
        } else {
            this.mobileMenu.classList.remove('bg-gray-800/98');
            this.mobileMenu.classList.add('bg-white/98');
            this.mobileMenuBackdrop.classList.remove('bg-gray-900/70');
            this.mobileMenuBackdrop.classList.add('bg-gray-800/60');
        }
    }

    updateSafeArea() {
        const safeAreaTop = getComputedStyle(document.documentElement).getPropertyValue('--sat') || '0px';
        const safeAreaBottom = getComputedStyle(document.documentElement).getPropertyValue('--sab') || '0px';

        this.mobileMenu.style.paddingTop = `calc(4rem + ${safeAreaTop})`;
        this.mobileMenu.style.paddingBottom = safeAreaBottom;
    }

    announceMenuState(message) {
        let announcer = document.getElementById('menu-announcer');
        if (!announcer) {
            announcer = document.createElement('div');
            announcer.id = 'menu-announcer';
            announcer.setAttribute('aria-live', 'polite');
            announcer.className = 'sr-only';
            document.body.appendChild(announcer);
        }
        announcer.textContent = message;
    }
}

class FontSizeManager {
    constructor() {
        this.decreaseBtn = document.getElementById('decrease-font-size');
        this.increaseBtn = document.getElementById('increase-font-size');
        this.resetBtn = document.getElementById('reset-font-size');
        this.currentFontSize = parseFloat(localStorage.getItem('fontSize')) || 1.0;

        this.initialize();
    }

    initialize() {
        this.applyFontSize(this.currentFontSize);
        this.setupEventListeners();
    }

    setupEventListeners() {
        if (!this.decreaseBtn || !this.increaseBtn || !this.resetBtn) return;

        this.decreaseBtn.addEventListener('click', () => {
            this.currentFontSize = Math.max(0.8, this.currentFontSize - 0.1);
            this.applyFontSize(this.currentFontSize);
        });

        this.increaseBtn.addEventListener('click', () => {
            this.currentFontSize = Math.min(1.5, this.currentFontSize + 0.1);
            this.applyFontSize(this.currentFontSize);
        });

        this.resetBtn.addEventListener('click', () => {
            this.currentFontSize = 1.0;
            this.applyFontSize(this.currentFontSize);
        });

        // Add keyboard support
        [this.decreaseBtn, this.increaseBtn, this.resetBtn].forEach(btn => {
            if (btn) {
                btn.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        btn.click();
                    }
                });
            }
        });
    }

    applyFontSize(fontSize) {
        document.documentElement.style.fontSize = `${fontSize}em`;
        localStorage.setItem('fontSize', fontSize);
        this.announceNewFontSize(fontSize);
    }

    announceNewFontSize(fontSize) {
        let announcer = document.getElementById('font-size-announcer');
        if (!announcer) {
            announcer = document.createElement('div');
            announcer.id = 'font-size-announcer';
            announcer.setAttribute('aria-live', 'polite');
            announcer.className = 'sr-only';
            document.body.appendChild(announcer);
        }
        announcer.textContent = `Font size ${Math.round(fontSize * 100)}%`;
    }
}

// Initialize components when DOM is ready
document.addEventListener('app:ready', async function() {
    await window.App.waitForDependencies();

    // Initialize mobile menu
    const mobileMenu = new MobileMenuManager();

    // Initialize font size controls
    const fontSizeManager = new FontSizeManager();

    // Handle flash messages
    initializeFlashMessages();

    // Initialize tooltips
    initializeTooltips();

    // Initialize modals
    initializeModals();
});

function initializeFlashMessages() {
    const flashMessages = document.querySelectorAll('[role="alert"]');
    flashMessages.forEach(message => {
        const dismissButton = message.querySelector('button');
        let timeoutId;

        const removeMessage = () => {
            message.style.opacity = '0';
            message.style.transform = 'translateY(-10px)';
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
}

function initializeTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(element => {
        const tooltipText = element.getAttribute('data-tooltip');
        if (!tooltipText) return;

        const tooltip = document.createElement('div');
        tooltip.className = 'tooltip hidden bg-gray-900/95 dark:bg-gray-800/95 text-white text-sm px-3 py-1.5 rounded-md absolute z-50 transform -translate-x-1/2 transition-all duration-200 shadow-lg backdrop-blur-sm';
        tooltip.textContent = tooltipText;
        document.body.appendChild(tooltip);

        function positionTooltip() {
            const rect = element.getBoundingClientRect();
            tooltip.style.left = `${rect.left + rect.width / 2}px`;
            tooltip.style.top = `${rect.bottom + 8}px`;
        }

        element.addEventListener('mouseenter', () => {
            tooltip.classList.remove('hidden');
            tooltip.classList.add('opacity-100');
            positionTooltip();
        });

        element.addEventListener('mouseleave', () => {
            tooltip.classList.add('hidden');
            tooltip.classList.remove('opacity-100');
        });

        // Reposition tooltip on scroll and resize
        window.addEventListener('scroll', positionTooltip);
        window.addEventListener('resize', positionTooltip);
    });
}

function initializeModals() {
    const modalTriggers = document.querySelectorAll('[data-modal-target]');
    modalTriggers.forEach(trigger => {
        const modalId = trigger.getAttribute('data-modal-target');
        const modal = document.getElementById(modalId);
        if (!modal) return;

        function openModal() {
            modal.classList.remove('hidden');
            modal.classList.add('opacity-100');
            document.body.classList.add('overflow-hidden');

            // Trap focus within modal
            const focusableElements = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            const firstFocusable = focusableElements[0];
            const lastFocusable = focusableElements[focusableElements.length - 1];

            firstFocusable?.focus();

            modal.addEventListener('keydown', function(e) {
                if (e.key === 'Tab') {
                    if (e.shiftKey && document.activeElement === firstFocusable) {
                        e.preventDefault();
                        lastFocusable?.focus();
                    } else if (!e.shiftKey && document.activeElement === lastFocusable) {
                        e.preventDefault();
                        firstFocusable?.focus();
                    }
                }
            });
        }

        function closeModal() {
            modal.classList.add('hidden');
            modal.classList.remove('opacity-100');
            document.body.classList.remove('overflow-hidden');
            trigger.focus(); // Return focus to trigger
        }

        // Open modal
        trigger.addEventListener('click', openModal);

        // Close modal
        const closeButtons = modal.querySelectorAll('[data-modal-close]');
        closeButtons.forEach(button => {
            button.addEventListener('click', closeModal);
        });

        // Click outside to close
        modal.addEventListener('click', event => {
            if (event.target === modal) {
                closeModal();
            }
        });

        // Close on ESC
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !modal.classList.contains('hidden')) {
                closeModal();
            }
        });
    });
}
