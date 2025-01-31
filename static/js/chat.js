/* static/js/chat.js */

/**
 * Main initialization function
 */
async function init() {
    try {
        console.log('Initializing chat interface');
        showLoadingIndicator();

        // Wait for utils to be available
        let attempts = 0;
        while (!window.utils && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }

        if (!window.utils) {
            throw new Error('Utils not initialized after 5 seconds');
        }

        // Add navigation state handler
        const handleNavigation = () => {
            if (window.location.pathname === '/chat') {
                showLoadingIndicator();
            }
        };
        window.addEventListener('popstate', handleNavigation);

        // Set up mobile viewport height
        function updateVH() {
            let vh = window.innerHeight * 0.01;
            document.documentElement.style.setProperty('--vh', `${vh}px`);
        }

        updateVH();
        window.addEventListener('resize', updateVH);

        // Initialize interface components
        await initializeInterface();

        console.debug('Chat initialization completed successfully');
    } catch (error) {
        console.error('Error during initialization:', error);
        if (window.utils) {
            window.utils.showFeedback(error.message || 'Failed to initialize chat', 'error');
        }
    } finally {
        hideLoadingIndicator();
    }
}

/**
 * This function wires up the UI: buttons, file uploads, token usage, model selection,
 * drag-and-drop, chat input behavior, etc.
 */
async function initializeInterface() {
    // 1. Attach basic chat event listeners (Send, Enter key in input)
    const sendButton = document.getElementById('send-button');
    if (!sendButton) {
        console.error('Send button not found - check HTML ID');
        return;
    }
    sendButton.addEventListener('click', sendMessage);

    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        });
    }

    // 2. Initialize FileUploadManager if needed
    const chatId = window.CHAT_CONFIG.chatId;
    const userId = window.CHAT_CONFIG.userId;
    const uploadButton = document.getElementById('upload-button');
    const mobileUploadButton = document.getElementById('mobile-upload-button');
    const correctUploadBtn = window.innerWidth < 768 ? mobileUploadButton : uploadButton;

    if (!window.fileUploadManager) {
        window.fileUploadManager = new window.FileUploadManager(chatId, userId, correctUploadBtn);
    }

    // 3. Initialize TokenUsageManager with full configuration
    if (window.TokenUsageManager && chatId) {
        console.log('Initializing TokenUsageManager with chatId:', chatId);
        const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(window.CHAT_CONFIG.currentModel?.id));
        const config = {
            chatId,
            model_limits: {
                max_tokens: model?.max_tokens || 32000
            }
        };
        window.tokenUsageManager = new window.TokenUsageManager(config);

        // Force an immediate update of token usage stats
        try {
            await window.tokenUsageManager.updateStats();

            // Start periodic updates
            window.tokenUsageManager.startPeriodicUpdates();

            // Show token usage panel by default
            const tokenUsageContainer = document.getElementById('token-usage');
            if (tokenUsageContainer?.classList.contains('hidden')) {
                window.tokenUsageManager.toggleDisplay();
            }
        } catch (error) {
            console.error('Error updating token stats:', error);
        }
    } else {
        console.error('TokenUsageManager initialization failed - missing dependencies');
    }

    // 4. Fix chat input visibility / dynamic height
    const chatBox = document.getElementById('chat-box');
    const messageInputContainer = document.getElementById('message-input-container');
    if (chatBox && messageInputContainer) {
        // Adjust chat box height based on keyboard visibility
        const updateChatBoxHeight = () => {
            if (window.innerHeight < 500) {
                // Keyboard is likely open
                chatBox.style.maxHeight = 'calc(100vh - 300px)';
            } else {
                chatBox.style.maxHeight = 'calc(100vh - 120px)';
            }
        };

        chatBox.style.cssText = `
            padding-bottom: 120px !important;
            margin-bottom: 0 !important;
            max-height: calc(100vh - 120px);
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
        `;

        messageInputContainer.style.cssText = `
            position: sticky !important;
            bottom: 0 !important;
            background-color: var(--tw-bg-opacity, 1) !important;
            z-index: 50 !important;
            border-top: 1px solid #e5e7eb !important;
            padding: 1rem !important;
            width: 100% !important;
            margin-top: auto !important;
        `;

        // Dark mode overrides
        const styleSheet = document.createElement('style');
        styleSheet.textContent = `
            .dark #message-input-container {
                background-color: #1a202c;
                border-color: #4a5568;
            }
            #message-input-container {
                position: sticky !important;
                bottom: 0 !important;
                z-index: 10 !important;
            }
        `;
        document.head.appendChild(styleSheet);

        window.addEventListener('resize', updateChatBoxHeight);
        updateChatBoxHeight();
    }

    // 5. New chat button
    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', createNewChat);
    }

    // 6. Edit model button
    const editModelBtn = document.getElementById('edit-model-btn');
    const modelSelect = document.getElementById('model-select');
    if (editModelBtn) {
        editModelBtn.addEventListener('click', () => {
            const modelId = modelSelect?.value;
            if (modelId) {
                console.debug('Editing model:', modelId);
                const editUrl = window.CHAT_CONFIG.editModelUrl + modelId;
                window.location.href = editUrl;
            } else if (window.utils) {
                window.utils.showFeedback('No model selected', 'error');
            }
        });
    }

    // 7. Handle model changes
    if (modelSelect) {
        // Create a debounced version of the handler
        const debouncedModelChange = debounce(handleModelChange, 300);

        // Store the current handler on the element to help with cleanup
        modelSelect.modelChangeHandler = async (e) => {
            e.preventDefault(); // Prevent any default form submission
            await debouncedModelChange();
        };

        // Remove any existing listener using the stored handler
        if (modelSelect.previousHandler) {
            modelSelect.removeEventListener('change', modelSelect.previousHandler);
        }

        // Add the new listener and store it
        modelSelect.addEventListener('change', modelSelect.modelChangeHandler);
        modelSelect.previousHandler = modelSelect.modelChangeHandler;
    }

    // 8. Edit chat title (if applicable)
    const editTitleBtn = document.getElementById('edit-title-btn');
    if (editTitleBtn) {
        editTitleBtn.addEventListener('click', handleEditTitle);
    }
    function handleEditTitle() {
        // Implement the logic to edit chat title
    }

    // 9. Delete chat buttons
    const deleteChatButtons = document.querySelectorAll('.delete-chat-btn');
    deleteChatButtons.forEach(button => {
        button.addEventListener('click', () => {
            const chatId = button.getAttribute('data-chat-id');
            handleDeleteChat(chatId);
        });
    });
    function handleDeleteChat(chatId) {
        // Implement the logic to delete the chat
    }

    // 10. Additional setup: attach action buttons, render existing messages, drag & drop
    attachActionButtonListeners();
    renderInitialAssistantMessages();
    setupDragAndDrop();

    // Done
    console.debug('Chat interface setup completed');
}

