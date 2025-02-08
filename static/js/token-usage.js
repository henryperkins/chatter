class TokenUsageManager {
    constructor(config) {
        // Prevent multiple instances
        if (window.TokenUsageManager?.instance) {
            console.log('TokenUsageManager: Returning existing instance');
            return window.TokenUsageManager.instance;
        }

        // Handle both config formats (just chatId or full CHAT_CONFIG)
        if (!config) {
            throw new Error('TokenUsageManager: Missing configuration');
        }

        this.chatId = typeof config === 'object' ? config.chatId : config;
        if (!this.chatId || typeof this.chatId !== 'string') {
            throw new Error('TokenUsageManager: Invalid or missing chatId in configuration');
        }

        this.updateInterval = null;
        this.retryCount = 0;
        this.initialized = false;

        // Set up element references
        this.elements = this.initializeElements();

        // Store instance
        window.TokenUsageManager.instance = this;

        console.log('TokenUsageManager: New instance initialized with chatId:', this.chatId);
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
    async initialize() {
        try {
            // Wait for dependencies to be available
            let attempts = 0;
            while ((!window.utils || !window.CHAT_CONFIG) && attempts < 50) {
                await new Promise(resolve => setTimeout(resolve, 100));
                attempts++;
            }

            if (!window.utils || !window.CHAT_CONFIG) {
                throw new Error('Required dependencies not available after waiting');
            }

            // Validate chat ID matches config
            if (this.chatId !== window.CHAT_CONFIG.chatId) {
                console.warn('TokenUsageManager: Chat ID mismatch, updating to match config');
                this.chatId = window.CHAT_CONFIG.chatId;
            }

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
            await this.updateStats();

            // Start auto-updates every 30 seconds
            this.startPeriodicUpdates();

            console.log('TokenUsageManager: Initialization complete');
            return true;
        } catch (error) {
            console.error('TokenUsageManager: Initialization failed:', error);
            return false;
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
     * Estimate token count for a message (simplified version)
     */
    async countMessageTokens(message) {
        // Simple estimation: ~4 characters per token
        return Math.ceil(message.length / 4);
    }

    /**
     * Truncate content to fit within token limit
     */
    async truncateContent(content, maxTokens) {
        // Simple truncation based on character length
        const estimatedCharsPerToken = 4;
        const maxChars = maxTokens * estimatedCharsPerToken;
        return content.slice(0, maxChars);
    }

    /**
     * Process and lint a message before display
     */
    async lintMessage(message) {
        // Basic message cleanup
        if (typeof message !== 'string') {
            return message?.toString() || '';
        }

        // Remove excessive newlines
        message = message.replace(/\n{3,}/g, '\n\n');

        // Ensure code blocks have language specified
        message = message.replace(/```(\s*\n)/g, '```javascript\n');

        // Fix common markdown issues
        message = message
            // Ensure proper spacing around headers
            .replace(/^(#{1,6}[^#\n]+)$/gm, '\n$1\n')
            // Fix list item spacing
            .replace(/^([*-])\s*([^\n]+)$/gm, '$1 $2')
            // Ensure proper code block closure
            .replace(/```[a-zA-Z]*\n((?:(?!```)[\s\S])*)\n?$/gm, '```$1\n```');

        return message;
    }

    /**
     * Fetch the latest stats from the server and update the UI.
     * Only runs if the panel is visible.
     */
    async updateStats() {
        if (!window.utils) {
            console.error('TokenUsageManager: Utils not available');
            return;
        }

        if (!this.elements.container) {
            console.error('TokenUsageManager: Container element not found');
            return;
        }

        if (!this.chatId || typeof this.chatId !== 'string') {
            console.error('TokenUsageManager: Invalid chat ID for stats update:', this.chatId);
            return;
        }

        try {
            console.log('TokenUsageManager: Starting stats update for chat', this.chatId);

            // Check current model from the <select> element, if present
            const modelSelect = document.getElementById('model-select');
            const modelId = modelSelect?.value || '';
            console.log('TokenUsageManager: Using model ID:', modelId);

            const url = `/chat/stats/${this.chatId}`;
            console.log('TokenUsageManager: Fetching stats from:', url, 'with chatId:', this.chatId);

            let data;
            try {
                data = await window.utils.fetchWithCSRF(url, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json'
                    }
                });
                console.log('TokenUsageManager: Received data:', data);
            } catch (error) {
                if (error.status === 404) {
                    console.error('TokenUsageManager: Chat not found:', this.chatId);
                    this.showError('Chat not found or access denied');
                    return;
                }
                throw error;
            }

            if (!data || !data.success || !data.stats) {
                console.error('TokenUsageManager: Invalid response format:', data);
                throw new Error(data?.error || 'Invalid response format');
            }

            console.log('TokenUsageManager: Processing stats:', data.stats);

            // Get file tokens if files are present
            let fileTokens = 0;
            try {
                if (window.fileUploadManager?.uploadedFiles?.length > 0) {
                    fileTokens = window.fileUploadManager.uploadedFiles.reduce((sum, file) => {
                        return sum + (file.tokenCount || Math.ceil(file.size / 4));
                    }, 0);
                }
            } catch (error) {
                console.error('TokenUsageManager: Error calculating file tokens:', error);
                // Continue without file tokens rather than failing
            }

            // Combine message and file tokens
            const combinedStats = {
                ...data.stats,
                total_tokens: (data.stats.total_tokens || 0) + fileTokens,
                token_breakdown: {
                    ...data.stats.token_breakdown,
                    files: fileTokens
                }
            };

            // Update token usage percentage
            if (data.stats.model_limits?.max_tokens) {
                combinedStats.token_usage_percentage =
                    (combinedStats.total_tokens / data.stats.model_limits.max_tokens) * 100;
            }

            // Update UI with combined stats
            this.updateDisplay(combinedStats);

            // Update model-specific token limits, if provided
            if (data.stats.model_limits) {
                console.log('TokenUsageManager: Updating model limits:', data.stats.model_limits);
                this.updateModelLimits(data.stats.model_limits);
            }

            console.log('TokenUsageManager: Stats updated successfully');
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
        if (!window.utils) {
            // Fallback error display if utils not available
            if (this.elements.container) {
                const errorElement = document.createElement('div');
                errorElement.className = 'text-red-500 text-sm mt-2';
                errorElement.textContent = message;
                this.elements.container.appendChild(errorElement);
                setTimeout(() => errorElement.remove(), 5000);
            }
            return;
        }

        // Use utils.showFeedback for consistent error display
        window.utils.showFeedback(message, 'error', {
            duration: 5000,
            position: 'top'
        });

        // Also show error in the token usage container
        if (this.elements.container) {
            const errorElement = document.createElement('div');
            errorElement.className = 'text-red-500 text-sm mt-2';
            errorElement.textContent = message;
            this.elements.container.appendChild(errorElement);

            // Remove the container error after 5 seconds
            setTimeout(() => {
                errorElement.remove();
            }, 5000);
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
        const breakdown = stats.token_breakdown || { user: 0, assistant: 0, system: 0, files: 0 };

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

        // Create or update the token breakdown display
        const breakdownContainer = document.querySelector('.token-breakdown');
        if (breakdownContainer) {
            breakdownContainer.innerHTML = `
                <span class="flex items-center">
                    <i class="fas fa-user text-xs mr-1"></i>
                    <span id="user-tokens" aria-label="User tokens">${(breakdown.user || 0).toLocaleString()}</span>
                </span>
                <span class="flex items-center">
                    <i class="fas fa-robot text-xs mr-1"></i>
                    <span id="assistant-tokens" aria-label="Assistant tokens">${(breakdown.assistant || 0).toLocaleString()}</span>
                </span>
                <span class="flex items-center">
                    <i class="fas fa-cog text-xs mr-1"></i>
                    <span id="system-tokens" aria-label="System tokens">${(breakdown.system || 0).toLocaleString()}</span>
                </span>
                <span class="flex items-center">
                    <i class="fas fa-file text-xs mr-1"></i>
                    <span id="file-tokens" aria-label="File tokens">${(breakdown.files || 0).toLocaleString()}</span>
                </span>
            `;
        }

        console.log('TokenUsageManager: Display update complete');
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
            if (
                this.elements.container &&
                !this.elements.container.classList.contains('hidden')
            ) {
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
    async handleNewMessage() {
        try {
            await this.updateStats();
        } catch (error) {
            console.error('TokenUsageManager: Error updating stats after new message:', error);
        }
    }
}

// Make the class available globally
if (!window.TokenUsageManager) {
    window.TokenUsageManager = TokenUsageManager;
}
