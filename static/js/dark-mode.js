// Dark mode utility singleton
const DarkMode = {
    init() {
        if (this.initialized) return;

        this.html = document.documentElement;
        this.darkModeToggle = document.getElementById('dark-mode-toggle');
        this.mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

        this.initialize();
        this.setupEventListeners();
        this.initialized = true;
    },

    initialize() {
        // Add transition class for smooth theme changes
        this.html.classList.add('dark-mode-transition');

        // Get stored theme or system preference
        const storedTheme = localStorage.getItem('theme');
        const systemPrefersDark = this.mediaQuery.matches;
        const userPrefersDark = storedTheme === 'dark' || (!storedTheme && systemPrefersDark);

        // Set initial theme without transition
        this.html.classList.remove('dark-mode-transition');
        this.setTheme(userPrefersDark ? 'dark' : 'light');

        // Re-enable transitions after a brief delay
        setTimeout(() => {
            this.html.classList.add('dark-mode-transition');
        }, 100);

        // Make theme controls visible after initialization
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.showToggle());
        } else {
            this.showToggle();
        }

        // Update ARIA labels
        this.updateARIALabels();
    },

    showToggle() {
        if (this.darkModeToggle) {
            // Fade in the toggle button
            this.darkModeToggle.classList.remove('opacity-0');
            this.darkModeToggle.classList.add('opacity-100');
        }
    },

    setupEventListeners() {
        // Handle toggle button clicks with improved feedback
        this.darkModeToggle?.addEventListener('click', (e) => {
            const newTheme = this.html.classList.contains('dark') ? 'light' : 'dark';

            // Add pressed state
            this.darkModeToggle.classList.add('scale-95');
            setTimeout(() => {
                this.darkModeToggle.classList.remove('scale-95');
            }, 200);

            this.setTheme(newTheme);
            localStorage.setItem('theme', newTheme);

            // Announce theme change to screen readers
            this.announceThemeChange(newTheme);
        });

        // Handle system preference changes
        this.mediaQuery.addEventListener('change', (e) => {
            // Only update if user hasn't set a preference
            if (!localStorage.getItem('theme')) {
                this.setTheme(e.matches ? 'dark' : 'light');
                this.announceThemeChange(e.matches ? 'dark' : 'light');
            }
        });

        // Handle keyboard navigation
        this.darkModeToggle?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.darkModeToggle.click();
            }
        });
    },

    setTheme(theme) {
        const isDark = theme === 'dark';

        if (isDark) {
            this.html.classList.add('dark');
        } else {
            this.html.classList.remove('dark');
        }

        // Update toggle button appearance
        this.updateToggleButton(isDark);

        // Update meta theme-color
        this.updateMetaThemeColor(isDark);
    },

    updateToggleButton(isDark) {
        if (!this.darkModeToggle) return;

        const moonIcon = this.darkModeToggle.querySelector('.dark\\:hidden');
        const sunIcon = this.darkModeToggle.querySelector('.hidden.dark\\:block');

        if (moonIcon && sunIcon) {
            if (isDark) {
                moonIcon.classList.add('hidden');
                sunIcon.classList.remove('hidden');
            } else {
                moonIcon.classList.remove('hidden');
                sunIcon.classList.add('hidden');
            }
        }
    },

    updateMetaThemeColor(isDark) {
        let metaThemeColor = document.querySelector('meta[name="theme-color"]');
        if (!metaThemeColor) {
            metaThemeColor = document.createElement('meta');
            metaThemeColor.name = 'theme-color';
            document.head.appendChild(metaThemeColor);
        }
        metaThemeColor.content = isDark ? '#111827' : '#ffffff';
    },

    updateARIALabels() {
        if (this.darkModeToggle) {
            this.darkModeToggle.setAttribute('role', 'switch');
            this.darkModeToggle.setAttribute('tabindex', '0');
            this.updateARIAState();
        }
    },

    updateARIAState() {
        if (this.darkModeToggle) {
            const isDark = this.html.classList.contains('dark');
            this.darkModeToggle.setAttribute('aria-checked', isDark.toString());
            this.darkModeToggle.setAttribute('aria-label', `${isDark ? 'Dark' : 'Light'} mode enabled. Click to toggle theme.`);
        }
    },

    announceThemeChange(theme) {
        // Create and update live region for screen readers
        let announcer = document.getElementById('theme-announcer');
        if (!announcer) {
            announcer = document.createElement('div');
            announcer.id = 'theme-announcer';
            announcer.setAttribute('aria-live', 'polite');
            announcer.className = 'sr-only';
            document.body.appendChild(announcer);
        }
        announcer.textContent = `${theme === 'dark' ? 'Dark' : 'Light'} mode enabled`;
    }
};

// Initialize dark mode
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => DarkMode.init());
} else {
    DarkMode.init();
}

// Expose DarkMode globally
window.DarkMode = DarkMode;