/**
 * Loading indicator functions
 */
function showLoadingIndicator() {
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'loading-indicator';
    loadingDiv.className = 'fixed inset-0 bg-white/50 dark:bg-gray-900/50 backdrop-blur-sm z-50 flex items-center justify-center';
    loadingDiv.innerHTML = `
        <div class="flex items-center space-x-2">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span class="text-gray-700 dark:text-gray-300">Loading chat...</span>
        </div>
    `;
    document.body.appendChild(loadingDiv);
}

function hideLoadingIndicator() {
    const loadingDiv = document.getElementById('loading-indicator');
    if (loadingDiv) {
        loadingDiv.remove();
    }
}

/**
 * Typing indicator functions
 */
function showTypingIndicator() {
    let indicator = document.getElementById('typing-indicator');
    if (indicator && indicator.parentNode) {
        indicator.parentNode.removeChild(indicator);
    }

    indicator = document.createElement('div');
    indicator.id = 'typing-indicator';
    indicator.className = 'flex w-full mt-4 space-x-3 max-w-3xl';
    indicator.setAttribute('role', 'status');
    indicator.setAttribute('aria-label', 'Assistant is typing');
    indicator.innerHTML = `
        <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white">
            <i class="fas fa-robot text-sm"></i>
        </div>
        <div class="relative max-w-3xl">
            <div class="bg-gray-100 dark:bg-gray-800 p-4 rounded-r-lg rounded-bl-lg shadow-sm">
                <div class="typing-animation">
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <div class="dot"></div>
                </div>
            </div>
            <span class="text-xs text-gray-500 dark:text-gray-400 leading-none">
                ${new Date().toLocaleTimeString()}
            </span>
        </div>
    `;

    document.getElementById('chat-box').appendChild(indicator);
    document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator && indicator.parentNode) {
        indicator.parentNode.removeChild(indicator);
    } else {
        console.warn('Typing indicator element not found or already removed.');
    }
}

