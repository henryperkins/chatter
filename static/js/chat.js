/* static/js/chat.js */

const utils = window.utils;

/**
 * Main initialization function
 */
async function init() {
    try {
        console.log('Initializing chat interface');
        showLoadingIndicator();

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
        utils.showFeedback(error.message || 'Failed to initialize chat', 'error');
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

    // 3. Initialize TokenUsageManager
    if (window.TokenUsageManager && chatId) {
        console.log('Initializing TokenUsageManager with chatId:', chatId);
        window.tokenUsageManager = new window.TokenUsageManager({ chatId });
        // Force an immediate update of token usage stats
        try {
            await window.tokenUsageManager.updateStats();
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
            } else {
                utils.showFeedback('No model selected', 'error');
            }
        });
    }

    // 7. Handle model changes
    if (modelSelect) {
        modelSelect.addEventListener('change', handleModelChange);
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
    indicator.className = 'flex w-full mt-2 space-x-3 max-w-3xl';
    indicator.setAttribute('role', 'status');
    indicator.setAttribute('aria-label', 'Assistant is typing');
    indicator.innerHTML = `
        <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700"></div>
        <div class="relative max-w-3xl">
            <div class="bg-gray-100 dark:bg-gray-800 p-3 rounded-r-lg rounded-bl-lg">
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
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    if (!messageInput || !sendButton) {
        utils.showFeedback('Chat interface not properly initialized', 'error');
        return;
    }

    const messageText = messageInput.value.trim();
    const hasUploadedFiles = window.fileUploadManager?.uploadedFiles?.length > 0;

    if (!messageText && !hasUploadedFiles) {
        utils.showFeedback('Please enter a message or upload files.', 'error');
        return;
    }

    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect?.value;
    const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
    const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

    try {
        // Clear previous errors
        document.querySelectorAll('.error-indicator').forEach(el => el.remove());

        const formData = new FormData();
        if (messageText) {
            formData.append('message', messageText);
            appendUserMessage(messageText);
        }
        // Add files if available
        if (window.fileUploadManager?.uploadedFiles?.length > 0) {
            window.fileUploadManager.uploadedFiles.forEach(file => {
                formData.append('files[]', file);
            });
        }

        formData.append('model_id', modelId);
        formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);
        sendButton.disabled = true;
        sendButton.classList.add('sending');

        try {
            await utils.withLoading(sendButton, async () => {
                const chatBox = document.getElementById('chat-box');
                if (chatBox.lastElementChild?.querySelector('[data-role="assistant-message"]')) {
                    chatBox.lastElementChild.remove();
                }

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
            });
        } finally {
            sendButton.disabled = false;
            sendButton.classList.remove('sending');
        }

        // Update token usage
        if (window.tokenUsageManager) {
            await window.tokenUsageManager.updateStats();
        }
    } catch (error) {
        console.error('Error sending message:', error);

        // Show persistent error with retry
        const errorMessage = error instanceof Error ? error.message : 'Failed to send message';
        const sanitizedError = errorMessage.replace(/<\/?[^>]+(>|$)/g, "");

        const errorIndicator = document.createElement('div');
        errorIndicator.className = 'error-indicator bg-red-100 border border-red-400 p-2 mb-2 rounded';
        errorIndicator.innerHTML = `
            <span class="text-red-700">${sanitizedError}</span>
            <button class="ml-2 text-red-700 hover:text-red-900 retry-button">Retry</button>
        `;
        messageInput.parentNode.insertBefore(errorIndicator, messageInput);

        errorIndicator.querySelector('.retry-button').addEventListener('click', () => {
            errorIndicator.remove();
            sendMessage();
        });
    } finally {
        removeTypingIndicator();
    }
}

async function handleStreamingResponse(formData) {
    showTypingIndicator();
    let reader;

    try {
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

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const streamData = line.slice(6);
                    if (streamData === '[DONE]') break;
                    if (streamData.startsWith('[ERROR]')) {
                        throw new Error(streamData.slice(7).trim());
                    }
                    accumulatedResponse += streamData;

                    const now = Date.now();
                    if (now - lastUpdateTime > updateInterval) {
                        appendAssistantMessage(accumulatedResponse, true);
                        lastUpdateTime = now;
                    }
                }
            }
        }

        // Final update
        if (accumulatedResponse) {
            appendAssistantMessage(accumulatedResponse, false);
        }
    } catch (error) {
        console.error('Streaming error:', error);
        // Re-throw the original error without wrapping it
        throw error instanceof Error ? error : new Error(error.toString());
    } finally {
        if (reader) {
            try {
                await reader.cancel();
            } catch (e) {
                console.error('Error canceling stream:', e);
            }
        }
        removeTypingIndicator();
    }
}

async function handleNormalResponse(formData) {
    showTypingIndicator();
    try {
        const data = await utils.fetchWithCSRF('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!data) {
            throw new Error('Server returned no response');
        }

        if (data.error) {
            // Handle nested error objects
            const errorMessage = typeof data.error === 'object'
                ? data.error.message || JSON.stringify(data.error)
                : data.error;
            throw new Error(errorMessage);
        }

        if (!data.message?.content) {
            throw new Error('Server response missing message content');
        }

        appendAssistantMessage(data.message.content);
    } catch (error) {
        console.error('Normal response error:', error);
        throw error; // Re-throw to be caught in sendMessage
    } finally {
        removeTypingIndicator();
    }
}

/**
 * Appends the assistant's message to the chat
 */
async function appendAssistantMessage(message, isStreaming = false) {
    if (!message) return;

    const chatBox = document.getElementById('chat-box');
    if (!chatBox) return;

    const DOMPurifyOptions = {
        ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'a', 'span'],
        ALLOWED_ATTRS: {
            'a': ['href', 'title', 'target', 'rel'],
            'span': ['class'],
            'code': ['class'],
            'pre': ['class']
        }
    };

    // For streaming updates, reuse the last assistant message div
    let messageDiv;
    if (isStreaming && chatBox.lastElementChild?.querySelector('[data-role="assistant-message"]')) {
        messageDiv = chatBox.lastElementChild;
        const contentDiv = messageDiv.querySelector('[data-role="assistant-message"]');
        if (contentDiv) {
            const renderedHtml = window.md.render(message);
            contentDiv.innerHTML = window.DOMPurify.sanitize(renderedHtml, DOMPurifyOptions);
            if (window.Prism) {
                window.Prism.highlightAllUnder(contentDiv);
            }
        }
    } else {
        messageDiv = document.createElement('div');
        messageDiv.className = 'flex w-full mt-2 space-x-2 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl';

        const renderedHtml = window.DOMPurify.sanitize(
            window.md.render(message),
            DOMPurifyOptions
        );

        messageDiv.innerHTML = `
            <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gray-300 dark:bg-gray-700" role="img"
                aria-label="Assistant avatar"></div>
            <div class="relative flex-1">
                <div class="absolute right-2 top-2 flex items-center space-x-1 z-10">
                    <button
                        class="copy-button p-1.5 rounded-md bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200 shadow-sm"
                        title="Copy to clipboard"
                        data-raw-content="${message.replace(/"/g, '&quot;')}"
                        aria-label="Copy message to clipboard">
                        <i class="fas fa-copy"></i>
                    </button>
                    ${
                      !isStreaming
                        ? `<button
                            class="regenerate-button p-1.5 rounded-md bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200 shadow-sm"
                            title="Regenerate response"
                            aria-label="Regenerate response">
                            <i class="fas fa-redo-alt"></i>
                           </button>`
                        : ''
                    }
                </div>
                <div class="bg-gray-100 dark:bg-gray-800 p-3 pr-16 rounded-r-lg rounded-bl-lg">
                    <div class="prose dark:prose-invert prose-sm max-w-none overflow-x-auto" data-role="assistant-message">
                        ${renderedHtml}
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
    messageDiv.className = 'flex w-full mt-2 space-x-2 max-w-[85%] sm:max-w-md md:max-w-2xl ml-auto justify-end';
    messageDiv.innerHTML = `
        <div>
            <div class="relative bg-blue-600 text-white p-2.5 rounded-l-lg rounded-br-lg">
                <p class="text-[15px] leading-normal break-words overflow-x-auto text-sm">${message}</p>
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
function renderInitialAssistantMessages() {
    const assistantMessageDivs = document.querySelectorAll('[data-role="assistant-message"]');

    assistantMessageDivs.forEach(div => {
        const rawContent = div.getAttribute('data-content');
        if (rawContent) {
            // Render and sanitize the message content
            const renderedHtml = window.md.render(rawContent);
            const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, {
                ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'a', 'span'],
                ALLOWED_ATTRS: {
                    'a': ['href', 'title', 'target', 'rel'],
                    'span': ['class'],
                    'code': ['class'],
                    'pre': ['class']
                }
            });
            div.innerHTML = sanitizedHtml;
            // Apply syntax highlighting
            if (window.Prism) {
                window.Prism.highlightAllUnder(div);
            }
        }
    });
}

/**
 * Markdown-it initialization (secure defaults)
 */
window.md = window.markdownit({
    html: false,
    linkify: true,
    typographer: true,
    breaks: true,
    xhtmlOut: true,
    maxNesting: 100,
    quotes: ["\"\"", "''"],
    highlight: function (str, lang) {
        if (lang && window.Prism && window.Prism.languages[lang]) {
            try {
                return '<pre class="language-' + lang + '"><code>' +
                    window.Prism.highlight(str, window.Prism.languages[lang], lang) +
                    '</code></pre>';
            } catch (error) {
                console.error('Prism highlighting error:', error);
            }
        }
        // Basic escaping if no language is specified
        return '<pre class="language-unknown"><code>' +
                window.md.utils.escapeHtml(str) + '</code></pre>';
    }
}).disable(['image', 'html_block', 'html_inline']);

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
    try {
        const rawContent = button.dataset.rawContent || '';
        await navigator.clipboard.writeText(rawContent);
        utils.showFeedback('Message copied to clipboard!', 'success');
    } catch (err) {
        console.error('Clipboard copy failed:', err);
        utils.showFeedback('Failed to copy message', 'error');
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
            if (!e.dataTransfer?.files) {
                utils.showFeedback('No files dropped', 'error');
                return;
            }
            const files = Array.from(e.dataTransfer.files);
            if (files.length === 0) {
                utils.showFeedback('No files dropped', 'error');
                return;
            }
            if (window.fileUploadManager) {
                const { validFiles, errors } = window.fileUploadManager.processFiles(files);
                if (errors.length > 0) {
                    errors.forEach(error => utils.showFeedback(error.errors.join(', '), 'error'));
                }
                if (validFiles.length > 0) {
                    window.fileUploadManager.uploadedFiles.push(...validFiles);
                    window.fileUploadManager.renderFileList();
                }
            }
        } catch (error) {
            console.error('Error handling file drop:', error);
            utils.showFeedback('Failed to process dropped files', 'error');
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
        const messageInput = document.getElementById('message-input');
        window.removeEventListener('beforeunload', cleanup);

        // Example: removing event listeners if needed
        // messageInput.removeEventListener(...);

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
    try {
        const newChatBtn = document.getElementById('new-chat-btn');
        if (newChatBtn) {
            newChatBtn.disabled = true;
        }

        const response = await utils.fetchWithCSRF('/chat/new_chat', {
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
        utils.showFeedback(error.message || 'Failed to create new chat', 'error');
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
function handleModelChange() {
    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect.value;

    fetch('/chat/update_model', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': utils.getCSRFToken(),
            'X-Chat-ID': window.CHAT_CONFIG.chatId,
        },
        body: JSON.stringify({
            'model_id': modelId,
            'chat_id': window.CHAT_CONFIG.chatId,
        }),
    })
    .then(response => response.json())
    .then(async data => {
        if (data.success) {
            utils.showFeedback('Model updated successfully', 'success');
            if (window.tokenUsageManager) {
                window.tokenUsageManager.updateStats();
            }
        } else {
            utils.showFeedback(data.error || 'Failed to update model', 'error');
        }
    })
    .catch(error => {
        console.error('Error updating model:', error);
        utils.showFeedback('Error updating model', 'error');
    });
}

/**
 * DOM readiness -> Start the chat
 */
document.addEventListener('DOMContentLoaded', async () => {
    await init();
});
