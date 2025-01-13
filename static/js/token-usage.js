
class TokenUsageManager {
    constructor(config) {
        this.chatId = config.chatId;
        this.elements = {
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
        this.updateInterval = null;
        this.initialize();
    }

    initialize() {
        // Add event listeners
        this.elements.toggleBtn.addEventListener('click', () => this.toggleDisplay());
        this.elements.refreshBtn.addEventListener('click', () => this.updateStats());

        // Start periodic updates
        this.startPeriodicUpdates();
    }

    toggleDisplay() {
        this.elements.container.classList.toggle('hidden');
        if (!this.elements.container.classList.contains('hidden')) {
            this.updateStats();
        }
    }

    async updateStats() {
        if (this.elements.container.classList.contains('hidden')) return;

        try {
            const response = await fetch(`/stats/${this.chatId}`);
            const data = await response.json();
            
            if (data.success && data.stats) {
                this.updateDisplay(data.stats);
            }
        } catch (error) {
            console.error('Error fetching token stats:', error);
        }
    }

    updateDisplay(stats) {
        const limit = stats.token_limit;
        const used = stats.total_tokens;
        const percentage = stats.token_usage_percentage;

        // Update progress bar
        this.elements.progress.style.width = `${Math.min(percentage, 100)}%`;
        this.updateProgressColor(percentage);

        // Update counts
        this.elements.tokensUsed.textContent = `${used.toLocaleString()} tokens used`;
        this.elements.tokensLimit.textContent = `/ ${limit.toLocaleString()} max`;
        this.elements.userTokens.textContent = stats.token_breakdown.user.toLocaleString();
        this.elements.assistantTokens.textContent = stats.token_breakdown.assistant.toLocaleString();
        this.elements.systemTokens.textContent = stats.token_breakdown.system.toLocaleString();
    }

    updateProgressColor(percentage) {
        this.elements.progress.classList.remove('bg-blue-600', 'bg-yellow-600', 'bg-red-600');
        if (percentage > 90) {
            this.elements.progress.classList.add('bg-red-600');
        } else if (percentage > 75) {
            this.elements.progress.classList.add('bg-yellow-600');
        } else {
            this.elements.progress.classList.add('bg-blue-600');
        }
    }

    startPeriodicUpdates() {
        this.updateInterval = setInterval(() => {
            if (!this.elements.container.classList.contains('hidden')) {
                this.updateStats();
            }
        }, 30000); // Update every 30 seconds if visible
    }

    stopPeriodicUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    // Method to be called after each chat message
    handleNewMessage() {
        this.updateStats();
    }
}

// Export the class
export default TokenUsageManager;