/**
 * Send message handling
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

    // Prevent multiple submissions
    if (sendButton.disabled) {
        return;
    }
    sendButton.disabled = true;

    const messageText = messageInput.value.trim();
    const hasUploadedFiles = window.fileUploadManager?.uploadedFiles?.length > 0;

    if (!messageText && !hasUploadedFiles) {
        window.utils.showFeedback('Please enter a message or upload files.', 'error');
        sendButton.disabled = false;
        return;
    }

    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect?.value;
    const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
    const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

    try {
        // Clear previous errors
        document.querySelectorAll('.error-indicator').forEach(el => el.remove());

        // Count tokens and check limits
        const maxTokens = model?.max_tokens || 32000;
        const tokenCount = await window.tokenUsageManager.countMessageTokens(messageText);

        if (tokenCount > maxTokens) {
            window.utils.showFeedback(`Message exceeds token limit (${tokenCount}/${maxTokens})`, 'error');
            sendButton.disabled = false;
            return;
        }

        // Prepare message metadata
        const metadata = {
            timestamp: new Date().toISOString(),
            token_count: tokenCount,
            requires_o1: model?.requires_o1_handling || false,
            model_max_tokens: maxTokens
        };

        // Create form data with metadata
        const formData = new FormData();
        if (messageText) {
            // Truncate if needed
            const truncatedMessage = tokenCount > maxTokens ?
                await window.tokenUsageManager.truncateContent(messageText, maxTokens) :
                messageText;
            formData.append('message', truncatedMessage);
            formData.append('metadata', JSON.stringify(metadata));
        }

        // Add files if available
        if (window.fileUploadManager?.uploadedFiles?.length > 0) {
            window.fileUploadManager.uploadedFiles.forEach(file => {
                formData.append('files[]', file);
            });
        }

        formData.append('model_id', modelId);
        formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);

        // Add user's message to the chat before sending
        if (messageText) {
            appendUserMessage(messageText);
        }

        // Show typing indicator before the request
        showTypingIndicator();

        try {
            // Only one response handler should be used
            if (useStreaming) {
                await handleStreamingResponse(formData);
            } else {
                await handleNormalResponse(formData);
            }

            // Clear inputs on success
            messageInput.value = '';
            messageInput.style.height = 'auto';
            window.fileUploadManager.uploadedFiles = [];
            window.fileUploadManager.renderFileList();

            // Update token usage and handle new message
            if (window.tokenUsageManager) {
                await window.tokenUsageManager.handleNewMessage();
                await window.tokenUsageManager.updateStats();

                // Update model limits if needed
                const modelLimits = {
                    max_tokens: model?.max_tokens || 32000
                };
                window.tokenUsageManager.updateModelLimits(modelLimits);

                // Show token usage panel if hidden
                const tokenUsageContainer = document.getElementById('token-usage');
                if (tokenUsageContainer?.classList.contains('hidden')) {
                    window.tokenUsageManager.toggleDisplay();
                }
            }
        } catch (error) {
            console.error('Error sending message:', error);
            const errorMessage = error instanceof Error ? error.message : 'Failed to send message';
            window.utils.showFeedback(errorMessage, 'error', { duration: 0 }); // Duration 0 means it won't auto-hide
        }
    } finally {
        removeTypingIndicator();
        sendButton.disabled = false;
        sendButton.classList.remove('sending');
    }
}

async function handleStreamingResponse(formData) {
    let reader;
    let messageDiv = null;

    try {
        console.log('Starting streaming response...'); // Debug log

        // Get current model
        const modelSelect = document.getElementById('model-select');
        const modelId = modelSelect?.value;
        const currentModel = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));

        // Use the native fetch for streaming since utils.fetchWithCSRF doesn't support streaming
        const response = await fetch('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'Accept': 'text/event-stream',
                'X-CSRFToken': window.CHAT_CONFIG.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        console.log('Stream response status:', response.status); // Debug log

        if (!response.ok) {
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const errorData = await response.json();
                if (errorData.error) {
                    // Handle nested error objects
                    const errorMessage = typeof errorData.error === 'object'
                        ? errorData.error.message || JSON.stringify(errorData.error)
                        : errorData.error;
                    throw new Error(errorMessage);
                }
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
        const updateInterval = 100;

        // Create message div once at the start
        messageDiv = document.createElement('div');
        messageDiv.className = 'flex w-full mt-2 space-x-2 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl';
        const chatBox = document.getElementById('chat-box');
        chatBox.appendChild(messageDiv);

        // Initialize the message structure
        messageDiv.innerHTML = `
            <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white" role="img"
                aria-label="Assistant avatar">
                <i class="fas fa-robot text-sm"></i>
            </div>
            <div class="relative flex-1">
                <div class="absolute right-2 top-2 flex items-center space-x-1 z-10 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                    <button class="copy-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                            title="Copy to clipboard"
                            aria-label="Copy message to clipboard">
                        <i class="fas fa-copy"></i>
                    </button>
                </div>
                <div class="bg-gray-100 dark:bg-gray-800 p-4 rounded-r-lg rounded-bl-lg shadow-sm group hover:shadow-md transition-all duration-200">
                    <div class="prose dark:prose-invert prose-sm sm:prose-base lg:prose-lg max-w-none overflow-x-auto"
                         data-role="assistant-message">
                    </div>
                </div>
                <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                    ${new Date().toLocaleTimeString()}
                </span>
            </div>
        `;

        console.log('Starting stream reading...'); // Debug log

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            console.log('Received chunk:', chunk); // Debug log

            const lines = chunk.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const streamData = line.slice(6);
                    if (streamData === '[DONE]') break;
                    if (streamData.startsWith('[ERROR]')) {
                        throw new Error(streamData.slice(7).trim());
                    }

                    try {
                        // Try to parse as JSON first
                        const jsonData = JSON.parse(streamData);
                        accumulatedResponse += jsonData.content || jsonData.message?.content || streamData;
                    } catch (e) {
                        // If not JSON, use as plain text
                        accumulatedResponse += streamData;
                    }

                    const now = Date.now();
                    if (now - lastUpdateTime > updateInterval) {
                        const contentDiv = messageDiv.querySelector('[data-role="assistant-message"]');
                        if (contentDiv) {
                            appendAssistantMessage(accumulatedResponse, true, messageDiv);
                            lastUpdateTime = now;
                        }
                    }
                }
            }
        }

        // Final update with complete response
        if (accumulatedResponse) {
            console.log('Final response:', accumulatedResponse); // Debug log

            // Lint the message before final display
            const lintedResponse = await window.tokenUsageManager.lintMessage(accumulatedResponse);

            // Display final linted response
            appendAssistantMessage(lintedResponse, true, messageDiv);
        }

    } catch (error) {
        console.error('Streaming error:', error);
        // Clean up the message div if there was an error
        if (messageDiv) {
            messageDiv.remove();
        }
        throw error instanceof Error ? error : new Error(error.toString());
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
        if (!window.utils) {
            throw new Error('Utils not initialized');
        }

        const response = await window.utils.fetchWithCSRF('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json'
            }
        });

        console.log('API Response:', response); // Debug log

        if (!response) {
            throw new Error('Server returned no response');
        }

        if (response.error) {
            // Handle nested error objects
            const errorMessage = typeof response.error === 'object'
                ? response.error.message || JSON.stringify(response.error)
                : response.error;
            throw new Error(errorMessage);
        }

        // Check both possible response formats
        const content = response.message?.content || response.content;
        if (!content) {
            throw new Error('Server response missing message content');
        }

        // Lint and process the message
        const lintedContent = await window.tokenUsageManager.lintMessage(content);

        // Display final linted response
        appendAssistantMessage(lintedContent);
    } catch (error) {
        console.error('Normal response error:', error);
        throw error; // Re-throw to be caught in sendMessage
    }
}

/**
 * Appends the assistant's message to the chat
 */
