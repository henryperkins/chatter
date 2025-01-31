/* static/js/chat.js */

/**
 * @typedef {Object} Utils
 * @property {() => string} getCSRFToken
 * @property {(url: string, options?: object) => Promise<any>} fetchWithCSRF
 * @property {(message: string, type?: string, options?: object) => void} showFeedback
 * @property {(formData: FormData) => object} formDataToObject
 * @property {(dateString: string) => string} formatDate
 * @property {(func: Function, wait: number) => Function} debounce
 * @property {(func: Function, limit: number) => Function} throttle
 * @property {(element: HTMLElement, callback: Function, options?: object) => Promise<any>} withLoading
 */

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

async function initializeInterface() {
    // Attach event listeners, initialize components, etc.

    // Example: Attach event listener to the "Send" button
    const sendButton = document.getElementById('send-button');
    if (!sendButton) {
        console.error('Send button not found - check HTML ID');
        return;
    }
    sendButton.addEventListener('click', sendMessage);

    // Attach event listener for the message input (e.g., for "Enter" key)
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        });
    }

    // Initialize FileUploadManager if needed
    const chatId = window.CHAT_CONFIG.chatId;
    const userId = window.CHAT_CONFIG.userId;
    const uploadButton = document.getElementById('upload-button');
    const mobileUploadButton = document.getElementById('mobile-upload-button');
    const correctUploadBtn = window.innerWidth < 768 ? mobileUploadButton : uploadButton;

    if (!window.fileUploadManager) {
        window.fileUploadManager = new window.FileUploadManager(chatId, userId, correctUploadBtn);
    }

    // Initialize TokenUsageManager
    if (window.TokenUsageManager && window.CHAT_CONFIG.chatId) {
        console.log('Initializing TokenUsageManager with chatId:', window.CHAT_CONFIG.chatId);
        window.tokenUsageManager = new window.TokenUsageManager({
            chatId: window.CHAT_CONFIG.chatId
        });
        // Force an immediate update of token usage stats
        try {
            await window.tokenUsageManager.updateStats();
        } catch (error) {
            console.error('Error updating token stats:', error);
        }
    } else {
        console.error('TokenUsageManager initialization failed - missing dependencies');
    }

    // New chat button
    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', createNewChat);
    }

    // Edit model button
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

    // Handle model changes
    if (modelSelect) {
        modelSelect.addEventListener('change', handleModelChange);
    }

    // Edit Title Button
    const editTitleBtn = document.getElementById('edit-title-btn');
    if (editTitleBtn) {
        editTitleBtn.addEventListener('click', handleEditTitle);
    }

    function handleEditTitle() {
        // Implement the logic to edit chat title
    }

    // Delete Chat Buttons
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

    // Call other setup functions as needed
    attachActionButtonListeners();
    renderInitialAssistantMessages();
    // ... any other initialization code
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
 * Message handling functions
 */
async function sendMessage() {
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    if (!messageInput || !sendButton) return;

    const messageText = messageInput.value.trim();
    if (!messageText && window.fileUploadManager.uploadedFiles.length === 0) {
        utils.showFeedback('Please enter a message or upload files.', 'error');
        return;
    }

    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect?.value;
    const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
    const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

    // Prepare the form data
    const formData = new FormData();
    if (messageText) {
        formData.append('message', messageText);
        appendUserMessage(messageText);
    }

    window.fileUploadManager.uploadedFiles.forEach(file => {
        formData.append('files[]', file);
    });
    formData.append('model_id', modelId);
    formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);

    try {
        const chatBox = document.getElementById('chat-box');
        if (chatBox.lastElementChild?.querySelector('[data-role="assistant-message"]')) {
            chatBox.lastElementChild.remove();
        }

        await utils.withLoading(sendButton, async () => {
            if (useStreaming) {
                await handleStreamingResponse(formData);
            } else {
                await handleNormalResponse(formData);
            }
        });

        // Clear input and files
        messageInput.value = '';
        messageInput.style.height = 'auto';
        window.fileUploadManager.uploadedFiles = [];
        window.fileUploadManager.renderFileList();

        // Update token usage
        if (window.tokenUsageManager) {
            await window.tokenUsageManager.updateStats();
        }
    } catch (error) {
        console.error('Error sending message:', error);
        removeTypingIndicator();
        utils.showFeedback(
            error.message === 'Failed to fetch' ?
            'Network error: Please check your internet connection.' :
            error.message,
            'error'
        );
    }
}

