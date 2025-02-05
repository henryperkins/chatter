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
        
        try {
            // Initialize core dependencies with timeout
            await Promise.race([
                this.initializeMarkdown(),
                new Promise((_, reject) => 
                    setTimeout(() => reject(new Error('Markdown initialization timeout')), 5000)
                )
            ]);

            await Promise.race([
                this.initializePrism(),
                new Promise((_, reject) => 
                    setTimeout(() => reject(new Error('Prism initialization timeout')), 5000)
                )
            ]);

            await Promise.race([
                this.initializeUtils(),
                new Promise((_, reject) => 
                    setTimeout(() => reject(new Error('Utils initialization timeout')), 5000)
                )
            ]);
            
            // Set up global error handling
            this.setupErrorHandling();
            
            this.initialized = true;
            document.dispatchEvent(new Event('app:ready'));
        } catch (error) {
            console.error('App initialization failed:', error);
            this.handleInitializationError(error);
        }
    },

    async initializeMarkdown() {
        if (!window.markdownit) {
            throw new Error('markdown-it not loaded');
        }

        try {
            window.md = window.markdownit({
                html: true,
                linkify: true,
                breaks: true,
                typographer: true,
                highlight: function (str, lang) {
                    if (lang && window.Prism?.languages[lang]) {
                        try {
                            return window.Prism.highlight(str, window.Prism.languages[lang], lang);
                        } catch (e) {
                            console.warn('Error highlighting code:', e);
                            return str; // Fallback to plain text
                        }
                    }
                    return str; // Return plain text if language isn't supported
                }
            });
            
            this.dependencies.markdown = true;
            return true;
        } catch (error) {
            console.error('Markdown initialization failed:', error);
            throw error;
        }
    },

    async initializePrism() {
        if (!window.Prism) {
            throw new Error('Prism not loaded');
        }
        
        try {
            // Configure Prism options if needed
            window.Prism.manual = true; // Prevent automatic highlighting
            this.dependencies.prism = true;
            return true;
        } catch (error) {
            console.error('Prism initialization failed:', error);
            throw error;
        }
    },

    async initializeUtils() {
        if (!window.utils) {
            throw new Error('Utils not loaded');
        }
        
        try {
            // Verify essential utils methods exist
            const requiredMethods = ['fetchWithCSRF', 'showFeedback', 'sanitizeHTML'];
            for (const method of requiredMethods) {
                if (typeof window.utils[method] !== 'function') {
                    throw new Error(`Missing required utils method: ${method}`);
                }
            }
            
            this.dependencies.utils = true;
            return true;
        } catch (error) {
            console.error('Utils initialization failed:', error);
            throw error;
        }
    },

    setupErrorHandling() {
        window.addEventListener('error', (event) => {
            console.error('Global error:', event.error);
            if (window.utils?.showFeedback) {
                window.utils.showFeedback('An error occurred. Please refresh the page.', 'error');
            } else {
                // Fallback error display
                this.showFallbackError('An error occurred. Please refresh the page.');
            }
        });

        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            if (window.utils?.showFeedback) {
                window.utils.showFeedback('An error occurred. Please refresh the page.', 'error');
            } else {
                this.showFallbackError('An error occurred. Please refresh the page.');
            }
        });
    },

    async waitForDependencies(timeout = 10000) {
        return new Promise((resolve, reject) => {
            const start = Date.now();
            
            const check = () => {
                if (Object.values(this.dependencies).every(dep => dep)) {
                    resolve();
                    return;
                }
                
                if (Date.now() - start > timeout) {
                    reject(new Error('Dependencies timeout'));
                    return;
                }
                
                setTimeout(check, 100);
            };
            
            check();
        });
    },

    handleInitializationError(error) {
        console.error('Initialization error:', error);
        this.showFallbackError('Failed to initialize application. Please refresh the page.');
    },

    showFallbackError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'fixed top-4 left-1/2 transform -translate-x-1/2 bg-red-500 text-white px-4 py-2 rounded-lg shadow-lg z-[2000]';
        errorDiv.textContent = message;
        document.body.appendChild(errorDiv);
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => window.App.init());
