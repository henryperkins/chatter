(() => {
    'use strict';

    class ChatConfig {
        constructor() {
            this.initialized = false;
            this.config = null;
            this.initPromise = null;
        }

        async init() {
            if (this.initialized) return this.config;

            if (this.initPromise) {
                return this.initPromise;
            }

            this.initPromise = new Promise((resolve, reject) => {
                try {
                    const configEl = document.getElementById('chat-config');
                    if (!configEl) {
                        console.warn('Chat configuration element not found. Skipping chat config initialization.');
                        resolve({});
                    }

                    this.config = {
                        chatId: configEl.dataset.chatId,
                        csrfToken: configEl.dataset.csrfToken,
                        models: JSON.parse(configEl.dataset.models || '[]'),
                        currentModel: JSON.parse(configEl.dataset.currentModel || 'null'),
                        userId: configEl.dataset.userId,
                        debug: configEl.dataset.debug === 'true',
                        azureToken: configEl.dataset.azureToken
                    };

                    this.initialized = true;
                    window.CHAT_CONFIG = this.config;
                    resolve(this.config);
                } catch (error) {
                    console.error('Failed to initialize chat config:', error);
                    reject(error);
                }
            });

            return this.initPromise;
        }

        static getInstance() {
            if (!ChatConfig.instance) {
                ChatConfig.instance = new ChatConfig();
            }
            return ChatConfig.instance;
        }
    }

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        const config = ChatConfig.getInstance();
        config.init().catch(error => {
            console.error('Failed to initialize chat config:', error);
        });
    });

    // Export for use in other modules
    window.ChatConfig = ChatConfig;
})();
