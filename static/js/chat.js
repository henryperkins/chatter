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

    /**
     * Wait until a global dependency is available.
     * @param {string} name - Global variable name.
     * @param {number} [timeout=CONFIG.DEPENDENCY_TIMEOUT]
     * @returns {Promise<any>}
     */
    async function waitForDependency(name, timeout = CONFIG.DEPENDENCY_TIMEOUT) {
        const start = Date.now();
        while (!window[name]) {
            if (Date.now() - start > timeout) {
                throw new Error(`Timeout waiting for ${name}`);
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        return window[name];
    }

    /**
     * Dynamically load a script if it isn't already present.
     * @param {string} id - Unique ID for the script element.
     * @param {string} src - Script source URL.
     * @returns {Promise<void>}
     */
    async function ensureScriptLoaded(id, src) {
        if (document.getElementById(id)) return;
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.id = id;
            script.src = src;
            script.onload = resolve;
            script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
            document.head.appendChild(script);
        });
    }

    /**
     * Compute a full static asset URL based on current script location.
     * @param {string} path - Relative path to the asset.
     * @returns {string}
     */
    function getStaticUrl(path) {
        const baseUrl = document.querySelector('script[src*="/static/"]')?.src.split('/static/')[0] || '';
        return `${baseUrl}/static${path}`;
    }

    /* =====================================================
       UI HELPERS: LOADING & TYPING INDICATORS
    ===================================================== */
    function showLoadingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading-indicator';
        loadingDiv.className =
            'fixed inset-0 bg-white/50 dark:bg-gray-900/50 backdrop-blur-sm z-modal flex items-center justify-center transition-all duration-300 ease-in-out';
        loadingDiv.innerHTML = `
      <div class="flex items-center space-x-3 bg-white/90 dark:bg-gray-800/90 px-6 py-4 rounded-xl shadow-soft border border-gray-200/50 dark:border-gray-700/50 animate-slide-up">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 dark:border-primary-400"></div>
          <span class="text-gray-700 dark:text-gray-300 font-medium">Loading chat...</span>
      </div>
    `;
        document.body.appendChild(loadingDiv);
        requestAnimationFrame(() => loadingDiv.style.opacity = '1');
    }

    function hideLoadingIndicator() {
        const loadingDiv = document.getElementById('loading-indicator');
        if (loadingDiv) {
            loadingDiv.style.opacity = '0';
            setTimeout(() => loadingDiv.remove(), 300);
        }
    }

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
        // Process message if provided as an object (e.g., from an API)
        let processedMessage = message;
        if (typeof message === 'object') {
            if (message.choices && message.choices[0]) {
                processedMessage = message.choices[0].message?.content || message.choices[0].text || processedMessage;
            } else if (message.content) {
                processedMessage = message.content;
            }
        }
        let messageDiv = existingDiv;
        const DOMPurifyOptions = {
            ALLOWED_TAGS: [
                'p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote',
                'a', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'br',
                'table', 'thead', 'tbody', 'tr', 'th', 'td'
            ],
            ALLOWED_ATTRS: {
                'a': ['href', 'title', 'target', 'rel', 'class'],
                'span': ['class'],
                'code': ['class'],
                'pre': ['class'],
                'div': ['class', 'style'],
                'table': ['class'],
                'th': ['class'],
                'td': ['class']
            },
            ADD_ATTR: ['target']
        };

        try {
            if (messageDiv) {
                // Update an existing element (useful for streaming updates)
                const contentDiv = messageDiv.querySelector('[data-role="assistant-message"]');
                if (contentDiv) {
                    const renderedHtml = window.md.render(processedMessage);
                    const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, DOMPurifyOptions);
                    contentDiv.innerHTML = sanitizedHtml;
                    const copyButton = messageDiv.querySelector('.copy-button');
                    if (copyButton) copyButton.setAttribute('data-raw-content', processedMessage);
                    if (window.Prism) window.Prism.highlightAllUnder(contentDiv);
                }
            } else {
                // Create a new message element
                messageDiv = document.createElement('div');
                messageDiv.className =
                    'flex w-full mt-4 space-x-3 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl animate-slide-up';
                const renderedHtml = window.md.render(processedMessage);
                const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, DOMPurifyOptions);
                messageDiv.innerHTML = `
          <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-primary-500 to-secondary-600 flex items-center justify-center text-white shadow-soft" role="img" aria-label="Assistant avatar">
              <i class="fas fa-robot text-sm"></i>
          </div>
          <div class="relative flex-1">
              <div class="absolute right-2 top-2 flex items-center space-x-1 z-10 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <button class="copy-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-soft" title="Copy to clipboard" aria-label="Copy message to clipboard" data-raw-content="${processedMessage.replace(/"/g, '&quot;')}">
                      <i class="fas fa-copy"></i>
                  </button>
                  ${!isStreaming ? `<button class="regenerate-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-soft" title="Regenerate response" aria-label="Regenerate response">
                      <i class="fas fa-redo-alt"></i>
                  </button>` : ''}
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
                chatBox.appendChild(messageDiv);
                if (window.Prism) {
                    window.Prism.highlightAllUnder(messageDiv.querySelector('[data-role="assistant-message"]'));
                }
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
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
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
    async function handleStreamingResponse(formData) {
        let reader;
        let messageDiv = null;
        try {
            logDebug('Starting streaming response...');
            const modelSelect = document.getElementById('model-select');
            const modelId = modelSelect?.value;
            const response = await fetch('/chat/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'Accept': 'text/event-stream',
                    'X-CSRFToken': window.CHAT_CONFIG.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Cache-Control': 'no-cache'
                }
            });
            logDebug('Stream response status:', response.status);
            if (!response.ok) {
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const errorData = await response.json();
                    const errorMessage = typeof errorData.error === 'object'
                        ? errorData.error.message || JSON.stringify(errorData.error)
                        : errorData.error;
                    throw new Error(errorMessage);
                }
                if (response.status === 403) {
                    throw new Error('Session expired - please refresh the page');
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedResponse = '';
            let lastUpdateTime = Date.now();
            messageDiv = document.createElement('div');
            messageDiv.className =
                'flex w-full mt-4 space-x-3 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl animate-slide-up';
            const chatBox = document.getElementById('chat-box');
            chatBox.appendChild(messageDiv);
            messageDiv.innerHTML = `
          <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-primary-500 to-secondary-600 flex items-center justify-center text-white shadow-soft" role="img" aria-label="Assistant avatar">
              <i class="fas fa-robot text-sm"></i>
          </div>
          <div class="relative flex-1">
              <div class="absolute right-2 top-2 flex items-center space-x-1 z-10 opacity-0 transition-opacity duration-200">
                  <button class="copy-button p-1.5 rounded-md" title="Copy to clipboard" aria-label="Copy message to clipboard">
                      <i class="fas fa-copy"></i>
                  </button>
              </div>
              <div class="bg-gray-100/95 dark:bg-gray-800/95 p-5 rounded-r-lg rounded-bl-lg shadow-soft border">
                  <div class="prose dark:prose-invert overflow-x-auto" data-role="assistant-message"></div>
              </div>
              <span class="text-xs text-gray-500 block mt-1">
                  ${new Date().toLocaleTimeString()}
              </span>
          </div>
      `;
            let streaming = true;
            while (streaming) {
                const { value, done } = await reader.read();
                if (done) {
                    streaming = false;
                    continue;
                }
                const chunk = decoder.decode(value);
                logDebug('Received chunk:', chunk);
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const streamData = line.slice(6);
                        if (streamData === '[DONE]') break;
                        if (streamData.startsWith('[ERROR]')) {
                            throw new Error(streamData.slice(7).trim());
                        }
                        try {
                            const jsonData = JSON.parse(streamData);
                            accumulatedResponse += jsonData.content || jsonData.message?.content || streamData;
                        } catch (e) {
                            accumulatedResponse += streamData;
                        }
                        const now = Date.now();
                        if (now - lastUpdateTime > CONFIG.STREAM_UPDATE_INTERVAL) {
                            const contentDiv = messageDiv.querySelector('[data-role="assistant-message"]');
                            if (contentDiv && accumulatedResponse.trim()) {
                                appendAssistantMessage(accumulatedResponse, true, messageDiv);
                                lastUpdateTime = now;
                            }
                        }
                    }
                }
            }
            if (accumulatedResponse.trim()) {
                logDebug('Final response:', accumulatedResponse);
                let lintedResponse = accumulatedResponse;
                try {
                    lintedResponse = await window.tokenUsageManager?.lintMessage(accumulatedResponse) || accumulatedResponse;
                } catch (error) {
                    console.warn('Error linting message:', error);
                }
                appendAssistantMessage(lintedResponse, true, messageDiv);
            }
        } catch (error) {
            console.error('Streaming error:', error);
            if (messageDiv) messageDiv.remove();
            throw error instanceof Error ? error : new Error(String(error));
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

    async function handleNormalResponse(formData) {
        try {
            if (!window.utils) throw new Error('Utils not initialized');
            const response = await window.utils.fetchWithCSRF('/chat/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });
            logDebug('Normal API Response:', response);
            if (!response) throw new Error('Server returned no response');
            if (response.error) {
                const errorMessage = typeof response.error === 'object'
                    ? response.error.message || JSON.stringify(response.error)
                    : response.error;
                throw new Error(errorMessage);
            }
            const content = response.message?.content || response.content;
            if (!content) throw new Error('Server response missing message content');
            let lintedContent = content;
            try {
                lintedContent = await window.tokenUsageManager?.lintMessage(content) || content;
            } catch (error) {
                console.warn('Error linting message, using raw content:', error);
            }
            appendAssistantMessage(lintedContent);
        } catch (error) {
            console.error('Normal response error:', error);
            throw error;
        }
    }

    /* =====================================================
       INTERFACE INITIALIZATION & EVENT HANDLING
    ===================================================== */
    let modelChangeInProgress = false;
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
        sendButton.disabled = true;
        try {
            const messageText = messageInput.value.trim();
            const hasUploadedFiles = window.fileUploadManager?.uploadedFiles?.length > 0;
            if (!messageText && !hasUploadedFiles) {
                window.utils.showFeedback('Please enter a message or upload files.', 'error');
                return;
            }
            const modelSelect = document.getElementById('model-select');
            const modelId = modelSelect?.value;
            const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
            const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;
            document.querySelectorAll('.error-indicator').forEach(el => el.remove());
            const maxTokens = model?.max_tokens || 32000;
            let tokenCount = 0;
            try {
                tokenCount = await window.tokenUsageManager?.countMessageTokens(messageText) || Math.ceil(messageText.length / 4);
            } catch (error) {
                console.error('Error counting tokens:', error);
                tokenCount = Math.ceil(messageText.length / 4);
            }
            if (tokenCount > maxTokens) {
                window.utils.showFeedback(`Message exceeds token limit (${tokenCount}/${maxTokens})`, 'error');
                return;
            }
            let uploadedFiles = [];
            if (window.fileUploadManager?.uploadedFiles?.length > 0) {
                uploadedFiles = await window.fileUploadManager.uploadFiles(window.CHAT_CONFIG.chatId) || [];
            }
            const metadata = {
                timestamp: new Date().toISOString(),
                token_count: tokenCount,
                requires_o1: model?.requires_o1_handling || false,
                model_max_tokens: maxTokens,
                has_files: uploadedFiles.length > 0
            };
            const formData = new FormData();
            let messageForSend = '';
            if (messageText) {
                messageForSend = tokenCount > maxTokens
                    ? await window.tokenUsageManager?.truncateContent(messageText, maxTokens) || messageText
                    : messageText;
                formData.append('message', messageForSend);
                formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);
            }
            formData.append('metadata', JSON.stringify(metadata));
            if (uploadedFiles.length > 0) {
                const fileIds = uploadedFiles.filter(file => file.id).map(file => file.id);
                fileIds.forEach(id => formData.append('file_ids[]', id));
            }
            formData.append('model_id', modelId);
            formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);
            if (messageText) appendUserMessage(messageText);
            showTypingIndicator();
            if (useStreaming) {
                await handleStreamingResponse(formData);
            } else {
                await handleNormalResponse(formData);
            }
            if (window.tokenUsageManager) {
                await window.tokenUsageManager?.handleNewMessage();
                await window.tokenUsageManager?.updateStats();
                const modelLimits = { max_tokens: model?.max_tokens || 32000 };
                window.tokenUsageManager.updateModelLimits(modelLimits);
                const tokenUsageContainer = document.getElementById('token-usage');
                if (tokenUsageContainer?.classList.contains('hidden')) {
                    window.tokenUsageManager.toggleDisplay();
                }
            }
            messageInput.value = '';
            messageInput.style.height = 'auto';
            if (uploadedFiles.length > 0) {
                window.fileUploadManager.uploadedFiles = [];
                window.fileUploadManager.renderFileList();
            }
        } catch (error) {
            console.error('Error sending message:', error);
            const errorMessage = error instanceof Error ? error.message : 'Failed to send message';
            window.utils.showFeedback(errorMessage, 'error', { duration: 0 });
        } finally {
            removeTypingIndicator();
            sendButton.disabled = false;
            sendButton.classList.remove('sending');
        }
    }

    async function handleModelChange() {
        if (!window.utils) {
            console.error('Utils not initialized');
            return;
        }
        if (modelChangeInProgress) return;
        const modelSelect = document.getElementById('model-select');
        const sendButton = document.getElementById('send-button');
        const modelId = modelSelect.value;
        const originalValue = modelSelect.getAttribute('data-original-value');
        if (modelId === originalValue) return;
        modelChangeInProgress = true;
        if (sendButton) sendButton.disabled = true;
        try {
            const response = await fetch('/chat/update_model', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.utils.getCSRFToken(),
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                },
                body: JSON.stringify({ model_id: modelId })
            });

            if (!response.ok) {
                throw new Error('Failed to update model');
            }

            modelSelect.setAttribute('data-original-value', modelId);
            window.utils.showFeedback('Model updated successfully', 'success');

            // Update token usage if available
            if (window.tokenUsageManager) {
                const model = window.CHAT_CONFIG.models.find(m => m.id === parseInt(modelId));
                if (model) {
                    const modelLimits = { max_tokens: model.max_tokens || 32000 };
                    window.tokenUsageManager.updateModelLimits(modelLimits);
                }
            }
        } catch (error) {
            console.error('Error during initialization:', error);
            if (window.utils) window.utils.showFeedback(error.message || 'Failed to initialize chat', 'error');
        } finally {
            hideLoadingIndicator();
        }
    }

    async function createNewChat() {
        try {
            const response = await fetch('/chat/new_chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                }
            });

            if (!response.ok) {
                throw new Error('Failed to create new chat');
            }

            const data = await response.json();
            if (data.chat_id) {
                window.location.href = `/chat/chat_interface?chat_id=${data.chat_id}`;
            } else {
                throw new Error('No chat ID returned from server');
            }
        } catch (error) {
            console.error('Error creating new chat:', error);
            if (window.utils) {
                window.utils.showFeedback('Failed to create new chat', 'error');
            }
        }
    }

    async function initializeInterface() {
        // Set up message input and send button
        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');
        if (messageInput && sendButton) {
            messageInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
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
