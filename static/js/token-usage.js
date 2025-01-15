// At the top of chat.js, after the imports
let messageInput, sendButton, chatBox, editTitleBtn, uploadButton, mobileUploadButton, fileInput;

function initializeElements() {
    // Cache DOM elements
    messageInput = document.getElementById('message-input');
    sendButton = document.getElementById('send-button');
    chatBox = document.getElementById('chat-box');
    editTitleBtn = document.getElementById('edit-title-btn');
    uploadButton = document.getElementById('upload-button');
    mobileUploadButton = document.getElementById('mobile-upload-button');
    fileInput = document.getElementById('file-input');

    // Log which elements were found
    console.log('Elements initialized:', {
        messageInput: !!messageInput,
        sendButton: !!sendButton,
        chatBox: !!chatBox,
        editTitleBtn: !!editTitleBtn,
        uploadButton: !!uploadButton,
        mobileUploadButton: !!mobileUploadButton,
        fileInput: !!fileInput
    });

    return {
        messageInput, sendButton, chatBox, editTitleBtn, 
        uploadButton, mobileUploadButton, fileInput
    };
}

function attachEventListeners() {
    console.log('Attaching event listeners');
    
    // Message input handlers
    if (messageInput) {
        console.log('Attaching messageInput listeners');
        messageInput.addEventListener('input', debounce(handleMessageInput, 100));
        messageInput.addEventListener('keydown', handleMessageKeydown);
    }

    // Send button handler
    if (sendButton) {
        console.log('Attaching sendButton listener');
        sendButton.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Send button clicked');
            sendMessage();
        });
    }

    // Edit title button handler
    if (editTitleBtn) {
        console.log('Attaching editTitleBtn listener');
        editTitleBtn.addEventListener('click', handleEditTitle);
    }

    // File upload handlers
    if (uploadButton && fileInput) {
        console.log('Attaching uploadButton listener');
        uploadButton.addEventListener('click', function(e) {
            e.preventDefault();
            fileInput.click();
        });
    }

    if (mobileUploadButton && fileInput) {
        console.log('Attaching mobileUploadButton listener');
        mobileUploadButton.addEventListener('click', function(e) {
            e.preventDefault();
            fileInput.click();
        });
    }

    if (fileInput) {
        console.log('Attaching fileInput listener');
        fileInput.addEventListener('change', handleFileSelection);
    }
}

function handleFileSelection(e) {
    const files = Array.from(e.target.files || []);
    if (window.fileUploadManager) {
        const { validFiles, errors } = window.fileUploadManager.processFiles(files);
        if (errors.length > 0) {
            errors.forEach(error => window.utils.showFeedback(error.errors.join(', '), 'error'));
        }
        if (validFiles.length > 0) {
            window.fileUploadManager.uploadedFiles.push(...validFiles);
            window.fileUploadManager.renderFileList();
        }
    }
}

async function handleEditTitle() {
    try {
        const chatTitle = document.getElementById('chat-title');
        const currentTitle = chatTitle?.textContent?.split('-')[0].trim() || 'New Chat';
        const newTitle = prompt('Enter new chat title:', currentTitle);

        if (!newTitle || newTitle === currentTitle) return;

        const response = await window.utils.fetchWithCSRF(
            `/chat/update_chat_title/${window.CHAT_CONFIG.chatId}`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ title: newTitle.trim() })
            }
        );

        if (response.success) {
            const modelName = chatTitle.textContent.split('-')[1]?.trim() || '';
            chatTitle.textContent = `${newTitle} ${modelName ? '- ' + modelName : ''}`;
            window.utils.showFeedback('Title updated successfully', 'success');
        } else {
            throw new Error(response.error || 'Failed to update title');
        }
    } catch (error) {
        window.utils.showFeedback(error.message, 'error');
    }
}
        this.updateInterval = null;
        this.initialize();
    }

    initialize() {
        // Add event listeners
        if (this.elements.toggleBtn) {
            this.elements.toggleBtn.addEventListener('click', () => this.toggleDisplay());
        }
        if (this.elements.refreshBtn) {
            this.elements.refreshBtn.addEventListener('click', () => this.updateStats());
        }

        // Start periodic updates
        this.startPeriodicUpdates();
    }

    toggleDisplay() {
        if (this.elements.container) {
            this.elements.container.classList.toggle('hidden');
            if (!this.elements.container.classList.contains('hidden')) {
                this.updateStats();
            }
        }
    }

    async updateStats() {
        if (this.elements.container && !this.elements.container.classList.contains('hidden')) {
            try {
                // Get current model from the select element
                const modelSelect = document.getElementById('model-select');
                const modelId = modelSelect?.value;
                
                const response = await fetch(`/stats/${this.chatId}?model_id=${modelId || ''}`);
                const data = await response.json();

                if (data.success && data.stats) {
                    this.updateDisplay(data.stats);
                    
                    // Update model-specific token limits
                    if (data.stats.model_limits) {
                        this.updateModelLimits(data.stats.model_limits);
                    }
                }
            } catch (error) {
                console.error('Error fetching token stats:', error);
                this.showError('Failed to update token usage');
            }
        }
    }

    updateModelLimits(limits) {
        const { max_tokens, max_completion_tokens } = limits;
        
        // Update progress bar max value
        if (this.elements.progress) {
            this.elements.progress.setAttribute('aria-valuemax', max_tokens);
        }
        
        // Update token limit display
        if (this.elements.tokensLimit) {
            this.elements.tokensLimit.textContent = `/ ${max_tokens.toLocaleString()} max`;
        }
        
        // Store limits for real-time calculations
        this.currentLimits = limits;
    }

    showError(message) {
        const errorElement = document.createElement('div');
        errorElement.className = 'text-red-500 text-sm mt-2';
        errorElement.textContent = message;
        
        // Add error message to container
        if (this.elements.container) {
            this.elements.container.appendChild(errorElement);
            
            // Remove error after timeout
            setTimeout(() => {
                errorElement.remove();
            }, 5000);
        }
    }

    updateDisplay(stats) {
        const limit = stats.token_limit;
        const used = stats.total_tokens;
        const percentage = stats.token_usage_percentage;

        // Update progress bar
        if (this.elements.progress) {
            this.elements.progress.style.width = `${Math.min(percentage, 100)}%`;
            this.updateProgressColor(percentage);
        }

        // Update counts
        if (this.elements.tokensUsed) {
            this.elements.tokensUsed.textContent = `${used.toLocaleString()} tokens used`;
        }
        if (this.elements.tokensLimit) {
            this.elements.tokensLimit.textContent = `/ ${limit.toLocaleString()} max`;
        }
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

    startPeriodicUpdates() {
        this.updateInterval = setInterval(() => {
            if (this.elements.container && !this.elements.container.classList.contains('hidden')) {
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
/* static/js/token-usage.js */

// Expose TokenUsageManager globally
window.TokenUsageManager = TokenUsageManager;