async function appendAssistantMessage(message, isStreaming = false, existingDiv = null) {
    if (!message) return;

    console.log('Appending message:', { message, isStreaming, hasExistingDiv: !!existingDiv }); // Debug log

    const chatBox = document.getElementById('chat-box');
    if (!chatBox) {
        console.error('Chat box not found');
        return;
    }

    // Wait for dependencies to be available
    let attempts = 0;
    while ((!window.md || !window.DOMPurify) && attempts < 50) {
        await new Promise(resolve => setTimeout(resolve, 100));
        attempts++;
    }

    if (!window.md || !window.DOMPurify) {
        console.error('Required dependencies not available after 5 seconds');
        const errorDiv = document.createElement('div');
        errorDiv.innerHTML = `<p class="text-red-500">Error: Required dependencies not available. Please refresh the page.</p>`;
        chatBox.appendChild(errorDiv);
        return;
    }

    // Process message content consistently
    let processedMessage = message;
    if (typeof message === 'object') {
        if (message.choices && message.choices[0]) {
            const choice = message.choices[0];
            if (choice.message && choice.message.content) {
                processedMessage = choice.message.content;
            } else if (choice.text) {
                processedMessage = choice.text;
            }
        } else if (message.content) {
            processedMessage = message.content;
        }
    }

    console.log('Processed message:', processedMessage); // Debug log

    const DOMPurifyOptions = {
        ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'a', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'br', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
        ALLOWED_ATTRS: {
            'a': ['href', 'title', 'target', 'rel', 'class'],
            'span': ['class'],
            'code': ['class'],
            'pre': ['class'],
            'table': ['class'],
            'th': ['class'],
            'td': ['class']
        },
        ADD_ATTR: ['target'],
        ADD_CLASS: {
            'blockquote': 'border-l-4 border-gray-300 dark:border-gray-600 pl-4 my-4 italic',
            'a': 'text-blue-600 dark:text-blue-400 hover:underline',
            'table': 'min-w-full border border-gray-300 dark:border-gray-600',
            'th': 'border border-gray-300 dark:border-gray-600 px-4 py-2 bg-gray-50 dark:bg-gray-700',
            'td': 'border border-gray-300 dark:border-gray-600 px-4 py-2'
        }
    };

    // For streaming updates, use the provided div
    let messageDiv = existingDiv;
    if (messageDiv) {
        const contentDiv = messageDiv.querySelector('[data-role="assistant-message"]');
        if (contentDiv) {
            try {
                // Render markdown and sanitize
                const renderedHtml = window.md.render(processedMessage);
                const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, DOMPurifyOptions);
                contentDiv.innerHTML = sanitizedHtml;

                // Update copy button raw content
                const copyButton = messageDiv.querySelector('.copy-button');
                if (copyButton) {
                    copyButton.setAttribute('data-raw-content', processedMessage);
                }

                if (window.Prism) {
                    window.Prism.highlightAllUnder(contentDiv);
                }
            } catch (error) {
                console.error('Error updating message content:', error);
                contentDiv.innerHTML = `<p class="text-red-500">Error rendering message: ${error.message}</p>`;
            }
        }
    } else {
        try {
            messageDiv = document.createElement('div');
            messageDiv.className = 'flex w-full mt-4 space-x-3 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl';

            const renderedHtml = window.md.render(processedMessage);
            const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, DOMPurifyOptions);

            messageDiv.innerHTML = `
                <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white" role="img"
                    aria-label="Assistant avatar">
                    <i class="fas fa-robot text-sm"></i>
                </div>
                <div class="relative flex-1">
                    <div class="absolute right-2 top-2 flex items-center space-x-1 z-10 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        <button
                            class="copy-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                            title="Copy to clipboard"
                            data-raw-content="${processedMessage.replace(/"/g, '&quot;')}"
                            aria-label="Copy message to clipboard">
                            <i class="fas fa-copy"></i>
                        </button>
                        ${
                          !isStreaming
                            ? `<button
                                class="regenerate-button p-1.5 rounded-md bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-all duration-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                                title="Regenerate response"
                                aria-label="Regenerate response">
                                <i class="fas fa-redo-alt"></i>
                               </button>`
                            : ''
                        }
                    </div>
                    <div class="bg-gray-100 dark:bg-gray-800 p-5 rounded-r-lg rounded-bl-lg shadow-sm group hover:shadow-md transition-all duration-200">
                        <div class="prose dark:prose-invert prose-sm sm:prose-base lg:prose-lg max-w-none overflow-x-auto [&_pre]:my-4 [&_pre]:p-4 [&_pre]:bg-gray-50 dark:[&_pre]:bg-gray-900 [&_pre]:rounded-lg [&_code]:text-sm [&_code]:bg-gray-50 dark:[&_code]:bg-gray-900 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_p]:leading-relaxed [&_ul]:my-4 [&_ol]:my-4 [&_li]:my-1"
                             data-role="assistant-message">
                            ${sanitizedHtml}
                        </div>
                    </div>
                    <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                        ${new Date().toLocaleTimeString()}
                    </span>
                </div>
            `;
            chatBox.appendChild(messageDiv);

            // Apply syntax highlighting
            if (window.Prism) {
                window.Prism.highlightAllUnder(
                    messageDiv.querySelector('[data-role="assistant-message"]')
                );
            }
        } catch (error) {
            console.error('Error creating message element:', error);
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = `<p class="text-red-500">Error creating message: ${error.message}</p>`;
            chatBox.appendChild(errorDiv);
        }
    }

    // Auto-scroll
    chatBox.scrollTop = chatBox.scrollHeight;
}

