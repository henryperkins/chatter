(() => {
    'use strict';

    // Declare a variable for scroll animation frames to avoid reference errors
    let scrollFrame = null;

    const CONFIG = {
        DEPENDENCY_TIMEOUT: 5000,
        STREAM_UPDATE_INTERVAL: 100,
        MAX_DEPENDENCY_ATTEMPTS: 50, 
        O_SERIES_MODELS: ['o3-mini', 'o1', 'o1-mini', 'o1-preview'],
        DEBUG: true
    };

    function logDebug(...args) {
        if (window.monitoring) {
            window.monitoring.log('debug', ...args);
        }
    }

    // 1. Visual viewport resize handling for on-screen keyboard:
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => {
            const inputBar = document.getElementById('chat-input');
            if (!inputBar) return;
            const viewport = window.visualViewport;
            // Adjust the bottom of the input bar so it stays visible above the virtual keyboard
            inputBar.style.bottom = `${viewport.height - viewport.offsetTop}px`;
        });
    }

    // 2. Swipe navigation on chat box
    (() => {
        const chatBox = document.getElementById('chat-box');
        if (!chatBox) return;

        let touchStartX = 0;
        let touchEndX = 0;
        const SWIPE_THRESHOLD = 50; // px

        chatBox.addEventListener('touchstart', (e) => {
            touchStartX = e.touches[0].clientX;
        }, { passive: true });

        chatBox.addEventListener('touchend', (e) => {
            touchEndX = e.changedTouches[0].clientX;
            const deltaX = touchEndX - touchStartX;
            if (Math.abs(deltaX) > SWIPE_THRESHOLD) {
                if (deltaX > 0) {
                    // Swipe right
                    // TODO: Implement "previous chat" logic if desired
                    console.debug('Swiped right in chat box');
                } else {
                    // Swipe left
                    // TODO: Implement "next chat" logic if desired
                    console.debug('Swiped left in chat box');
                }
            }
        }, { passive: true });
    })();

    // 3. IntersectionObserver-based message virtualization (basic example):
    (() => {
        if (!('IntersectionObserver' in window)) return; // gracefully degrade

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // Reveal this message container
                    entry.target.style.visibility = 'visible';
                    // Additional re-render logic could go here if you truly remove DOM content below
                } else {
                    // Hide message container
                    // If you actually want to free memory, you'd remove the content:
                    // entry.target.innerHTML = '';
                    // but you'd also need to restore it later when re-intersecting.
                    entry.target.style.visibility = 'hidden';
                }
            });
        }, { threshold: 0.1 });

        document.querySelectorAll('.message-container').forEach(el => {
            observer.observe(el);
        });
    })();

    // Create new chat function
    async function createNewChat() {
        try {
            const sendBtn = document.getElementById('new-chat-btn');
            if (sendBtn) sendBtn.disabled = true;
        
            const response = await fetch('/chat/new', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': window.CHAT_CONFIG?.csrfToken,
                    'Content-Type': 'application/json'
                }
            });
        
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to create new chat');
            }
        
            const data = await response.json();
            if (data.success && data.chat_id) {
                // Force full page load to initialize new chat
                window.location.href = `/chat/chat_interface?chat_id=${data.chat_id}&new=true`;
            } else {
                throw new Error('Invalid response from server');
            }
        } catch (error) {
            console.error('New chat error:', error);
            window.MessageRenderer.showError(`Failed to create chat: ${error.message}`);
        } finally {
            const sendBtn = document.getElementById('new-chat-btn');
            if (sendBtn) sendBtn.disabled = false;
        }
    }

    function initializeNewChatButton() {
        const newChatBtn = document.getElementById('new-chat-btn');
        if (newChatBtn) {
            newChatBtn.addEventListener('click', (e) => {
                e.preventDefault();
                createNewChat();
            });
        }
    }

    // Mobile chat selector handler
    document.getElementById('mobile-chat-selector')?.addEventListener('change', function(e) {
        const chatId = e.target.value;
        if (chatId === 'new') {
            createNewChat();
        } else {
            window.location.href = `/chat/chat_interface?chat_id=${chatId}`;
        }
    });

    // New chat button handler
    document.getElementById('new-chat-btn')?.addEventListener('click', createNewChat);

    async function handleNormalResponse(formData) {
        // Same base JSON payload as handleStreamingResponse, but no "stream: true"
        const message = formData.get('message') || '';
        const jsonData = {
            message,
            chat_id: window.CHAT_CONFIG.chatId
        };

        const response = await fetch('/chat/send', {
            method: 'POST',
            body: JSON.stringify(jsonData),
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'api-key': window.CHAT_CONFIG.azureToken,
                'Content-Type': 'application/json',
                'X-CSRFToken': window.CHAT_CONFIG.csrfToken
            }
        });

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        const data = await response.json();
        if (data.error) {
            throw new Error(data.error);
        }

        // data.message.content holds the assistant's reply
        const content = data.message?.content || '';
        await window.MessageRenderer.appendAssistantMessage(content, /* isStreaming= */ false);

        // Immediately show a quick success toast
        window.MessageRenderer.showSuccess('Assistant responded successfully');
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
                const chatBox = document.getElementById('chat-box');
                if (!chatBox) continue;

                const scrollPos = chatBox.scrollTop;
                const isNearBottom = chatBox.scrollHeight - chatBox.clientHeight - scrollPos < 100;

                if (isNearBottom) {
                    cancelAnimationFrame(scrollFrame);
                    scrollFrame = requestAnimationFrame(() => {
                        chatBox.scrollTop = chatBox.scrollHeight;
                    });
                }
            }

            // Final render with Markdown + syntax highlighting
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
            window.MessageRenderer.showError(`API Error: ${error.message}`);
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
            window.MessageRenderer.showError('Chat interface not properly initialized');
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
                    window.MessageRenderer.showError('File upload failed', uploadError.file);
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

            const modelSelect = document.getElementById('model-select');
            let modelSupportsStreaming = false;
            let isOSeriesModel = false;
            
            if (modelSelect && modelSelect.selectedOptions.length) {
                const selectedOption = modelSelect.selectedOptions[0];
                const modelType = selectedOption.dataset.modelType;
                
                // Check if it's an o-series model
                isOSeriesModel = CONFIG.O_SERIES_MODELS.includes(modelType);
                
                // Only o3-mini supports streaming
                modelSupportsStreaming = modelType === 'o3-mini';
                
                window.CHAT_CONFIG.isOSeriesModel = isOSeriesModel;
            }

            window.MessageRenderer.appendUserMessage(message, uploadedFiles);
            messageInput.value = '';
            window.fileUploadManager?.clearFiles();

            window.MessageRenderer.showTypingIndicator();
            if (modelSupportsStreaming) {
                await handleStreamingResponse(formData);
            } else {
                await handleNormalResponse(formData);
            }

            if (window.tokenUsageManager) {
                await window.tokenUsageManager.handleNewMessage();
            }
        } catch (error) {
            window.monitoring?.logError('Error in sendMessage:', error);
            window.MessageRenderer.showError(error.message || 'Failed to send message');
        } finally {
            sendButton.disabled = false;
            window.MessageRenderer.removeTypingIndicator();
        }
    }

    async function startChat() {
        try {
            initializeNewChatButton();
            const configDiv = document.getElementById('chat-config');
            if (!configDiv) {
                throw new Error('Chat configuration not found');
            }
            window.CHAT_CONFIG.isOSeriesModel = false;

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
                window.MessageRenderer.showError('Failed to initialize chat components: ' + error.message);
                return;
            }

            if (window.fileUploadManager) {
                await window.fileUploadManager.initializeFileUpload();
            }

            const modelSelect = document.getElementById('model-select');
            if (modelSelect) {
                modelSelect.addEventListener('change', async () => {
                    // Update o-series model status
                    const selectedOption = modelSelect.selectedOptions[0];
                    const modelType = selectedOption.dataset.modelType;
                    window.CHAT_CONFIG.isOSeriesModel = CONFIG.O_SERIES_MODELS.includes(modelType);
                    
                    // Update model in backend
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
                            window.MessageRenderer.showSuccess('Chat model updated');
                        } else {
                            window.MessageRenderer.showError(data.error || 'Failed to update chat model');
                        }
                    } catch (err) {
                        window.MessageRenderer.showError('Failed to update chat model');
                    }
                });
            }

            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            const chatForm = document.getElementById('chat-form');
            
            if (chatForm) {
                chatForm.addEventListener('submit', (e) => {
                    e.preventDefault();
                    sendMessage(e);
                });
            }

            if (messageInput) {
                // Debounce Enter presses
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
                        sendMessage(e);
                    }
                }, 100);

                messageInput.addEventListener('keydown', debouncedKeydown);
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
                            window.MessageRenderer.showSuccess('Chat deleted');
                            window.location.href = '/chat/interface';
                        } else {
                            window.MessageRenderer.showError(data.error);
                        }
                    } catch (err) {
                        window.MessageRenderer.showError('Delete failed');
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
                            window.MessageRenderer.showSuccess('Chat title updated');
                            location.reload();
                        } else {
                            window.MessageRenderer.showError(data.error);
                        }
                    } catch (err) {
                        window.MessageRenderer.showError('Failed to update chat title');
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
                        // Placeholder regeneration logic
                        window.MessageRenderer.showSuccess('Regeneration triggered (feature not fully implemented yet)');
                    }
                });
            });

        } catch (error) {
            window.monitoring?.logError('Failed to initialize chat:', error);
            window.MessageRenderer.showError(error.message);
        }
    }

    window.addEventListener('load', startChat);
})();
