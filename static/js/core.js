window.App = {
    initialized: false,
    dependencies: {
        utils: false,
        markdown: false,
        prism: false,
        darkMode: false,
        tokenUsage: false,
        fileUpload: false,
        chatConfig: false
    },

    async init() {
        if (this.initialized) return;
        
        // Initialize core dependencies
        await this.initializeMarkdown();
        await this.initializePrism();
        await this.initializeUtils();
        
        // Set up global error handling
        this.setupErrorHandling();
        
        this.initialized = true;
        document.dispatchEvent(new Event('app:ready'));
    },

    async initializeMarkdown() {
        if (!window.markdownit) {
            console.error('markdown-it not loaded');
            return;
        }

        window.md = window.markdownit({
            html: true,
            linkify: true,
            breaks: true,
            typographer: true,
            highlight: function (str, lang) {
                if (lang && window.Prism.languages[lang]) {
                    try {
                        return window.Prism.highlight(str, window.Prism.languages[lang], lang);
                    } catch (e) {
                        console.warn('Error highlighting code:', e);
                    }
                }
                return '';
            }
        });
        
        this.dependencies.markdown = true;
    },

    async initializePrism() {
        if (!window.Prism) {
            console.error('Prism not loaded');
            return;
        }
        
        this.dependencies.prism = true;
    },

    async initializeUtils() {
        if (!window.utils) {
            console.error('Utils not loaded');
            return;
        }
        
        this.dependencies.utils = true;
    },

    setupErrorHandling() {
        window.addEventListener('error', (event) => {
            console.error('Global error:', event.error);
            if (window.utils) {
                window.utils.showFeedback('An error occurred', 'error');
            }
        });
    },

    async waitForDependencies() {
        return new Promise((resolve, reject) => {
            const check = () => {
                if (Object.values(this.dependencies).every(dep => dep)) {
                    resolve();
                    return;
                }
                
                setTimeout(check, 100);
            };
            
            check();
        });
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => window.App.init());
