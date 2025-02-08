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

    async function handleStreamingResponse(formData) {
        let accumulatedContent = '';
        let messageDiv = null;
        let buffer = '';

        try {
            // Validate that we have a message or files
            const message = formData.get('message')?.trim() || '';
            const files = formData.getAll('files');

            if (!message && files.length === 0) {
                throw new Error('No message or files provided');
            }

            // Convert FormData to JSON while preserving structure
            const jsonData = {
                message: message,
                files: files,
                chat_id: window.CHAT_CONFIG.chatId,
                stream: true
            };

            // Add model if present
            const modelSelect = document.getElementById('model-select');
            if (modelSelect && modelSelect.value) {
                jsonData.model = modelSelect.value;
            }

            logDebug('Sending chat request:', {
                url: '/chat/send',
                method: 'POST',
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream'
                },
                body: jsonData
            });

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
                window.monitoring?.logError('Server error response:', {
                    status: response.status,
                    statusText: response.statusText,
                    headers: Object.fromEntries([...response.headers]),
                    body: text
                });
                throw new Error(errorMessage);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            let streamComplete = false;
            while (!streamComplete) {
                const { done, value } = await reader.read();
                if (done) {
                    streamComplete = true;
                    continue;
                }

                if (window.monitoring) {
                    window.monitoring.mark('chunkReceived');
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
                            if (!messageDiv) {
                                messageDiv = document.createElement('div');
                                document.getElementById('chat-box').appendChild(messageDiv);
                            }
                            await appendAssistantMessage({ content: accumulatedContent }, true, messageDiv);
                        }
                    } catch (error) {
                        throw new Error(`Stream parsing error: ${error.message}`);
                    }
                }

                const chatBox = document.getElementById('chat-box');
                chatBox.scrollTop = chatBox.scrollHeight;
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
            if (messageDiv) messageDiv.remove();
        }
    }

    async function appendAssistantMessage(message, isStreaming = false, existingDiv = null) {
        if (!message) return;
        logDebug('Appending assistant message:', message);
        const chatBox = document.getElementById('chat-box');
        if (!chatBox) {
            window.monitoring?.logError('Chat box not found');
            return;
        }

        let attempts = 0;
        while ((!window.md || !window.DOMPurify) && attempts < CONFIG.MAX_DEPENDENCY_ATTEMPTS) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }

        if (!window.md || !window.DOMPurify) {
            window.monitoring?.logError('Required dependencies not available.');
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = '<p class="text-red-500">Error: Required dependencies not available. Please refresh the page.</p>';
            chatBox.insertBefore(errorDiv, chatBox.firstChild);
            return;
        }

        try {
            const renderedHtml = typeof message === 'string' ? window.md.render(message) : message.content;
            const DOMPurifyOptions = {
                ALLOWED_TAGS: [
                    'p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote',
                    'a', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'br',
                    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del', 'input'
                ],
                ALLOWED_ATTRS: {
                    'a': ['href', 'title', 'target', 'rel', 'class'],
                    'span': ['class'],
                    'code': ['class'],
                    'pre': ['class'],
                    'div': ['class', 'style'],
                    'table': ['class'],
                    'th': ['class'],
                    'td': ['class'],
                    'input': ['type', 'checked', 'disabled'],
                    'li': ['class']
                },
                ADD_ATTR: ['target'],
                FORCE_BODY: true
            };

            const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, DOMPurifyOptions);
            let messageDiv;

            if (!existingDiv) {
                messageDiv = document.createElement('div');
                messageDiv.className = 'flex w-full mt-4 space-x-3 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl animate-slide-up';
            } else {
                messageDiv = existingDiv;
            }

            messageDiv.innerHTML = `
                <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-primary-500 to-secondary-600 flex items-center justify-center text-white shadow-soft" role="img" aria-label="Assistant avatar">
                    <i class="fas fa-robot text-sm"></i>
                </div>
                <div class="relative flex-1">
                    <div class="absolute right-2 top-2 flex items-center space-x-1 z-10 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        <button class="copy-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-soft" title="Copy to clipboard" aria-label="Copy message to clipboard" data-raw-content="${message.content ? message.content.replace(/"/g, '&quot;') : ''}">
                            <i class="fas fa-copy"></i>
                        </button>
                        ${!isStreaming
                            ? `<button class="regenerate-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-soft" title="Regenerate response" aria-label="Regenerate response">
                                <i class="fas fa-redo-alt"></i>
                               </button>`
                            : ''}
                    </div>
                    <div class="bg-gray-100/95 dark:bg-gray-800/95 p-5 rounded-r-lg rounded-bl-lg shadow-soft border border-gray-200/50 dark:border-gray-700/50">
                        <div class="prose dark:prose-invert prose-sm sm:prose-base lg:prose-lg max-w-none overflow-x-auto" data-role="assistant-message">
                            ${sanitizedHtml}
                        </div>
                    </div>
                    <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                        ${new Date().toLocaleTimeString()}
                    </span>
                </div>
            `;

            if (!existingDiv) {
                chatBox.appendChild(messageDiv);
            }

            if (window.Prism) {
                window.Prism.highlightAllUnder(messageDiv.querySelector('[data-role="assistant-message"]'));
            }
        } catch (error) {
            window.monitoring?.logError('Error appending assistant message:', error);
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = `<p class="text-red-500">Error creating message: ${error.message}</p>`;
            chatBox.appendChild(errorDiv);
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendUserMessage(message) {
        if (!message || typeof message !== 'string') {
            window.monitoring?.logError('Invalid message content.');
            return;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = 'flex w-full mt-4 space-x-3 max-w-[85%] sm:max-w-md md:max-w-2xl ml-auto justify-end animate-slide-up';
        messageDiv.innerHTML = `
            <div>
                <div class="relative bg-gradient-to-r from-primary-600/95 to-secondary-600/95 text-white p-4 rounded-l-lg rounded-br-lg shadow-soft hover:shadow-md transition-all duration-300 hover:-translate-y-0.5 border border-primary-500/10">
                    <p class="text-[15px] leading-relaxed break-words whitespace-pre-wrap">${message}</p>
                </div>
                <span class="text-xs text-gray-500 block mt-1">
                    ${new Date().toLocaleTimeString()}
                </span>
            </div>
        `;

        const chatBox = document.getElementById('chat-box');
        if (chatBox) {
            chatBox.appendChild(messageDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
        } else {
            window.monitoring?.logError('Chat box not found');
        }
    }

    async function renderInitialAssistantMessages() {
        const assistantMessageDivs = document.querySelectorAll('[data-role="assistant-message"]');
        if (!assistantMessageDivs.length) return;

        logDebug('Re-rendering existing messages:', assistantMessageDivs.length);
        let attempts = 0;
        while (!window.md && attempts < CONFIG.MAX_DEPENDENCY_ATTEMPTS) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }

        if (!window.md) {
            window.monitoring?.logError('markdown-it not available');
            assistantMessageDivs.forEach(div => {
                div.innerHTML = '<p class="text-red-500">Error: Markdown renderer not available. Please refresh the page.</p>';
            });
            return;
        }

        assistantMessageDivs.forEach(div => {
            try {
                const rawContent = div.getAttribute('data-content');
                if (!rawContent) return;

                const decodedContent = window.he ? window.he.decode(rawContent) : rawContent;
                const renderedHtml = window.md.render(decodedContent);
                const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, {
                    ALLOWED_TAGS: [
                        'p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote',
                        'a', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'br',
                        'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del', 'input'
                    ],
                    ALLOWED_ATTRS: {
                        'a': ['href', 'title', 'target', 'rel', 'class'],
                        'span': ['class'],
                        'code': ['class'],
                        'pre': ['class'],
                        'div': ['class', 'style'],
                        'table': ['class'],
                        'th': ['class'],
                        'td': ['class'],
                        'input': ['type', 'checked', 'disabled'],
                        'li': ['class']
                    },
                    ADD_ATTR: ['target'],
                    FORCE_BODY: true
                });

                div.innerHTML = sanitizedHtml;

                if (window.Prism) {
                    div.querySelectorAll('pre code').forEach(block => {
                        const langClass = Array.from(block.classList).find(c => c.startsWith('language-'));
                        if (langClass) {
                            const language = langClass.replace('language-', '');
                            if (window.Prism.languages[language]) {
                                block.innerHTML = window.Prism.highlight(block.textContent, window.Prism.languages[language], language);
                            }
                        }
                    });
                }
            } catch (error) {
                window.monitoring?.logError('Error rendering message:', error);
                div.innerHTML = `<p class="text-red-500">Error rendering message: ${error.message}</p>`;
            }
        });

        logDebug('Finished re-rendering messages');
    }

    function attachActionButtonListeners() {
        const chatBox = document.getElementById('chat-box');
        if (!chatBox) return;

        chatBox.addEventListener('click', async event => {
            const target = event.target.closest('button');
            if (!target) return;

            event.preventDefault();
            if (target.classList.contains('copy-button')) {
                await handleCopyMessage(target);
            } else if (target.classList.contains('regenerate-button')) {
                await handleRegenerateMessage();
            }
        });
    }

    async function handleCopyMessage(button) {
        if (!window.utils) {
            window.monitoring?.logError('Utils not initialized');
            return;
        }

        try {
            const rawContent = button.dataset.rawContent || '';
            await navigator.clipboard.writeText(rawContent);
            window.showAlert('Message copied to clipboard!', 'success');
        } catch (error) {
            window.monitoring?.logError('Clipboard copy failed:', error);
            window.showAlert('Failed to copy message', 'error');
        }
    }

    async function handleRegenerateMessage() {
        logDebug('Regenerate message triggered.');
        try {
            const chatBox = document.getElementById('chat-box');
            if (!chatBox) return;

            const userMessages = [...chatBox.querySelectorAll('div.justify-end')];
            if (!userMessages.length) {
                logDebug('No user messages found for regeneration.');
                return;
            }

            const lastUserMessage = userMessages[userMessages.length - 1];
            const lastUserPara = lastUserMessage.querySelector('p');
            if (!lastUserPara) {
                logDebug('No paragraph found in last user message.');
                return;
            }

            const lastUserText = lastUserPara.textContent;
            const allMessages = Array.from(chatBox.children);
            const lastUserIndex = allMessages.indexOf(lastUserMessage);

            while (allMessages.length > lastUserIndex + 1) {
                chatBox.removeChild(allMessages[lastUserIndex + 1]);
                allMessages.splice(lastUserIndex + 1, 1);
            }

            const messageInput = document.getElementById('message-input');
            if (messageInput) {
                messageInput.value = lastUserText;
            } else {
                return;
            }

            const sendButton = document.getElementById('send-button');
            if (sendButton) {
                sendButton.click();
            }
        } catch (error) {
            window.monitoring?.logError('Error during regeneration:', error);
            window.showAlert('Failed to regenerate message', 'error');
        }
    }

    let modelChangeInProgress = false;

    async function handleModelChange() {
        if (modelChangeInProgress) return;

        const modelSelect = document.getElementById('model-select');
        const sendButton = document.getElementById('send-button');
        const modelId = modelSelect.value;
        const originalValue = modelSelect.getAttribute('data-original-value');

        if (modelId === originalValue) return;

        modelChangeInProgress = true;
        if (sendButton) sendButton.disabled = true;

        try {
            const response = await window.utils.fetchWithCSRF('/chat/update_model', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    model_id: modelId,
                    chat_id: window.CHAT_CONFIG.chatId
                })
            });

            if (!response.success) {
                throw new Error(response.error || 'Failed to update model');
            }

            modelSelect.setAttribute('data-original-value', modelId);
            window.showAlert('Model updated successfully', 'success');

            if (window.tokenUsageManager) {
                const model = window.CHAT_CONFIG.models.find(m => m.id === parseInt(modelId));
                if (model) {
                    await window.tokenUsageManager.updateModelLimits({
                        max_tokens: model.max_tokens || 32000
                    });
                }
            }
        } catch (error) {
            window.monitoring?.logError('Error updating model:', error);
            window.showAlert(error.message || 'Failed to update model', 'error');
            modelSelect.value = originalValue;
        } finally {
            modelChangeInProgress = false;
            if (sendButton) sendButton.disabled = false;
        }
    }

    async function createNewChat() {
        try {
            const response = await window.utils.fetchWithCSRF('/chat/new', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.success) {
                throw new Error(response.error || 'Failed to create new chat');
            }

            if (response.chat_id) {
                window.location.href = `/chat/?chat_id=${response.chat_id}`;
            } else {
                throw new Error('No chat ID returned from server');
            }
        } catch (error) {
            window.monitoring?.logError('Error creating new chat:', error);
            window.showAlert(error.message || 'Failed to create new chat', 'error');
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

            // Validate message and files
            if (!message && !hasFiles) {
                throw new Error('No message or files provided');
            }

            // Create FormData
            const formData = new FormData();
            formData.append('message', message);

            // Add files if present
            if (hasFiles) {
                window.fileUploadManager.uploadedFiles.forEach(file => {
                    formData.append('files', file);
                });
            }

            // Clear input and files
            messageInput.value = '';
            if (window.fileUploadManager) {
                window.fileUploadManager.clearFiles();
            }

            // Add user message to chat
            if (message) {
                appendUserMessage(message);
            }

            // Show typing indicator
            showTypingIndicator();

            try {
                await handleStreamingResponse(formData);
            } catch (error) {
                window.monitoring?.logError('Failed to send message:', error);
                showError('Failed to send message. Please try again.');
            }

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

    async function initializeInterface() {
        try {
            const chatForm = document.getElementById('chat-form');
            if (chatForm) {
                chatForm.addEventListener('submit', e => {
                    e.preventDefault();
                    sendMessage();
                });
            }

            if (window.FileUploadManager && window.CHAT_CONFIG) {
                const uploadButton = document.getElementById('file-upload');
                if (!window.fileUploadManager) {
                    window.fileUploadManager = new window.FileUploadManager(
                        window.CHAT_CONFIG.chatId,
                        window.CHAT_CONFIG.userId,
                        uploadButton
                    );
                    await window.fileUploadManager.initializeFileUpload();
                }
            }

            if (window.TokenUsageManager) {
                const tokenUsageContainer = document.getElementById('token-usage');
                if (tokenUsageContainer && window.CHAT_CONFIG && window.CHAT_CONFIG.chatId) {
                    window.tokenUsageManager = new window.TokenUsageManager({
                        chatId: window.CHAT_CONFIG.chatId
                    });
                    const success = await window.tokenUsageManager.initialize();
                    if (!success) {
                        window.monitoring?.logError('Token usage manager initialization failed');
                    }
                }
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

            const modelSelect = document.getElementById('model-select');
            if (modelSelect) {
                modelSelect.addEventListener('change', handleModelChange);
            }

            const newChatBtn = document.getElementById('new-chat-btn');
            if (newChatBtn) {
                newChatBtn.addEventListener('click', createNewChat);
            }

            attachActionButtonListeners();
            await renderInitialAssistantMessages();
        } catch (error) {
            window.monitoring?.logError('Error during interface initialization:', error);
            throw error;
        }
    }

    async function startChat() {
        try {
            await initializeInterface();
        } catch (error) {
            window.monitoring?.logError('Failed to initialize chat:', error);
            showError(error.message);
        }
    }

    function showError(message) {
        if (message.includes('Authentication Error')) {
            message = message.replace('Authentication Error:', '🔑 Authentication Error:');
        }

        if (window.showAlert) {
            window.showAlert(message, 'error', 10000);
        } else {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'pointer-events-auto fixed top-20 left-1/2 transform -translate-x-1/2 bg-red-100 dark:bg-red-900/50 text-red-900 dark:text-red-100 px-6 py-4 rounded-lg shadow-xl border-2 border-red-500/50 z-[2200] max-w-[90%] sm:max-w-lg';
            errorDiv.innerHTML = `
                <div class="flex items-center gap-3">
                    <i class="fas fa-exclamation-circle text-lg"></i>
                    <p class="text-sm font-medium flex-1">${message}</p>
                    <button onclick="this.parentElement.parentElement.remove()" class="hover:opacity-80 transition-opacity">
                        <i class="fas fa-times"></i>
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

    document.addEventListener('app:ready', startChat);
})();