async function handleStreamingResponse(formData) {
    const response = await fetch('/', {
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
        if (response.status === 403) {
            throw new Error('Session expired - please refresh the page');
        }
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulatedResponse = '';
    let lastUpdateTime = Date.now();
    const updateInterval = 100;

    showTypingIndicator();

    try {
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

        if (accumulatedResponse) {
            appendAssistantMessage(accumulatedResponse, false);
        }
    } finally {
        removeTypingIndicator();
    }
}

async function handleNormalResponse(formData) {
    showTypingIndicator();

    try {
        const response = await utils.fetchWithCSRF('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.success) {
            throw new Error(response.error || 'Failed to send message');
        }

        if (response.message?.content) {
            appendAssistantMessage(response.message.content);
        } else {
            throw new Error('No message received from server');
        }
    } finally {
        removeTypingIndicator();
    }
}


/**
 * Message display functions
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
                    ${!isStreaming ? `
                        <button
                            class="regenerate-button p-1.5 rounded-md bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200 shadow-sm"
                            title="Regenerate response"
                            aria-label="Regenerate response">
                            <i class="fas fa-redo-alt"></i>
                        </button>
                    ` : ''}
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
            window.Prism.highlightAllUnder(messageDiv.querySelector('[data-role="assistant-message"]'));
        }
    }

    // Auto-scroll
    chatBox.scrollTop = chatBox.scrollHeight;

    // Initialize FileUploadManager if needed
    const chatId = window.CHAT_CONFIG.chatId;
    const userId = window.CHAT_CONFIG.userId;
    const correctUploadBtn = window.innerWidth < 768 ? mobileUploadButton : uploadButton;

    if (!window.fileUploadManager) {
        window.fileUploadManager = new window.FileUploadManager(chatId, userId, correctUploadBtn);
    }

    // Initialize TokenUsageManager
    if (window.TokenUsageManager && window.CHAT_CONFIG.chatId) {
        console.log('Initializing TokenUsageManager with chatId:', window.CHAT_CONFIG.chatId);
        window.tokenUsageManager = new window.TokenUsageManager({
            chatId: window.CHAT_CONFIG.chatId
        });
        // Force an immediate update of token usage stats
        try {
            await window.tokenUsageManager.updateStats();
        } catch (error) {
            console.error('Error updating token stats:', error);
        }
    } else {
        console.error('TokenUsageManager initialization failed - missing dependencies');
    }

    // Mobile menu is initialized in base.js

    // Fix chat input visibility (ensure chat box doesn't overlap the input area)
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

        // Initial setup
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

        // Dark mode styles
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

        // Update on resize (keyboard show/hide)
        window.addEventListener('resize', updateChatBoxHeight);
        updateChatBoxHeight();
    }

    // New chat button
    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', createNewChat);
    }

    // Edit model button
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

    // Handle model changes
    if (modelSelect) {
        modelSelect.addEventListener('change', handleModelChange);
    }

/**
 * Attach event listeners to action buttons within the chat messages
 */
    // Set up drag and drop
    setupDragAndDrop();

    console.debug('Chat initialization completed successfully');
    hideLoadingIndicator();
}

/**
 * Attach event listeners to action buttons within the chat messages
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
            await regenerateResponse();
        }
    });
}

window.init = init;

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
        const sendButton = document.getElementById('send-button');
        if (messageInput) {
            // Remove exact references (not anonymous)
            messageInput.removeEventListener('input', utils.debounce(handleMessageInput, 100));
            messageInput.removeEventListener('keydown', handleMessageKeydown);
        }
        if (sendButton) {
            sendButton.removeEventListener('click', throttledSendMessage);
        }
        console.debug('Chat cleanup completed successfully');
    } catch (error) {
        console.error('Error during cleanup:', error);
    }
}

// Attach cleanup to window unload
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
 * Handle regenerate message
 */
async function regenerateResponse() {
    console.log('sendMessage function called');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    if (!messageInput || !sendButton) return;

    const messageText = messageInput.value.trim();
    if (!messageText && window.fileUploadManager.uploadedFiles.length === 0) {
        utils.showFeedback('Please enter a message or upload files.', 'error');
        return;
    }

    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect?.value;
    const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
    const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

    // Prepare the form data
    const formData = new FormData();
    if (messageText) {
        formData.append('message', messageText);
        // Append user's message immediately
        appendUserMessage(messageText);
    }

    // Add files if present
    window.fileUploadManager.uploadedFiles.forEach(file => {
        formData.append('files[]', file);
    });

    // Add CSRF token
    formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);

    try {
        // Clear any existing streaming message
        const chatBox = document.getElementById('chat-box');
        if (chatBox.lastElementChild?.querySelector('[data-role="assistant-message"]')) {
            chatBox.lastElementChild.remove();
        }

        await utils.withLoading(sendButton, async () => {
            if (useStreaming) {
                const response = await fetch('/chat/', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Chat-ID': window.CHAT_CONFIG.chatId,
                        'Accept': 'text/event-stream',
                        'X-CSRFToken': utils.getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let accumulatedResponse = '';
                let lastUpdateTime = Date.now();
                const updateInterval = 100; // More frequent updates for smoother experience

                showTypingIndicator();

                try {
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
                } finally {
                    removeTypingIndicator();
                }
            } else {
                showTypingIndicator();

                try {
                    const response = await utils.fetchWithCSRF('/chat/', {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-Chat-ID': window.CHAT_CONFIG.chatId,
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    });

                    if (!response.success) {
                        throw new Error(response.error || 'Failed to send message');
                    }

                    if (response.message?.content) {
                        appendAssistantMessage(response.message.content);
                    } else {
                        throw new Error('No message received from server');
                    }
                } finally {
                    removeTypingIndicator();
                }
            }
        });

        // Clear input and files after successful send
        messageInput.value = '';
        messageInput.style.height = 'auto';
        window.fileUploadManager.uploadedFiles = [];
        window.fileUploadManager.renderFileList();

        // Update token usage
        if (window.tokenUsageManager) {
            await window.tokenUsageManager.updateStats();
        }
    } catch (error) {
        console.error('Error sending message:', error);
        removeTypingIndicator();
        utils.showFeedback(
            error.message === 'Failed to fetch' ?
            'Network error: Please check your internet connection.' :
            error.message,
            'error'
        );
    }
}


/**
 * Adjusts the textarea height dynamically
 */
function adjustTextareaHeight(textarea) {
    if (!textarea) return;

    // Store the current scroll position
    const scrollPos = window.scrollY;

    // Reset height to auto to get proper scrollHeight
    textarea.style.height = 'auto';

    // Calculate new height with limits
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 44), 120);
    textarea.style.height = `${newHeight}px`;

    // Update chat box padding to prevent content hiding
    const chatBox = document.getElementById('chat-box');
    if (chatBox) {
        const bottomPadding = newHeight + (window.innerWidth < 768 ? 100 : 80);
        chatBox.style.paddingBottom = `${bottomPadding}px`;
    }

    // Restore scroll position on mobile
    if (window.innerWidth < 768) {
        window.scrollTo(0, scrollPos);
    }
}

        if (document.getElementById('chat-box').lastElementChild) {
            document.getElementById('chat-box').lastElementChild.remove();
        }

        showTypingIndicator();

        const formData = new FormData();
        formData.append('message', lastUserMessage);

        // Check for streaming
        const modelSelect = document.getElementById('model-select');
        const modelId = modelSelect?.value;
        const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
        const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

        let responseData;
        if (useStreaming) {
            formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);
            const response = await fetch('/chat/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'X-CSRFToken': utils.getCSRFToken(),
                    'Accept': 'text/event-stream',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedResponse = '';
            const updateInterval = 500; // Update every 500ms
            let lastUpdateTime = Date.now();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const streamData = line.slice(6);
                        if (streamData === '[DONE]') break;
                        accumulatedResponse += streamData;

                        const now = Date.now();
                        if (now - lastUpdateTime > updateInterval || streamData.endsWith('\n')) {
                            appendAssistantMessage(accumulatedResponse, true);
                            lastUpdateTime = now;
                        }
                    }
                }
            }

            // Final update after streaming is complete
            appendAssistantMessage(accumulatedResponse, false);
        } else {
            responseData = await utils.fetchWithCSRF('/chat/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (responseData.message?.content) {
                appendAssistantMessage(responseData.message.content);
            } else {
                throw new Error(responseData.error || 'Failed to regenerate response');
            }
        }
    } catch (error) {
        console.error('Error regenerating response:', error);
        utils.showFeedback(error.message || 'An unexpected error occurred', 'error');
    } finally {
        const sendButton = document.getElementById('send-button');
        if (sendButton) {
            sendButton.disabled = false;
        }
        removeTypingIndicator();
    }
}

async function handleRegenerateMessage(target) {
    // Implement the logic to handle regenerate message
    console.log('Regenerate message logic goes here');
}



/**
 * Appends the assistant's message to the chat
 */

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
 * Renders all assistant messages present in the DOM on initial load.
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
            window.Prism.highlightAllUnder(div);
        }
    });
}

// Initialize markdown-it with secure defaults
window.md = window.markdownit({
    html: false, // Disable HTML tags in markdown for security
    linkify: true,
    typographer: true,
    breaks: true,
    xhtmlOut: true,
    maxNesting: 100, // Increase max nesting level
    quotes: '“”‘’', // Proper typographic quotes
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
        // use basic escaping if no language is specified or Prism can't highlight
        return '<pre class="language-unknown"><code>' +
               window.md.utils.escapeHtml(str) + '</code></pre>';
    }
}).disable(['image', 'html_block', 'html_inline']); // Disable potentially unsafe features

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', async () => {
    await init();
});
function handleModelChange() {
    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect.value;

    fetch('/update_model', {
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
    .then(data => {
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