/**
 * Appends the user's message
 */
function appendUserMessage(message) {
    if (!message || typeof message !== 'string') {
        console.error('Invalid message content.');
        return;
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = 'flex w-full mt-4 space-x-3 max-w-[85%] sm:max-w-md md:max-w-2xl ml-auto justify-end';
    messageDiv.innerHTML = `
        <div>
            <div class="relative bg-blue-600 text-white p-4 rounded-l-lg rounded-br-lg shadow-sm">
                <p class="text-[15px] leading-relaxed break-words overflow-x-auto whitespace-pre-wrap">${message}</p>
            </div>
            <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                ${new Date().toLocaleTimeString()}
            </span>
        </div>
    `;
    document.getElementById('chat-box').appendChild(messageDiv);
    document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;
}

/**
 * Renders all assistant messages present in the DOM on initial load (server-side or static).
 */
async function renderInitialAssistantMessages() {
    const assistantMessageDivs = document.querySelectorAll('[data-role="assistant-message"]');

    // Wait for dependencies to be available
    let attempts = 0;
    while ((!window.md || !window.DOMPurify || !window.he) && attempts < 50) {
        await new Promise(resolve => setTimeout(resolve, 100));
        attempts++;
    }

    if (!window.md || !window.DOMPurify || !window.he) {
        console.error('Required dependencies not available after 5 seconds');
        assistantMessageDivs.forEach(div => {
            div.innerHTML = `<p class="text-red-500">Error: Required dependencies not available. Please refresh the page.</p>`;
        });
        return;
    }

    const sanitizeOptions = {
        ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'a', 'span'],
        ALLOWED_ATTRS: {
            'a': ['href', 'title', 'target', 'rel'],
            'span': ['class'],
            'code': ['class'],
            'pre': ['class']
        }
    };

    assistantMessageDivs.forEach(div => {
        const rawContent = div.getAttribute('data-content');
        if (rawContent) {
            try {
                // First decode any HTML entities in the content
                const decodedContent = window.he.decode(rawContent);

                // Render markdown
                const renderedHtml = window.md.render(decodedContent);

                // Sanitize the rendered HTML
                const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, sanitizeOptions);

                // Update the content
                div.innerHTML = sanitizedHtml;

                // Apply syntax highlighting
                if (window.Prism) {
                    window.Prism.highlightAllUnder(div);
                }
            } catch (error) {
                console.error('Error rendering message:', error);
                // Show a fallback message if rendering fails
                div.innerHTML = `<p class="text-red-500">Error rendering message: ${error.message}</p>`;
            }
        }
    });
}

