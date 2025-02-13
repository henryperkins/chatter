(() => {
    (() => {
        class TokenUsageManager {
            constructor(config) {
                // Prevent multiple instances
                console.debug('TokenUsageManager: Constructor called');
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
                this.tokenCount = 0;
                this.lastUpdateTime = 0;
                this.minUpdateInterval = 5000; // Minimum time between updates in ms
                this.maxRetries = 3;
                this.backoffDelay = 1000; // Initial backoff delay in ms
                this.isRateLimited = false;
                this.rateLimitEndTime = 0;

                // Set up element references
                this.elements = this.initializeElements();

                // Store instance
                window.TokenUsageManager.instance = this;

                console.log('TokenUsageManager: New instance initialized with chatId:', this.chatId);
            }

            updateTokenCount(count) {
                if (!this.elements.tokensUsed) {
                    console.error('TokenUsageManager: tokensUsed element not found');
                    return;
                }
                this.tokenCount = count;
                this.elements.tokensUsed.textContent = this.tokenCount;
            }

            initializeElements() {
                return {
                    container: document.getElementById('token-usage'),
                    tokensUsed: document.getElementById('tokens-used'),
                    tokensLimit: document.getElementById('tokens-limit'),
                    tokensLeft: document.getElementById('tokens-left'),
                    userTokens: document.getElementById('user-tokens'),
                    assistantTokens: document.getElementById('assistant-tokens'),
                    systemTokens: document.getElementById('system-tokens')
                };
            }

            async initialize() {
                try {
                    console.debug('TokenUsageManager: Starting initialization', { config: this.config });
                    
                    // Check dependencies immediately instead of polling
                    if (!window.utils) throw new Error('Utils dependency not available');
                    if (!window.CHAT_CONFIG) throw new Error('CHAT_CONFIG dependency not available');

                    if (!window.utils || !window.CHAT_CONFIG) {
                        console.error('TokenUsageManager: Required dependencies not available after waiting');
                        throw new Error('Required dependencies not available after waiting');
                    }

                    console.log('TokenUsageManager: Dependencies loaded, proceeding with initialization');

                    if (this.chatId !== window.CHAT_CONFIG.chatId) {
                        console.warn('TokenUsageManager: Chat ID mismatch, updating to match config');
                        this.chatId = window.CHAT_CONFIG.chatId;
                    }

                    if (this.elements.container) {
                        this.elements.container.classList.remove('hidden');
                    }


                    await this.updateStats();
                    this.startPeriodicUpdates();

                    console.debug('TokenUsageManager: Initialization completed successfully');
                    return true;
                } catch (error) {
                    console.error('TokenUsageManager: Initialization failed:', error);
                    return false;
                }
            }

            async updateStats(forceUpdate = false) {
                try {
                    // Check dependencies and elements
                    if (!window.utils || !this.elements.container || !this.chatId) {
                        console.error('TokenUsageManager: Missing required dependencies or elements');
                        return;
                    }

                    // Check if we're rate limited
                    if (this.isRateLimited) {
                        const now = Date.now();
                        if (now < this.rateLimitEndTime) {
                            console.debug('TokenUsageManager: Still rate limited, skipping update');
                            return;
                        }
                        this.isRateLimited = false;
                    }

                    // Enforce minimum update interval unless forced
                    const now = Date.now();
                    const timeSinceLastUpdate = now - this.lastUpdateTime;
                    if (!forceUpdate && timeSinceLastUpdate < this.minUpdateInterval) {
                        console.debug('TokenUsageManager: Update throttled, too soon since last update');
                        return;
                    }

                    console.debug('TokenUsageManager: Starting stats update for chat', this.chatId);
                    const url = `/chat/stats/${this.chatId}`;

                    const response = await fetch(url, {
                        method: 'GET',
                        headers: {
                            'Accept': 'application/json',
                            'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                        },
                        credentials: 'same-origin'
                    });

                    if (response.status === 429) {
                        const retryAfter = parseInt(response.headers.get('Retry-After')) || 30;
                        this.handleRateLimit(retryAfter);
                        return;
                    }

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const data = await response.json();
                    if (!data || !data.success || !data.stats) {
                        throw new Error(data?.error || 'Invalid response format');
                    }

                    this.lastUpdateTime = now;
                    this.retryCount = 0;

                    const stats = data.stats;
                    const breakdown = stats.token_breakdown || {};
                    const limit = stats.model_limits?.max_tokens || 0;
                    const used = stats.total_tokens || 0;
                    const percentage = limit > 0 ? (used / limit) * 100 : 0;
                    const tokensLeft = limit - used;

                    // Update progress bar
                    if (this.elements.progress) {
                        const width = `${Math.min(percentage, 100)}%`;
                        this.elements.progress.style.width = width;
                        this.elements.progress.setAttribute('aria-valuenow', percentage);
                        this.updateProgressColor(percentage);
                        this.elements.progress.style.height = '0.5rem';  // Match new height
                    }

                    // Update token counts
                    if (this.elements.tokensUsed) {
                        this.elements.tokensUsed.textContent = used.toLocaleString();
                    }

                    if (this.elements.tokensLimit) {
                        this.elements.tokensLimit.textContent = `/ ${limit.toLocaleString()} max`;
                    }

                    // Update token breakdown
                    if (this.elements.userTokens) {
                        this.elements.userTokens.textContent = (breakdown.user || 0).toLocaleString();
                    }
                    if (this.elements.assistantTokens) {
                        this.elements.assistantTokens.textContent = (breakdown.assistant || 0).toLocaleString();
                    }
                    if (this.elements.systemTokens) {
                        this.elements.systemTokens.textContent = (breakdown.system || 0).toLocaleString();
                    }

                    console.debug('TokenUsageManager: Stats updated successfully');
                } catch (error) {
                    console.error('TokenUsageManager: Error updating stats:', error);
                    this.showError('Failed to update token usage');
                }
            }

            updateProgressColor(percentage) {
                if (this.elements.progress) {
                    this.elements.progress.classList.remove('bg-blue-600', 'bg-yellow-600', 'bg-red-600');

                    if (percentage > 90) {
                        this.elements.progress.classList.add('bg-red-500');
                    } else if (percentage > 75) {
                        this.elements.progress.classList.add('bg-yellow-500');
                    } else {
                        this.elements.progress.classList.add('bg-blue-600');
                    }
                }
            }

            showError(message) {
                if (!window.utils) {
                    if (this.elements.container) {
                        const errorElement = document.createElement('div');
                        errorElement.className = 'text-red-500 text-sm mt-2';
                        errorElement.textContent = message;
                        this.elements.container.appendChild(errorElement);
                        setTimeout(() => errorElement.remove(), 5000);
                    }
                    return;
                }

                window.utils.showFeedback(message, 'error', {
                    duration: 5000,
                    position: 'top'
                });
            }

            handleRateLimit(retryAfter) {
                this.isRateLimited = true;
                this.rateLimitEndTime = Date.now() + (retryAfter * 1000);
                
                // Update UI to show rate limit status
                if (this.elements.tokensUsed) {
                    this.elements.tokensUsed.innerHTML = `<span class="text-yellow-500">Rate limited</span>`;
                }
                
                console.debug(`TokenUsageManager: Rate limited, retry after ${retryAfter}s`);
                
                // Schedule a retry
                setTimeout(() => {
                    this.isRateLimited = false;
                    this.updateStats(true);
                }, retryAfter * 1000);
            }

            startPeriodicUpdates() {
                // Clear any existing interval
                this.stopPeriodicUpdates();
                
                this.updateInterval = setInterval(() => {
                    if (this.elements.container && 
                        !this.elements.container.classList.contains('hidden') &&
                        !this.isRateLimited) {
                        this.updateStats();
                    }
                }, 30000);
            }

            stopPeriodicUpdates() {
                if (this.updateInterval) {
                    clearInterval(this.updateInterval);
                    this.updateInterval = null;
                }
            }

            async handleNewMessage() {
                try {
                    if (this.isRateLimited) {
                        console.debug('TokenUsageManager: Skipping update due to rate limit');
                        return;
                    }
                    await this.updateStats(true);
                } catch (error) {
                    console.error('TokenUsageManager: Error updating stats after new message:', error);
                    if (error.message.includes('429')) {
                        this.handleRateLimit(30); // Default 30s backoff if no Retry-After header
                    }
                }
            }
        }

        console.debug('TokenUsageManager: Module loaded, exposing to window');
        // Expose to window
        window.TokenUsageManager = TokenUsageManager;
    })();
})();
