/* remediated static/js/chat.js */
(() => {
    'use strict';

    /* =====================================================
       CONFIGURATION & UTILITY FUNCTIONS
    ===================================================== */
    const CONFIG = {
        DEPENDENCY_TIMEOUT: 5000,      // ms to wait for globals
        STREAM_UPDATE_INTERVAL: 100,   // ms between streaming updates
        MAX_DEPENDENCY_ATTEMPTS: 50,
        DEBUG: true                    // Set false for production logging
    };

    const logDebug = (...args) => {
        if (CONFIG.DEBUG) console.debug(...args);
    };

    function showTypingIndicator() {
        let indicator = document.getElementById('typing-indicator');
        if (indicator && indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
        }
        indicator = document.createElement('div');
        indicator.id = 'typing-indicator';
        indicator.className = 'flex w-full mt-4 space-x-3 max-w-3xl animate-slide-up';
        indicator.setAttribute('role', 'status');
        indicator.setAttribute('aria-label', 'Assistant is typing');
        indicator.innerHTML = `
            <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-primary-500 to-secondary-600 flex items-center justify-center text-white shadow-soft">
                <i class="fas fa-robot text-sm"></i>
            </div>
            <div class="relative max-w-3xl">
                <div class="bg-gray-100/95 dark:bg-gray-800/95 p-4 rounded-r-lg rounded-bl-lg shadow-soft border border-gray-200/50 dark:border-gray-700/50">
                    <div class="typing-animation">
                        <div class="dot"></div>
                        <div class="dot"></div>
                        <div class="dot"></div>
                    </div>
                </div>
                <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                    ${new Date().toLocaleTimeString()}
                </span>
            </div>
        `;
        const chatBox = document.getElementById('chat-box');
        if (chatBox) {
            chatBox.appendChild(indicator);
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator && indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
        } else {
            console.warn('Typing indicator not found or already removed.');
        }
    }

    /* =====================================================
       AZURE PARAMETER & MESSAGE BUILDERS
    ===================================================== */
    /**
     * Build a message array including a system message and the user message.
     * @param {string} messageText - The text entered by the user.
     * @param {object} model - The current model configuration.
     * @returns {Array} - An array of message objects.
     */
    function buildMessageArray(messageText, model) {
        const messages = [];
        messages.push({
            role: 'system',
            content: model.system_message || 'You are a helpful assistant.'
        });
        messages.push({ role: 'user', content: messageText });
        return messages;
    }

    /**
     * Validate model parameters and build the Azure parameters object.
     * @param {object} model - The current model configuration.
     * @param {Array} messages - The messages array.
     * @returns {object} - An object containing all parameters for Azure.
     */
    function buildAzureParameters(model, messages) {
        // Validate required Azure model properties
        if (!model.deployment_name || !model.api_version) {
            throw new Error('Invalid Azure model configuration');
        }
        const temperature = (model.temperature !== undefined) ? model.temperature : 1.0;
        if (temperature < 0 || temperature > 2) {
            throw new Error('Temperature must be between 0 and 2');
        }
        const top_p = (model.top_p !== undefined) ? model.top_p : 1;
        if (top_p < 0 || top_p > 1) {
            throw new Error('top_p must be between 0 and 1');
        }
        const presence_penalty = (model.presence_penalty !== undefined) ? model.presence_penalty : 0;
        if (presence_penalty < -2 || presence_penalty > 2) {
            throw new Error('presence_penalty must be between -2 and 2');
        }
        const frequency_penalty = (model.frequency_penalty !== undefined) ? model.frequency_penalty : 0;
        if (frequency_penalty < -2 || frequency_penalty > 2) {
            throw new Error('frequency_penalty must be between -2 and 2');
        }
        const azureParams = {
            messages: messages,
            max_tokens: model.max_tokens || 32000,
            temperature: temperature,
            top_p: top_p,
            frequency_penalty: frequency_penalty,
            presence_penalty: presence_penalty,
            stop: model.stop_sequences || null,
            stream: true,
            n: (model.n && Number.isInteger(model.n) && model.n > 0) ? Math.min(model.n, 128) : 1,
            logprobs: model.logprobs !== undefined ? model.logprobs : undefined,
            best_of: (model.best_of && Number.isInteger(model.best_of)) ? model.best_of : undefined,
            user: window.CHAT_CONFIG.userId || 'anonymous'
        };
        if (model.response_format) {
            azureParams.response_format = { type: model.response_format };
        }
        return azureParams;
    }

    /* =====================================================
       MESSAGE RENDERING FUNCTIONS
    ===================================================== */
    /**
     * Append the assistant's message to the chat box.
     * Uses markdown-it for rendering and DOMPurify for sanitization.
     * @param {string|object} message - The message text or an API response object.
     * @param {boolean} [isStreaming=false] - If true, indicates a partial update.
     * @param {HTMLElement|null} existingDiv - An existing message element to update.
     */
    async function appendAssistantMessage(message, isStreaming = false, existingDiv = null) {
        if (!message) return;
        logDebug('Appending assistant message:', message);
        const chatBox = document.getElementById('chat-box');
        if (!chatBox) {
            console.error('Chat box not found');
            return;
        }

        // Wait for markdown-it and DOMPurify to be ready
        let attempts = 0;
        while ((!window.md || !window.DOMPurify) && attempts < CONFIG.MAX_DEPENDENCY_ATTEMPTS) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        if (!window.md || !window.DOMPurify) {
            console.error('Required dependencies not available.');
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = '<p class="text-red-500">Error: Required dependencies not available. Please refresh the page.</p>';
            chatBox.insertBefore(errorDiv, chatBox.firstChild);
            return;
        }

        try {
            const renderedHtml = typeof message === 'string' ? window.md.render(message) : message.content;
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
                        <button class="copy-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-soft" title="Copy to clipboard" aria-label="Copy message to clipboard" data-raw-content="${message.content.replace(/"/g, '&quot;')}">
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
            console.error('Error appending assistant message:', error);
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = `<p class="text-red-500">Error creating message: ${error.message}</p>`;
            chatBox.appendChild(errorDiv);
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    /**
     * Append a user message to the chat.
     * @param {string} message - The user's message.
     */
    function appendUserMessage(message) {
        if (!message || typeof message !== 'string') {
            console.error('Invalid message content.');
            return;
        }
        const messageDiv = document.createElement('div');
        messageDiv.className =
            'flex w-full mt-4 space-x-3 max-w-[85%] sm:max-w-md md:max-w-2xl ml-auto justify-end animate-slide-up';
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
            console.error('Chat box not found');
        }
    }

    /**
     * Re-render any initial assistant messages (for server-side rendered content).
     */
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
            console.error('markdown-it not available');
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
                console.error('Error rendering message:', error);
                div.innerHTML = `<p class="text-red-500">Error rendering message: ${error.message}</p>`;
            }
        });
        logDebug('Finished re-rendering messages');
    }

    /**
     * Attach action button listeners (e.g., copy or regenerate).
     */
    function attachActionButtonListeners() {
        const chatBox = document.getElementById('chat-box');
        if (!chatBox) return;
        chatBox.addEventListener('click', async (event) => {
            const target = event.target.closest('button');
            if (!target) return;
            event.preventDefault();
            if (target.classList.contains('copy-button')) {
                await handleCopyMessage(target);
            } else if (target.classList.contains('regenerate-button')) {
                await handleRegenerateMessage(target);
            }
        });
    }

    async function handleCopyMessage(button) {
        if (!window.utils) {
            console.error('Utils not initialized');
            return;
        }
        try {
            const rawContent = button.dataset.rawContent || '';
            await navigator.clipboard.writeText(rawContent);
            window.utils.showFeedback('Message copied to clipboard!', 'success');
        } catch (err) {
            console.error('Clipboard copy failed:', err);
            window.utils.showFeedback('Failed to copy message', 'error');
        }
    }

    async function handleRegenerateMessage(target) {
        logDebug('Regenerate message triggered.');
        // Implement regeneration logic here if desired.
    }

    /* =====================================================
       RESPONSE HANDLING: STREAMING & NORMAL RESPONSES
    ===================================================== */
    /**
     * Handle streaming response from the server.
     * Parses each line as JSON and updates the assistant message.
     */
    async function handleStreamingResponse(formData) {
        let reader;
        let messageDiv = null;
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minutes
            const response = await fetch('/chat/send', {  // Updated URL
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'X-Azure-Token': window.CHAT_CONFIG.azureToken,
                    'api-key': window.CHAT_CONFIG.azureToken,
                    'X-Request-ID': (crypto.randomUUID && crypto.randomUUID()) || Date.now().toString(),
                    'X-Azure-Operation': 'chat-completion',
                    'Accept': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive'
                },
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error?.message || `Azure OpenAI Error: ${response.status}`);
            }

            reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedResponse = '';

            // Create a new assistant message container
            messageDiv = document.createElement('div');
            messageDiv.className =
                'flex w-full mt-4 space-x-3 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl animate-slide-up';
            const chatBox = document.getElementById('chat-box');
            chatBox.appendChild(messageDiv);

            let streaming = true;
            while (streaming) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6).trim();
                        if (data === '[DONE]') {
                            streaming = false;
                        } else if (data.startsWith('[ERROR]')) {
                            throw new Error(data.slice(7).trim());
                        } else {
                            try {
                                const parsed = JSON.parse(data);
                                if (parsed.choices && parsed.choices[0]) {
                                    const delta = parsed.choices[0].delta;
                                    if (delta) {
                                        if (delta.content) {
                                            accumulatedResponse += delta.content;
                                        }
                                        // Handle function calls if provided
                                        if (delta.function_call) {
                                            handleFunctionCall(delta.function_call);
                                        }
                                        await appendAssistantMessage(accumulatedResponse, true, messageDiv);
                                    }
                                }
                            } catch (e) {
                                console.error('Error parsing streaming chunk:', e);
                            }
                        }
                    }
                }
            }

            // Update token usage after streaming completes
            if (window.tokenUsageManager) {
                await window.tokenUsageManager.handleNewMessage();
            }

        } catch (error) {
            console.error('Streaming error:', error);
            if (messageDiv) {
                messageDiv.remove();
            }
            throw error;
        } finally {
            if (reader) {
                try {
                    await reader.cancel();
                } catch (e) {
                    console.error('Error canceling stream:', e);
                }
            }
        }
    }

    /* =====================================================
       CHAT CONTROL & EVENT HANDLERS
    ===================================================== */
    let modelChangeInProgress = false;

    /**
     * Handle model changes.
     */
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
                    'Content-Type': 'application/json',
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
            window.utils.showFeedback('Model updated successfully', 'success');

            // Update token usage if available
            if (window.tokenUsageManager) {
                const model = window.CHAT_CONFIG.models.find(m => m.id === parseInt(modelId));
                if (model) {
                    await window.tokenUsageManager.updateModelLimits({
                        max_tokens: model.max_tokens || 32000
                    });
                }
            }
        } catch (error) {
            console.error('Error updating model:', error);
            window.utils.showFeedback(error.message || 'Failed to update model', 'error');
            modelSelect.value = originalValue;
        } finally {
            modelChangeInProgress = false;
            if (sendButton) sendButton.disabled = false;
        }
    }

    /**
     * Create a new chat.
     */
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
            console.error('Error creating new chat:', error);
            window.utils.showFeedback(error.message || 'Failed to create new chat', 'error');
        }
    }

    /**
     * Send a message using Azure OpenAI parameters.
     */
    async function sendMessage() {
        if (!window.utils) {
            console.error('Utils not initialized');
            return;
        }

        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');

        if (!messageInput || !sendButton) {
            window.utils.showFeedback('Chat interface not properly initialized', 'error');
            return;
        }

        if (sendButton.disabled) return;

        try {
            sendButton.disabled = true;
            const messageText = messageInput.value.trim();

            if (!messageText) {
                window.utils.showFeedback('Please enter a message', 'error');
                return;
            }

            // Show typing indicator
            showTypingIndicator();

            // Get current model info and validate model configuration
            const modelSelect = document.getElementById('model-select');
            const modelId = modelSelect?.value;
            const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
            if (!model) {
                window.utils.showFeedback('Invalid Azure model configuration', 'error');
                return;
            }

            // Build messages array (including a system message)
            const messages = buildMessageArray(messageText, model);

            // Build Azure parameters using model and messages
            const azureParams = buildAzureParameters(model, messages);

            // Build FormData payload: append each parameter (stringifying objects)
            const formData = new FormData();
            for (const key in azureParams) {
                if (azureParams[key] !== undefined && azureParams[key] !== null) {
                    formData.append(key, typeof azureParams[key] === 'object' ? JSON.stringify(azureParams[key]) : azureParams[key]);
                }
            }
            // Also append the CSRF token if required by your backend
            formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);

            // Send the message via streaming fetch
            await handleStreamingResponse(formData);

            // Clear input and update UI
            messageInput.value = '';
            appendUserMessage(messageText);

            // In case the final response is non-streamed, you could also call:
            // const response = await window.utils.fetchWithCSRF('/chat/send', { ... });
            // appendAssistantMessage(response.message);

            // Update token usage
            if (window.tokenUsageManager) {
                await window.tokenUsageManager.handleNewMessage();
            }

        } catch (error) {
            console.error('Error sending message:', error);
            window.utils.showFeedback(error.message || 'Failed to send message', 'error');
        } finally {
            sendButton.disabled = false;
            removeTypingIndicator();
        }
    }

    /* =====================================================
       INTERFACE INITIALIZATION
    ===================================================== */
    async function initializeInterface() {
        try {
            // Initialize token usage manager
            if (window.TokenUsageManager) {
                const tokenUsageContainer = document.getElementById('token-usage');
                if (tokenUsageContainer && window.CHAT_CONFIG && window.CHAT_CONFIG.chatId) {
                    window.tokenUsageManager = new window.TokenUsageManager({
                        chatId: window.CHAT_CONFIG.chatId
                    });
                    const success = await window.tokenUsageManager.initialize();
                    if (!success) console.warn('Token usage manager initialization failed');
                } else {
                    console.warn('Token usage container not found');
                }
            }

            // Set up message input and send button
            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            if (messageInput && sendButton) {
                // Debounce function
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

                // Debounced keydown handler
                const debouncedKeydown = debounce((e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                    }
                }, 100);

                messageInput.addEventListener('keydown', debouncedKeydown);
                sendButton.addEventListener('click', sendMessage);
            }

            // Set up model select
            const modelSelect = document.getElementById('model-select');
            if (modelSelect) {
                modelSelect.addEventListener('change', handleModelChange);
            }

            // Set up new chat button
            const newChatBtn = document.getElementById('new-chat-btn');
            if (newChatBtn) {
                newChatBtn.addEventListener('click', createNewChat);
            }

            // Set up action buttons and render messages
            attachActionButtonListeners();
            await renderInitialAssistantMessages();

        } catch (error) {
            console.error('Error during interface initialization:', error);
            throw error;
        }
    }

    async function startChat() {
        try {
            await initializeInterface();
        } catch (error) {
            console.error('Failed to initialize chat:', error);
            showError(error.message);
        }
    }

    function showError(message) {
        if (!window.utils) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'fixed top-4 left-1/2 transform -translate-x-1/2 bg-red-500 text-white px-4 py-2 rounded-lg shadow-lg';
            errorDiv.textContent = message;
            document.body.appendChild(errorDiv);
        } else {
            window.utils.showFeedback(message, 'error');
        }
    }

    document.addEventListener('DOMContentLoaded', startChat);
})();