/**
 * Markdown-it initialization check
 */
if (!window.md) {
    console.error('Markdown renderer not initialized');
    if (window.utils) {
        window.utils.showFeedback('Failed to initialize markdown renderer', 'error');
    }
}

/**
 * Attach copy/regenerate functionality to chat action buttons
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
    console.log('Regenerate message logic goes here.');
    // Implement your regenerate behavior or call a helper
    // e.g. regenerateResponse();
}

/**
 * Drag-and-drop functionality
 */
function setupDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    dropZone.addEventListener('dragenter', () => {
        dropZone.classList.remove('hidden');
    });

    dropZone.addEventListener('dragleave', (e) => {
        if (!e.relatedTarget || !dropZone.contains(e.relatedTarget)) {
            dropZone.classList.add('hidden');
        }
    });

    dropZone.addEventListener('drop', (e) => {
        try {
            dropZone.classList.add('hidden');
            if (!window.utils) {
                console.error('Utils not initialized');
                return;
            }

            if (!e.dataTransfer?.files) {
                window.utils.showFeedback('No files dropped', 'error');
                return;
            }
            const files = Array.from(e.dataTransfer.files);
            if (files.length === 0) {
                window.utils.showFeedback('No files dropped', 'error');
                return;
            }
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
        } catch (error) {
            console.error('Error handling file drop:', error);
            if (window.utils) {
                window.utils.showFeedback('Failed to process dropped files', 'error');
            }
        } finally {
            dropZone.classList.add('hidden');
        }
    });
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

