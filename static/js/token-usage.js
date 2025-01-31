class TokenUsageManager {
    constructor(config) {
        // Handle both config formats (just chatId or full CHAT_CONFIG)
        if (!config) {
            console.error('TokenUsageManager: Missing configuration');
            return;
        }
    }

        this.chatId = typeof config === 'object' ? config.chatId : config;
        if (!this.chatId) {
            console.error('TokenUsageManager: Missing chatId in configuration');
            return;
        }

        this.updateInterval = null;

        // Set up element references
        this.elements = this.initializeElements();

        // Validate required elements
        if (this.validateElements()) {
            console.log('TokenUsageManager: Initialized successfully');
            this.initialize();
        } else {
            console.error('TokenUsageManager: Failed to initialize - missing elements');
        }
    }
}

    /**
     * Collect references to all DOM elements TokenUsageManager depends on.
     */
    initializeElements() {
        return {
            container: document.getElementById('token-usage'),
            progress: document.getElementById('token-progress'),
            tokensUsed: document.getElementById('tokens-used'),
            tokensLimit: document.getElementById('tokens-limit'),
            userTokens: document.getElementById('user-tokens'),
            assistantTokens: document.getElementById('assistant-tokens'),
            systemTokens: document.getElementById('system-tokens'),
            toggleBtn: document.getElementById('toggle-stats-btn'),
            refreshBtn: document.getElementById('refresh-stats')
        };
    }

    /**
     * Ensure that critical elements exist in the DOM before initializing.
     */
    validateElements() {
        console.log('TokenUsageManager: Starting element validation');
        console.log('TokenUsageManager: Current elements:', this.elements);

        const requiredElements = ['container', 'progress', 'tokensUsed', 'tokensLimit'];
        console.log('TokenUsageManager: Required elements:', requiredElements);

        const missingElements = [];
        const validElements = requiredElements.every(elementName => {
            const exists = !!this.elements[elementName];
            if (!exists) {
                missingElements.push(elementName);
                console.error(`TokenUsageManager: Missing required element: ${elementName}`);
            } else {
                console.log(`TokenUsageManager: Found required element: ${elementName}`);
            }
            return exists;
        });

        if (validElements) {
            console.log('TokenUsageManager: All required elements found');
        } else {
            console.error('TokenUsageManager: Missing elements:', missingElements);
        }

        return validElements;
    }

    /**
     * Perform the main setup steps: show the container, attach event listeners,
     * do an initial stats update, and start periodic updates.
     */
    initialize() {
        try {
            // Show token usage container (if hidden)
            if (this.elements.container) {
                this.elements.container.classList.remove('hidden');
            }

            // Attach event listeners
            if (this.elements.toggleBtn) {
                this.elements.toggleBtn.addEventListener('click', () => this.toggleDisplay());
            }
            if (this.elements.refreshBtn) {
                this.elements.refreshBtn.addEventListener('click', () => this.updateStats());
            }

            // Initial stats update
            this.updateStats();

            // Start auto-updates every 30 seconds
            this.startPeriodicUpdates();

            console.log('TokenUsageManager: Initialization complete');
        } catch (error) {
            console.error('TokenUsageManager: Initialization failed:', error);
        }
    }

    /**
     * Show/hide the token usage panel. If becoming visible, also refresh stats.
     */
    toggleDisplay() {
        if (this.elements.container) {
            this.elements.container.classList.toggle('hidden');
            if (!this.elements.container.classList.contains('hidden')) {
                this.updateStats();
            }
        }
    }

    /**
     * Fetch the latest stats from the server and update the UI.
     * Only runs if the panel is visible.
     */
    async updateStats() {
        if (!this.elements.container) {
            console.error('TokenUsageManager: Container element not found');
            return;
        }

        try {
            console.log('TokenUsageManager: Starting stats update for chat', this.chatId);

            // Check current model from the <select> element, if present
            const modelSelect = document.getElementById('model-select');
            const modelId = modelSelect?.value || '';
            console.log('TokenUsageManager: Using model ID:', modelId);

            const url = `/chat/stats/${this.chatId}?model_id=${modelId}`;
            console.log('TokenUsageManager: Fetching stats from:', url);

            // Fetch stats from the server
            const response = await fetch(url, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });
            console.log('TokenUsageManager: Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('TokenUsageManager: Received data:', data);

            if (data.success && data.stats) {
                console.log('TokenUsageManager: Processing stats:', data.stats);

                // Update UI with stats
                this.updateDisplay(data.stats);

                // Update model-specific token limits, if provided
                if (data.stats.model_limits) {
                    console.log('TokenUsageManager: Updating model limits:', data.stats.model_limits);
                    this.updateModelLimits(data.stats.model_limits);
                }

                console.log('TokenUsageManager: Stats updated successfully');
            } else {
                console.error('TokenUsageManager: Invalid response format:', data);
                throw new Error(data.error || 'Invalid response format');
            }
        } catch (error) {
            console.error('TokenUsageManager: Error updating stats:', error);
            this.showError('Failed to update token usage');
        }
    }

    /**
     * Update the UI with new model limits (e.g., max tokens).
     */
    updateModelLimits(limits) {
        const { max_tokens } = limits;

        // Update the ARIA max for the progress bar
        if (this.elements.progress) {
            this.elements.progress.setAttribute('aria-valuemax', max_tokens);
        }

        // Update the token limit text
        if (this.elements.tokensLimit) {
            this.elements.tokensLimit.textContent = `/ ${max_tokens.toLocaleString()} max`;
        }

        // Store the limits if needed
        this.currentLimits = limits;
    }

    /**
     * Show an error message briefly at the bottom of the token usage container.
     */
    showError(message) {
        const errorElement = document.createElement('div');
        errorElement.className = 'text-red-500 text-sm mt-2';
        errorElement.textContent = message;

        if (this.elements.container) {
            this.elements.container.appendChild(errorElement);

            // Remove the message after 5 seconds
            setTimeout(() => {
                errorElement.remove();
            }, 5000);
        }
    }
    }

    /**
     * Update the display: progress bar width, token usage numbers, etc.
     */
    updateDisplay(stats) {
        console.log('TokenUsageManager: Starting display update with stats:', stats);

        // Ensure we have valid stats object
        if (!stats || typeof stats !== 'object') {
            console.error('TokenUsageManager: Invalid stats object');
            return;
        }

        const limit = stats.token_limit || 0;
        const used = stats.total_tokens || 0;
        const percentage = stats.token_usage_percentage || 0;
        const breakdown = stats.token_breakdown || { user: 0, assistant: 0, system: 0 };

        console.log('TokenUsageManager: Parsed values:', { limit, used, percentage, breakdown });

        // Progress bar width and color
        if (this.elements.progress) {
            const width = `${Math.min(percentage, 100)}%`;
            console.log('TokenUsageManager: Setting progress width to:', width);
            this.elements.progress.style.width = width;
            this.elements.progress.setAttribute('aria-valuenow', percentage);
            this.updateProgressColor(percentage);
        }

        // Tokens used / limit
        if (this.elements.tokensUsed) {
            const text = `${used.toLocaleString()} tokens used`;
            console.log('TokenUsageManager: Setting tokens used text to:', text);
            this.elements.tokensUsed.textContent = text;
        }

        if (this.elements.tokensLimit) {
            const text = `/ ${limit.toLocaleString()} max`;
            console.log('TokenUsageManager: Setting tokens limit text to:', text);
            this.elements.tokensLimit.textContent = text;
        }

        // Token breakdown (user/assistant/system)
        if (this.elements.userTokens) {
            const text = (breakdown.user || 0).toLocaleString();
            console.log('TokenUsageManager: Setting user tokens to:', text);
            this.elements.userTokens.textContent = text;
        }

        if (this.elements.assistantTokens) {
            const text = (breakdown.assistant || 0).toLocaleString();
            console.log('TokenUsageManager: Setting assistant tokens to:', text);
            this.elements.assistantTokens.textContent = text;
        }

        if (this.elements.systemTokens) {
            const text = (breakdown.system || 0).toLocaleString();
            console.log('TokenUsageManager: Setting system tokens to:', text);
            this.elements.systemTokens.textContent = text;
        }

        console.log('TokenUsageManager: Display update complete');
    }
    }

    /**
     * Dynamically update the progress bar color based on usage percentage.
     */
    updateProgressColor(percentage) {
        if (this.elements.progress) {
            this.elements.progress.classList.remove('bg-blue-600', 'bg-yellow-600', 'bg-red-600');

            if (percentage > 90) {
                this.elements.progress.classList.add('bg-red-600');
            } else if (percentage > 75) {
                this.elements.progress.classList.add('bg-yellow-600');
            } else {
                this.elements.progress.classList.add('bg-blue-600');
            }
        }
    }

    /**
     * Auto-update stats every 30 seconds if the panel is visible.
     */
    startPeriodicUpdates() {
        this.updateInterval = setInterval(() => {
            if (this.elements.container && !this.elements.container.classList.contains('hidden')) {
                this.updateStats();
            }
        }, 30000);
}
    }

    /**
     * Manually stop the auto-updates, if needed.
     */
    stopPeriodicUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        }
    }

    /**
     * Optional method: if your app calls this on a new message event,
     * you can re-fetch stats immediately afterward.
     */
    async handleNewMessage() {
        try {
            await this.updateStats();
        } catch (error) {
            console.error('TokenUsageManager: Error updating stats after new message:', error);
        }
    }
}

// Expose the class globally
window.TokenUsageManager = TokenUsageManager;
