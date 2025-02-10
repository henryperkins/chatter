(() => {
    'use strict';

    const CONFIG = {
        DEPENDENCY_TIMEOUT: 5000,
        STREAM_UPDATE_INTERVAL: 100,
        MAX_DEPENDENCY_ATTEMPTS: 50,
        DEBUG: true
    };

    function logDebug(...args) {
        if (window.monitoring) {
            window.monitoring.log('debug', ...args);
        }
    }

    function showTypingIndicator() {
        if (window.monitoring) {
            window.monitoring.mark('typingStart');
        }
    }

    function removeTypingIndicator() {
        if (window.monitoring) {
            window.monitoring.mark('typingEnd');
            window.monitoring.measure('typingDuration', 'typingStart', 'typingEnd');
        }
    }

    function showError(message, file = null) {
        if (message.includes('Authentication Error')) {
            message = message.replace('Authentication Error:', '🔑 Authentication Error:');
        }

        let errorMessage = message;
        if (file) {
            errorMessage = `[${file.name}] ${message} (${(file.size / 1024 / 1024).toFixed(2)}MB)`;
        }

        if (window.showAlert) {
            window.showAlert(errorMessage, 'error', 10000);
        } else {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'pointer-events-auto fixed top-20 left-1/2 transform -translate-x-1/2 bg-red-100 dark:bg-red-900/50 text-red-900 dark:text-red-100 px-6 py-4 rounded-lg shadow-xl border-2 border-red-500/50 z-[2200] max-w-[90%] sm:max-w-lg';
            errorDiv.innerHTML = `
                <div class='flex items-center gap-3'>
                    <i class='fas fa-exclamation-circle text-lg'></i>
                    <p class='text-sm font-medium flex-1'>${errorMessage}</p>
                    <button onclick='this.parentElement.parentElement.remove()' class='hover:opacity-80 transition-opacity'>
                        <i class='fas fa-times'></i>
                    </button>
                </div>
            `;
            document.body.appendChild(errorDiv);
            setTimeout(() => {
                if (errorDiv.parentElement) {
                    errorDiv.remove();
                }
            }, 10000);
        }
    }

    function appendUserMessage(message, files = []) {
        if (!message || typeof message !== 'string') {
            window.monitoring?.logError('Invalid user message content.');
            return;
        }

        const chatBox = document.getElementById('chat-box');
        if (!chatBox) {
            window.monitoring?.logError('Chat box not found');
            return;
        }

        const messageDiv = window.MessageRenderer.renderUserMessage(message, files);
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    async function appendAssistantMessage(message, isStreaming = false, existingDiv = null, files = []) {
        if (!message) return;
        logDebug('Appending assistant message:', message);

        const chatBox = document.getElementById('chat-box');
        if (!chatBox) {
            window.monitoring?.logError('Chat box not found');
            return;
        }

        // Wait for dependencies
        let attempts = 0;
        while ((!window.md || !window.DOMPurify) && attempts < CONFIG.MAX_DEPENDENCY_ATTEMPTS) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }

        if (!window.md || !window.DOMPurify) {
            window.monitoring?.logError('Required dependencies not available.');
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = '<p class=\'text-red-500\'>Error: Required dependencies not available. Please refresh the page.</p>';
            chatBox.insertBefore(errorDiv, chatBox.firstChild);
            return;
        }

        try {
            const textContent = (typeof message === 'string') ? message : message.content;
            let messageDiv;

            if (!existingDiv) {
                messageDiv = window.MessageRenderer.renderAssistantMessage(textContent, isStreaming);
                chatBox.appendChild(messageDiv);
            } else {
                messageDiv = existingDiv;
                window.MessageRenderer.finalizeAssistantMessage(messageDiv, textContent);
            }

            chatBox.scrollTop = chatBox.scrollHeight;
            return messageDiv;
        } catch (error) {
            window.monitoring?.logError('Error appending assistant message:', error);
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = `<p class='text-red-500'>Error creating message: ${error.message}</p>`;
            chatBox.appendChild(errorDiv);
        }
    }

    async function handleStreamingResponse(formData) {
        let accumulatedContent = '';
        let messageDiv = null;
        let buffer = '';

        try {
            const message = formData.get('message');
            const files = formData.getAll('files[]') || [];
            const hasMessage = message && message.trim().length > 0;
            const hasFiles = files && files.length > 0;

            if (!hasMessage && !hasFiles) {
                throw new Error('Please provide a message or upload files.');
            }

            const jsonData = {
                message: message || '',
                files: [],
                chat_id: window.CHAT_CONFIG.chatId,
                stream: true
            };

            const response = await fetch('/chat/send', {
                method: 'POST',
                body: JSON.stringify(jsonData),
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'api-key': window.CHAT_CONFIG.azureToken,
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                    'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                }
            });

            if (!response.ok) {
                const text = await response.text();
                let errorMessage;
                try {
                    const errorData = JSON.parse(text);
                    errorMessage = errorData.error || `Server error: ${response.status}`;
                } catch {
                    errorMessage = `Server error: ${response.status}`;
                }
                throw new Error(errorMessage);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            let streamComplete = false;
            let updateQueue = [];
            let updateScheduled = false;
            
            const processUpdate = () => {
                if (updateQueue.length > 0) {
                    const latestContent = updateQueue[updateQueue.length - 1];
                    accumulatedContent = latestContent;
                    
                    if (!messageDiv) {
                        messageDiv = window.MessageRenderer.renderAssistantMessage(latestContent, true);
                        document.getElementById('chat-box').appendChild(messageDiv);
                    } else {
                        const contentContainer = messageDiv.querySelector('[data-role="assistant-message"]');
                        if (contentContainer) {
                            contentContainer.textContent = latestContent;
                        }
                    }
                    
                    updateQueue = [];
                    updateScheduled = false;
                }
            };

            while (!streamComplete) {
                const { done, value } = await reader.read();
                if (done) {
                    streamComplete = true;
                    continue;
                }

                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split('\n\n');
                buffer = events.pop() || '';

                for (const event of events) {
                    const match = event.match(/^data: (.*)/);
                    if (!match) continue;

                    try {
                        const data = JSON.parse(match[1]);
                        if (data.error) throw new Error(data.error);
                        
                        if (data.content) {
                            accumulatedContent += data.content;
                            updateQueue.push(accumulatedContent);
                            
                            if (!updateScheduled) {
                                updateScheduled = true;
                                requestAnimationFrame(processUpdate);
                            }
                        }
                    } catch (err) {
                        throw new Error(`Stream parsing error: ${err.message}`);
                    }
                }

                // Debounce scroll updates
                if (!streamComplete) {
                    const chatBox = document.getElementById('chat-box');
                    const scrollPos = chatBox.scrollTop;
                    const isNearBottom = chatBox.scrollHeight - chatBox.clientHeight - scrollPos < 100;
                    
                    if (isNearBottom) {
                        cancelAnimationFrame(scrollFrame);
                        const scrollFrame = requestAnimationFrame(() => {
                            chatBox.scrollTop = chatBox.scrollHeight;
                        });
                    }
                }
            }
            
            // Final render with Markdown and syntax highlighting
            if (messageDiv) {
                window.MessageRenderer.finalizeAssistantMessage(messageDiv, accumulatedContent);
            }

            if (window.monitoring) {
                window.monitoring.mark('streamEnd');
                window.monitoring.measure('streamDuration', 'streamStart', 'streamEnd');
            }

        } catch (error) {
            if (window.monitoring) {
                window.monitoring.logError('Streaming failed:', error);
            }
            showError(`API Error: ${error.message}`);
            if (messageDiv) {
                messageDiv.remove();
            }
        }
    }

    async function sendMessage(event) {
        if (event) {
            event.preventDefault();
        }

        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');

        if (!messageInput || !sendButton) {
            showError('Chat interface not properly initialized');
            return;
        }
        if (sendButton.disabled) return;

        sendButton.disabled = true;

        try {
            const message = messageInput.value.trim();
            const hasFiles = window.fileUploadManager?.uploadedFiles?.length > 0;
            let uploadedFiles = [];

            if (hasFiles) {
                try {
                    uploadedFiles = await window.fileUploadManager.uploadFiles();
                } catch (uploadError) {
                    showError('File upload failed', uploadError.file);
                    throw uploadError;
                }
            }

            const formData = new FormData();
            formData.append('message', message);

            if (hasFiles) {
                window.fileUploadManager.uploadedFiles.forEach(file => {
                    formData.append('files[]', file);
                });
            }

            appendUserMessage(message, uploadedFiles);
            messageInput.value = '';
            window.fileUploadManager?.clearFiles();

            showTypingIndicator();
            await handleStreamingResponse(formData);

            if (window.tokenUsageManager) {
                await window.tokenUsageManager.handleNewMessage();
            }
        } catch (error) {
            window.monitoring?.logError('Error in sendMessage:', error);
            showError(error.message || 'Failed to send message');
        } finally {
            sendButton.disabled = false;
            removeTypingIndicator();
        }
    }

    async function startChat() {
        try {
            const configDiv = document.getElementById('chat-config');
            if (!configDiv) {
                throw new Error('Chat configuration not found');
            }

            // Wait for MessageRenderer to be available
            let attempts = 0;
            while (!window.MessageRenderer && attempts < CONFIG.MAX_DEPENDENCY_ATTEMPTS) {
                await new Promise(resolve => setTimeout(resolve, 100));
                attempts++;
            }

            if (!window.MessageRenderer) {
                throw new Error('MessageRenderer not available');
            }

            try {
                const FileUploadManagerClass = window.FileUploadManager;
                if (!FileUploadManagerClass) {
                    throw new Error('FileUploadManager class not loaded');
                }
                if (!window.fileUploadManager) {
                    const uploadButton = document.getElementById('file-upload');
                    window.fileUploadManager = new FileUploadManagerClass(
                        configDiv.dataset.chatId,
                        configDiv.dataset.userId,
                        uploadButton
                    );
                }

                const TokenUsageManagerClass = window.TokenUsageManager;
                if (!TokenUsageManagerClass) {
                    throw new Error('TokenUsageManager class not loaded');
                }
                if (!window.tokenUsageManager && window.CHAT_CONFIG?.chatId) {
                    window.tokenUsageManager = new TokenUsageManagerClass(window.CHAT_CONFIG);
                    await window.tokenUsageManager.initialize();
                }
            } catch (error) {
                window.monitoring?.logError('Component init failed', error);
                showError('Failed to initialize chat components: ' + error.message);
                return;
            }

            if (window.fileUploadManager) {
                await window.fileUploadManager.initializeFileUpload();
            }

            const modelSelect = document.getElementById('model-select');
            if (modelSelect) {
                modelSelect.addEventListener('change', async () => {
                    const newModelId = modelSelect.value;
                    const chatId = window.CHAT_CONFIG.chatId;
                    try {
                        const resp = await fetch('/chat/update_model', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                            },
                            body: JSON.stringify({ chat_id: chatId, model_id: newModelId })
                        });
                        const data = await resp.json();
                        if (data.success) {
                            window.showAlert('Chat model updated', 'success');
                        } else {
                            window.showAlert(data.error || 'Failed to update chat model', 'error');
                        }
                    } catch (err) {
                        window.showAlert('Failed to update chat model', 'error');
                    }
                });
            }

            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            if (messageInput && sendButton) {
                const debounce = (func, wait) => {
                    let timeout;
                    return function executedFunction(...args) {
                        const later = () => {
                            clearTimeout(timeout);
                            func(...args);
                        };
                        clearTimeout(timeout);
                        timeout = setTimeout(later, wait);
                    };
                };

                const debouncedKeydown = debounce(e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                    }
                }, 100);

                messageInput.addEventListener('keydown', debouncedKeydown);
                sendButton.addEventListener('click', sendMessage);
            }

            document.querySelectorAll('button[aria-label="Delete chat"]').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const chatId = btn.getAttribute('data-chat-id');
                    if (!chatId) return;
                    if (!confirm('Are you sure you want to delete this chat?')) return;
                    try {
                        const resp = await fetch(`/chat/delete_chat/${chatId}`, {
                            method: 'DELETE',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                            }
                        });
                        const data = await resp.json();
                        if (data.success) {
                            window.showAlert('Chat deleted', 'success');
                            window.location.href = '/chat/interface';
                        } else {
                            window.showAlert(data.error, 'error');
                        }
                    } catch (err) {
                        window.showAlert('Delete failed', 'error');
                    }
                });
            });

            const editTitleBtn = document.getElementById('edit-title-btn');
            if (editTitleBtn) {
                editTitleBtn.addEventListener('click', async () => {
                    const newTitle = prompt('Enter new chat title:');
                    if (!newTitle || newTitle.trim() === '') return;
                    try {
                        const resp = await fetch(`/chat/update_chat_title/${window.CHAT_CONFIG.chatId}`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                            },
                            body: JSON.stringify({ title: newTitle.trim() })
                        });
                        const data = await resp.json();
                        if (data.success) {
                            window.showAlert('Chat title updated', 'success');
                            location.reload();
                        } else {
                            window.showAlert(data.error, 'error');
                        }
                    } catch (err) {
                        window.showAlert('Failed to update chat title', 'error');
                    }
                });
            }

            document.querySelectorAll('.copy-button').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const rawContent = btn.getAttribute('data-raw-content');
                    if (rawContent && window.utils?.copyToClipboard) {
                        window.utils.copyToClipboard(rawContent);
                    }
                });
            });

            document.querySelectorAll('.regenerate-button').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (confirm('Do you want to regenerate the assistant response?')) {
                        window.showAlert('Regeneration triggered (feature not fully implemented yet)', 'info');
                    }
                });
            });

        } catch (error) {
            window.monitoring?.logError('Failed to initialize chat:', error);
            showError(error.message);
        }
    }

    window.addEventListener('load', startChat);
})();
