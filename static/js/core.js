window.App = {
    initialized: false,
    components: {
        monitoring: false,
        utils: false,
        markdown: false,
        prism: false,
        darkMode: false,
        chatConfig: false,
        messageRenderer: false,
        tokenUsage: false,
        chat: false
    },

    async init() {
        if (this.initialized) return;
        
        console.debug('App: Starting initialization sequence');
        
        // Configure Axios defaults
        window.axios.defaults.headers.common['X-Requested-With'] = 'XMLHttpRequest';
        window.axios.defaults.withCredentials = true;

        try {
            // 1. Initialize monitoring first for error tracking
            await this.initMonitoring();
            
            // 2. Initialize utils
            await this.initUtils();

            // 3. Initialize core dependencies in parallel
            const timeout = 15000;
            await Promise.all([
                this.initializeWithTimeout(this.initializeMarkdown(), 'Markdown', timeout),
                this.initializeWithTimeout(this.initializePrism(), 'Prism', timeout),
                this.initializeWithTimeout(this.initializeDarkMode(), 'Dark Mode', timeout)
            ]);

            // 4. Initialize chat-specific components if on chat page
            if (document.getElementById('chat-container')) {
                await this.initializeChatComponents();
            }

            this.initialized = true;
            document.dispatchEvent(new Event('app:ready'));
            
            if (this.components.monitoring) {
                console.debug('App: Component states:', this.components);
                window.monitoring.log('info', 'App initialization complete', this.components);
            }
        } catch (error) {
            console.error('App initialization failed:', error);
            if (this.components.monitoring) {
                window.monitoring.logError('App initialization failed', error);
            }
            this.handleInitializationError(error);
        }
    },

    async initMonitoring() {
        if (this.components.monitoring) return;
        if (window.monitoring) {
            console.debug('App: Initializing monitoring');
            this.components.monitoring = true;
            console.debug('App: Monitoring initialized');
        }
    },

    async initUtils() {
        if (this.components.utils) return;
        if (!window.utils) {
            console.debug('App: Utils not found');
            console.trace('Utils dependency missing');
            throw new Error('Utils not loaded');
        }
        this.components.utils = true;
        console.log('Utils initialized');
    },

    async initializeChatComponents() {
        try {
            console.debug('App: Initializing chat components');
            // Initialize ChatConfig first
            const config = window.ChatConfig.getInstance();
            await config.init();
            this.components.chatConfig = true;

            // Initialize MessageRenderer after ChatConfig
            if (window.MessageRenderer) {
                await window.MessageRenderer.initialize();
                this.components.messageRenderer = true;
            }

            // TokenUsageManager depends on ChatConfig
            if (window.TokenUsageManager && window.CHAT_CONFIG?.chatId) {
                window.tokenUsageManager = new TokenUsageManager(window.CHAT_CONFIG);
                await window.tokenUsageManager.initialize();
                this.components.tokenUsage = true;
            }
            
            console.debug('App: Chat components initialized successfully');
        } catch (error) {
            console.error('Chat components initialization failed:', error);
            if (this.components.monitoring) {
                window.monitoring.logError('Chat components initialization failed', error);
            }
            throw error;
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

            this.components.markdown = true;
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
            this.components.prism = true;
            return true;
        } catch (error) {
            console.error('Prism initialization failed:', error);
            throw error;
        }
    },

    async waitForDependencies(timeout = 10000) {
        return new Promise((resolve, reject) => {
            const start = Date.now();

            const check = () => {
                const requiredDeps = ['markdown', 'prism', 'darkMode'];
                if (requiredDeps.every(dep => this.components[dep])) {
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
        if (this.components.monitoring) {
            window.monitoring.logError('Initialization error', error);
        }
        this.showFallbackError('Failed to initialize application. Please refresh the page.');
    },

    showFallbackError(message) {
        if (window.utils?.showFeedback) {
            window.utils.showFeedback(message, 'error');
        } else {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'fixed top-4 left-1/2 transform -translate-x-1/2 bg-red-500 text-white px-4 py-2 rounded-lg shadow-lg z-[2000]';
            errorDiv.textContent = message;
            document.body.appendChild(errorDiv);
        }
    },

    async initializeWithTimeout(promise, name, timeout) {
        return Promise.race([
            promise,
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error(`${name} initialization timeout`)), timeout)
            )
        ]);
    },

    async initializeDarkMode() {
        if (typeof window.DarkMode === 'undefined') {
            throw new Error('Dark mode module not loaded');
        }
        try {
            await window.DarkMode.init();
            this.components.darkMode = true;
            return true;
        } catch (error) {
            console.error('Dark mode initialization failed:', error);
            throw error;
        }
    }
};

// Initialize when DOM is ready, with error handling
document.addEventListener('DOMContentLoaded', () => {
    console.debug('App: DOMContentLoaded triggered, starting initialization');
    window.App.init().catch(error => {
        console.error('Failed to initialize App:', error);
        window.App.handleInitializationError(error);
    });
});
