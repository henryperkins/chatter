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
        // Get stored theme or system preference
        const storedTheme = localStorage.getItem('theme');
        const systemPrefersDark = this.mediaQuery.matches;

        // If theme is explicitly stored, use it
        if (storedTheme) {
            this.setTheme(storedTheme);
        } else {
            // Otherwise use system preference
            this.setTheme(systemPrefersDark ? 'dark' : 'light');
        }

        // Make theme controls visible after initialization
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.showToggle());
        } else {
            this.showToggle();
        }
    },

    showToggle() {
        if (this.darkModeToggle) {
            this.darkModeToggle.classList.remove('opacity-0');
            // Add transition class after a small delay to prevent initial animation
            setTimeout(() => {
                this.html.classList.add('transitioning');
            }, 100);
        }
    },

    setupEventListeners() {
        // Handle toggle button clicks
        this.darkModeToggle?.addEventListener('click', () => {
            const newTheme = this.html.classList.contains('dark') ? 'light' : 'dark';
            this.setTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        });

        // Handle system preference changes
        this.mediaQuery.addEventListener('change', (e) => {
            // Only update if user hasn't set a preference
            if (!localStorage.getItem('theme')) {
                this.setTheme(e.matches ? 'dark' : 'light');
            }
        });
    },

    setTheme(theme) {
        if (theme === 'dark') {
            this.html.classList.add('dark');
        } else {
            this.html.classList.remove('dark');
        }
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