/**
 * Cleanup on page unload
 */
function cleanup() {
    try {
        window.removeEventListener('beforeunload', cleanup);

        // Clean up model select event listener
        const modelSelect = document.getElementById('model-select');
        if (modelSelect && modelSelect.previousHandler) {
            modelSelect.removeEventListener('change', modelSelect.previousHandler);
            modelSelect.previousHandler = null;
        }

        // Stop TokenUsageManager periodic updates
        if (window.tokenUsageManager) {
            window.tokenUsageManager.stopPeriodicUpdates();

            // Update final stats before cleanup
            try {
                window.tokenUsageManager.updateStats();
            } catch (error) {
                console.error('Error updating final token stats:', error);
            }
        }

        // Clean up any remaining event listeners
        const chatBox = document.getElementById('chat-box');
        if (chatBox) {
            chatBox.removeEventListener('click', attachActionButtonListeners);
        }

        console.debug('Chat cleanup completed successfully');
    } catch (error) {
        console.error('Error during cleanup:', error);
    }
}
window.addEventListener('beforeunload', cleanup);

/**
 * Creates a new chat
 */
async function createNewChat() {
    if (!window.utils) {
        console.error('Utils not initialized');
        return;
    }

    try {
        const newChatBtn = document.getElementById('new-chat-btn');
        if (newChatBtn) {
            newChatBtn.disabled = true;
        }

        const response = await window.utils.fetchWithCSRF('/chat/new_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (response.success && response.chat_id) {
            window.location.href = `/chat/chat_interface?chat_id=${response.chat_id}`;
        } else {
            throw new Error(response.error || 'Failed to create new chat');
        }
    } catch (error) {
        console.error('Error creating new chat:', error);
        window.utils.showFeedback(error.message || 'Failed to create new chat', 'error');
    } finally {
        const newChatBtn = document.getElementById('new-chat-btn');
        if (newChatBtn) {
            newChatBtn.disabled = false;
        }
    }
}

/**
 * Model change handler
 */
// Debounce function to prevent multiple rapid calls
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

let modelChangeInProgress = false;

async function handleModelChange() {
    if (!window.utils) {
        console.error('Utils not initialized');
        return;
    }

    if (modelChangeInProgress) {
        return;
    }

    const modelSelect = document.getElementById('model-select');
    const sendButton = document.getElementById('send-button');
    const modelId = modelSelect.value;
    const originalValue = modelSelect.getAttribute('data-original-value');

    // If the value hasn't changed, don't do anything
    if (modelId === originalValue) {
        return;
    }

    modelChangeInProgress = true;
    if (sendButton) {
        sendButton.disabled = true;
    }

    try {
        const response = await fetch('/chat/update_model', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.utils.getCSRFToken(),
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
            },
            body: JSON.stringify({
                'model_id': modelId,
                'chat_id': window.CHAT_CONFIG.chatId,
            }),
        });

        const data = await response.json();

        if (data.success) {
            window.utils.showFeedback('Model updated successfully', 'success');
            if (window.tokenUsageManager) {
                await window.tokenUsageManager.updateStats();
            }
            // Update the current model in the window config
            const selectedModel = window.CHAT_CONFIG.models.find(m => m.id === parseInt(modelId));
            if (selectedModel) {
                window.CHAT_CONFIG.currentModel = selectedModel;
            }
        } else {
            window.utils.showFeedback(data.error || 'Failed to update model', 'error');
            // Revert model selection on failure
            const previousModel = window.CHAT_CONFIG.currentModel;
            if (previousModel && modelSelect) {
                modelSelect.value = previousModel.id;
            }
        }
    } catch (error) {
        console.error('Error updating model:', error);
        window.utils.showFeedback('Error updating model', 'error');
        // Revert model selection on error
        const previousModel = window.CHAT_CONFIG.currentModel;
        if (previousModel && modelSelect) {
            modelSelect.value = previousModel.id;
        }
    } finally {
        modelChangeInProgress = false;
        // Re-enable send button
        if (sendButton) {
            sendButton.disabled = false;
        }
    }
}

/**
 * DOM readiness -> Start the chat
 */
document.addEventListener('DOMContentLoaded', async () => {
    await init();
});
