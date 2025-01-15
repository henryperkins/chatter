class TokenUsageManager {
    constructor(config) {
        // Validate config
        if (!config || !config.chatId) {
            console.error('TokenUsageManager: Invalid configuration');
            return;
        }

        this.chatId = config.chatId;
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
        const requiredElements = ['container', 'progress', 'tokensUsed', 'tokensLimit'];
        return requiredElements.every(elementName => {
            const exists = !!this.elements[elementName];
            if (!exists) {
                console.error(`TokenUsageManager: Missing required element: ${elementName}`);
            }
            return exists;
        });
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
        if (this.elements.container.classList.contains('hidden')) {
            // If hidden, do nothing
            return;
        }

        try {
            console.log('TokenUsageManager: Updating stats...');

            // Check current model from the <select> element, if present
            const modelSelect = document.getElementById('model-select');
            const modelId = modelSelect?.value || '';

            // Fetch stats from the server
            const response = await fetch(`/chat/stats/${this.chatId}?model_id=${modelId}`, {
                headers: { 'X-Requested-With': 'X-Requested-With' }
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.success && data.stats) {
                // Update UI with stats
                this.updateDisplay(data.stats);

                // Update model-specific token limits, if provided
                if (data.stats.model_limits) {
                    this.updateModelLimits(data.stats.model_limits);
                }

                console.log('TokenUsageManager: Stats updated successfully');
            } else {
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

        // Keep them in memory if needed for other calculations
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

    /**
     * Update the display: progress bar width, token usage numbers, etc.
     */
    updateDisplay(stats) {
        const limit = stats.token_limit;
        const used = stats.total_tokens;
        const percentage = stats.token_usage_percentage;

        // Progress bar width and color
        if (this.elements.progress) {
            this.elements.progress.style.width = `${Math.min(percentage, 100)}%`;
            this.updateProgressColor(percentage);
        }

        // Tokens used / limit
        if (this.elements.tokensUsed) {
            this.elements.tokensUsed.textContent = `${used.toLocaleString()} tokens used`;
        }
        if (this.elements.tokensLimit) {
            this.elements.tokensLimit.textContent = `/ ${limit.toLocaleString()} max`;
        }

        // Token breakdown (user/assistant/system)
        if (this.elements.userTokens) {
            this.elements.userTokens.textContent = stats.token_breakdown.user.toLocaleString();
        }
        if (this.elements.assistantTokens) {
            this.elements.assistantTokens.textContent = stats.token_breakdown.assistant.toLocaleString();
        }
        if (this.elements.systemTokens) {
            this.elements.systemTokens.textContent = stats.token_breakdown.system.toLocaleString();
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

    /**
     * Manually stop the auto-updates, if needed.
     */
    stopPeriodicUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    /**
     * Optional method: if your app calls this on a new message event,
     * you can re-fetch stats immediately afterward.
     */
    handleNewMessage() {
        this.updateStats();
    }
}

// Expose the class globally
window.TokenUsageManager = TokenUsageManager;
