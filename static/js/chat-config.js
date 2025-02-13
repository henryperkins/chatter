export class ChatConfig {
    constructor() {
        this.initialized = false;
        this.config = null;
    }

    async init(options = {}) {
        if (this.initialized) return this.config;
        console.debug('ChatConfig: Starting initialization');

        try {
            const configEl = document.getElementById('chat-config');

            console.debug('ChatConfig: Checking for chat container');
            // If we're not on a chat page, resolve with empty config
            if (!configEl || !document.getElementById('chat-container')) {
                this.config = {};
                this.initialized = true;
                window.CHAT_CONFIG = this.config;
                return this.config;
            }

            console.debug('ChatConfig: Loading configuration from DOM');
            // Initialize config from data attributes
            this.config = {
                chatId: configEl.dataset.chatId,
                csrfToken: configEl.dataset.csrfToken,
                models: JSON.parse(configEl.dataset.models || '[]'),
                currentModel: JSON.parse(configEl.dataset.currentModel || 'null'),
                userId: configEl.dataset.userId,
                debug: configEl.dataset.debug === 'true',
                azureToken: configEl.dataset.azureToken
            };

            // Merge any provided options
            if (options.headers) {
                this.config.headers = {
                    ...this.config.headers,
                    ...options.headers
                };
            }

            console.debug('ChatConfig: Configuration loaded:', this.config);

            // Log initialization if in debug mode
            if (this.config.debug) {
                console.log('ChatConfig initialized:', this.config);
            }

            this.initialized = true;
            window.CHAT_CONFIG = this.config;

            // Initialize token usage manager if needed
            if (window.TokenUsageManager && this.config.chatId) {
                console.debug('ChatConfig: Initializing TokenUsageManager');
                window.tokenUsageManager = new TokenUsageManager(this.config);
                await window.tokenUsageManager.initialize();
            }

            return this.config;

        } catch (error) {
            console.error('Failed to initialize chat config:', error);
            // Create empty config on error rather than throwing
            this.config = {};
            this.initialized = true;
            window.CHAT_CONFIG = this.config;
            return this.config;
        }
    }

    static getInstance() {
        console.debug('ChatConfig: Getting instance');
        if (!ChatConfig.instance) {
            ChatConfig.instance = new ChatConfig();
        }
        return ChatConfig.instance;
    }
}

// Export singleton instance
window.ChatConfig = ChatConfig;
