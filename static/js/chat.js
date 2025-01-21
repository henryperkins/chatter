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
 * @property {(element: HTMLElement, options?: object) => void} showLoading
 * @property {(element: HTMLElement, originalContent: string) => void} hideLoading
 * @property {(element: HTMLElement, callback: Function, options?: object) => Promise<any>} withLoading
 */

/**
 * @typedef {Object} WindowExtensions
 * @property {Utils} utils
 * @property {any} FileUploadManager
 * @property {any} TokenUsageManager
 * @property {any} md
 * @property {any} CHAT_CONFIG
 * @property {any} Prism
 * @property {any} DOMPurify
 * @property {any} fileUploadManager
 * @property {any} tokenUsageManager
 */

const utils = window.utils;

// Debounced handler for input
const handleMessageInput = (e) => {
    console.log('handleMessageInput called');
    adjustTextareaHeight(e.target);
};

// Throttled handler for send
const throttledSendMessage = utils.throttle(() => {
    sendMessage();
}, 1000);

// Keydown handler
const handleMessageKeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
};

/**
 * Main initialization function
 */
window.renderMessages = function(messages) {
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = ''; // Clear existing messages

    messages.forEach(message => {
        if (message.role === 'user') {
            appendUserMessage(message.content);
        } else {
            appendAssistantMessage(message.content);
        }
    });
}

async function init() {
    console.log('Initializing chat interface');

    // Set up mobile viewport height
    function updateVH() {
        let vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    }

    updateVH();
    window.addEventListener('resize', updateVH);

    // Cache DOM elements
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatBox = document.getElementById('chat-box');
    const editTitleBtn = document.getElementById('edit-title-btn');
    const uploadButton = document.getElementById('upload-button');
    const mobileUploadButton = document.getElementById('mobile-upload-button');
    const fileInput = document.getElementById('file-input');

    // Verify critical elements exist
    if (!messageInput || !sendButton || !chatBox) {
        console.error('Critical UI elements are missing');
        return;
    }

    // Improve mobile input handling
    if (messageInput) {
        // Initial height adjustment
        adjustTextareaHeight(messageInput);

        // Handle input changes
        messageInput.addEventListener('input', utils.debounce(() => {
            adjustTextareaHeight(messageInput);
        }, 100));

        // Handle focus
        messageInput.addEventListener('focus', () => {
            setTimeout(() => {
                messageInput.scrollIntoView({ behavior: 'smooth' });
            }, 300);
        });

        // Prevent unwanted zoom
        messageInput.addEventListener('touchstart', (e) => {
            if (e.touches.length > 1) {
                e.preventDefault();
            }
        }, { passive: false });

        // Handle keydown for send
        messageInput.addEventListener('keydown', handleMessageKeydown);
    }

    // Improve button feedback
    [sendButton, uploadButton, mobileUploadButton].forEach(button => {
        if (button) {
            button.addEventListener('touchstart', () => {
                button.style.transform = 'scale(0.95)';
            });

            button.addEventListener('touchend', () => {
                button.style.transform = 'scale(1)';
            });
        }
    });

    // Handle mobile keyboard
    let isKeyboardVisible = false;

    window.addEventListener('resize', () => {
        const newIsKeyboardVisible = window.innerHeight < window.outerHeight;
        if (isKeyboardVisible !== newIsKeyboardVisible) {
            isKeyboardVisible = newIsKeyboardVisible;
            if (chatBox) {
                chatBox.style.maxHeight = isKeyboardVisible ?
                    `${window.innerHeight - 120}px` :
                    'calc(100vh - 120px)';
            }
        }
    });

    // Attach send button listener
    sendButton.addEventListener('click', throttledSendMessage);

    // Edit title button
    if (editTitleBtn) {
        editTitleBtn.addEventListener('click', async () => {
            try {
                const chatTitle = document.getElementById('chat-title');
                const currentTitle = chatTitle?.textContent?.split('-')[0].trim() || 'New Chat';
                const newTitle = prompt('Enter new chat title:', currentTitle);

                if (!newTitle || newTitle === currentTitle) return;

                const response = await utils.fetchWithCSRF(
                    `/chat/update_chat_title/${window.CHAT_CONFIG.chatId}`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: newTitle.trim() })
                    }
                );

                if (response.success) {
                    const modelName = chatTitle.textContent.split('-')[1]?.trim() || '';
                    chatTitle.textContent = `${newTitle} ${modelName ? '- ' + modelName : ''}`;
                    utils.showFeedback('Title updated successfully', 'success');
                } else {
                    throw new Error(response.error || 'Failed to update title');
                }
            } catch (error) {
                utils.showFeedback(error.message, 'error');
            }
        });
    }

    // File upload functionality
    if (uploadButton && fileInput) {
        uploadButton.addEventListener('click', () => {
            fileInput.click();
        });
    }
    if (mobileUploadButton && fileInput) {
        mobileUploadButton.addEventListener('click', () => {
            fileInput.click();
        });
    }
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            const files = Array.from(e.target.files || []);
            if (window.fileUploadManager) {
                const { validFiles, errors } = window.fileUploadManager.processFiles(files);
                if (errors.length > 0) {
                    errors.forEach(error =>
                        utils.showFeedback(error.errors.join(', '), 'error')
                    );
                }
                if (validFiles.length > 0) {
                    window.fileUploadManager.uploadedFiles.push(...validFiles);
                    window.fileUploadManager.renderFileList();
                }
            }
        });
    }

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

    // Event delegation for message actions
    chatBox.addEventListener('click', (event) => {
        const target = event.target.closest('button');
        if (!target) return;

        if (target.classList.contains('copy-button')) {
            handleCopyMessage(target);
        } else if (target.classList.contains('regenerate-button')) {
            handleRegenerateMessage(target);
        }
    });

    // Set up drag and drop
    setupDragAndDrop();

    console.debug('Chat initialization completed successfully');
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
 * Sends a new message
 */
async function sendMessage() {
    // Clear any existing streaming message
    const chatBox = document.getElementById('chat-box');
    if (chatBox.lastElementChild &&
        chatBox.lastElementChild.querySelector('.bg-gray-100')) {
        chatBox.lastElementChild.remove();
    }

    console.log('sendMessage function called');
    // Update token usage after sending
    if (window.tokenUsageManager) {
        window.tokenUsageManager.updateStats();
    }

    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    if (!messageInput || !sendButton) return;

    if (messageInput.value.trim() === '' && window.fileUploadManager.uploadedFiles.length === 0) {
        utils.showFeedback('Please enter a message or upload files.', 'error');
        return;
    }

    const messageText = messageInput.value.trim();
    const formData = new FormData();

    // Add message text if present
    if (messageText) {
        formData.append('message', messageText);
        // Append user's message to chat immediately
        appendUserMessage(messageText);
    }

    // Add files if present
    window.fileUploadManager.uploadedFiles.forEach(file => {
        formData.append('files[]', file);
    });

    try {
        await utils.withLoading(sendButton, async () => {
            // Add CSRF token to formData
            formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);

            const response = await utils.fetchWithCSRF('/chat/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response) {
                throw new Error('No response received from server');
            }
            if (response.error) {
                throw new Error(response.error);
            }

            // Append assistant response
            if (response.message && response.message.content) {
                appendAssistantMessage(response.message.content);
            } else {
                throw new Error('No message received from server');
            }

            // Clear input and files
            messageInput.value = '';
            window.fileUploadManager.uploadedFiles = [];
            window.fileUploadManager.renderFileList();

            // Update token usage stats after sending message
            if (window.tokenUsageManager) {
                await window.tokenUsageManager.updateStats();
            }

            // Show success feedback
            utils.showFeedback('Message sent successfully', 'success');
        }, { text: 'Sending...' });
    } catch (error) {
        if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
            utils.showFeedback('Network error: Please check your internet connection.', 'error');
        } else {
            utils.showFeedback(error.message, 'error');
        }
        console.error('Error in sendMessage:', error);
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

/**
 * Handles model changes
 */
async function handleModelChange() {
    const modelSelect = document.getElementById('model-select');
    if (!modelSelect) return;

    const modelId = modelSelect.value;
    const originalValue = modelSelect.dataset.originalValue;

    try {
        await utils.withLoading(modelSelect, async () => {
            const response = await utils.fetchWithCSRF('/chat/update_model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_id: modelId,
                    chat_id: window.CHAT_CONFIG.chatId
                })
            });

            if (response.success) {
                // Update UI elements
                const chatTitle = document.getElementById('chat-title');
                if (chatTitle) {
                    const currentTitle = chatTitle.textContent.split('-')[0].trim();
                    const selectedOption = modelSelect.options[modelSelect.selectedIndex];
                    chatTitle.textContent = `${currentTitle} - ${selectedOption.textContent}`;
                }

                // Update token usage display if needed
                if (window.tokenUsageManager) {
                    await window.tokenUsageManager.updateStats();
                }

                // Update model configuration
                modelSelect.dataset.originalValue = modelId;
                utils.showFeedback('Model updated successfully', 'success');

                // Handle o1 model UI adjustments
                if (response.model.requires_o1_handling) {
                    adjustUIForO1Model(response.model);
                } else {
                    resetUIForStandardModel();
                }
            } else {
                throw new Error(response.error || 'Failed to update model');
            }
        });
    } catch (error) {
        utils.showFeedback(error.message, 'error');
        modelSelect.value = originalValue;
    }
}

function adjustUIForO1Model(model) {
    // Disable streaming options for o1 models
    const streamingElements = document.querySelectorAll('.streaming-option');
    streamingElements.forEach(el => {
        el.classList.add('hidden');
    });

    // Update token limit display
    const tokenLimit = document.getElementById('tokens-limit');
    if (tokenLimit) {
        tokenLimit.textContent = `/ ${model.max_completion_tokens.toLocaleString()} max`;
    }
}

function resetUIForStandardModel() {
    // Re-enable streaming options
    const streamingElements = document.querySelectorAll('.streaming-option');
    streamingElements.forEach(el => {
        el.classList.remove('hidden');
    });

    // Reset token limit display
    const tokenLimit = document.getElementById('tokens-limit');
    if (tokenLimit) {
        const defaultLimit = window.CHAT_CONFIG.defaultMaxTokens || 16384;
        tokenLimit.textContent = `/ ${defaultLimit.toLocaleString()} max`;
    }
}

/**
 * Handle copy message action
 */
async function handleCopyMessage(button) {
    try {
        const rawContent = button.dataset.rawContent;
        const content = rawContent || button.closest('.max-w-3xl').querySelector('.prose').textContent;
        await navigator.clipboard.writeText(content);
        utils.showFeedback('Copied to clipboard!', 'success');
    } catch (error) {
        console.error('Error copying message:', error);
        utils.showFeedback('Failed to copy message', 'error');
    }
}

/**
 * Handle message regeneration
 */
async function handleRegenerateMessage(button) {
    try {
        button.disabled = true;
        await regenerateResponse(button);
    } catch (error) {
        console.error('Error regenerating message:', error);
        utils.showFeedback('Failed to regenerate message', 'error');
    } finally {
        button.disabled = false;
    }
}

/**
 * Regenerate the assistant's last response
 */
async function regenerateResponse(button) {
    button.disabled = true;

    // Update token usage
    if (window.tokenUsageManager) {
        await window.tokenUsageManager.updateStats();
    }

    try {
        const chatId = window.CHAT_CONFIG.chatId;
        if (!chatId) {
            utils.showFeedback('Chat ID not found', 'error');
            return;
        }

        // Grab last user message from DOM
        const messages = Array.from(document.getElementById('chat-box').children);
        let lastUserMessage = null;
        for (let i = messages.length - 1; i >= 0; i--) {
            const messageDiv = messages[i];
            if (messageDiv.querySelector('.bg-blue-600')) {
                lastUserMessage = messageDiv.querySelector('.bg-blue-600 p').textContent;
                break;
            }
        }
        if (!lastUserMessage) {
            utils.showFeedback('No message found to regenerate', 'error');
            return;
        }

        // Remove last assistant messages
        while (document.getElementById('chat-box').lastElementChild &&
            !document.getElementById('chat-box').lastElementChild.querySelector('.bg-blue-600')) {
            document.getElementById('chat-box').lastElementChild.remove();
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


            if (responseData.response) {
                appendAssistantMessage(responseData.response);
            } else {
                throw new Error(responseData.error || 'Failed to regenerate response');
            }
        }
    } catch (error) {
        console.error('Error regenerating response:', error);
        utils.showFeedback(error.message, 'error');
    } finally {
        button.disabled = false;
        removeTypingIndicator();
    }
}

/**
 * Show typing indicator
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

/**
 * Remove typing indicator
 */
function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator && indicator.parentNode) {
        indicator.parentNode.removeChild(indicator);
    } else {
        console.warn('Typing indicator element not found or already removed.');
    }
}

/**
 * Appends the assistant's message to the chat
 */
// Define DOMPurify options once
const DOMPurifyOptions = {
    ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'a', 'span'],
    ALLOWED_ATTRS: {
        'a': ['href', 'title', 'target', 'rel'],
        'span': ['class'],
        'code': ['class'],
        'pre': ['class']
    }
};

function appendAssistantMessage(message, isStreaming = false) {
    const chatBox = document.getElementById('chat-box');

    let messageDiv;
    if (isStreaming && chatBox.lastElementChild &&
        chatBox.lastElementChild.querySelector('.bg-gray-100')) {
        // Update existing streaming message
        messageDiv = chatBox.lastElementChild;
        const contentDiv = messageDiv.querySelector('.prose');
        if (contentDiv) {
            const renderedHtml = window.md.render(message);
            const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, DOMPurifyOptions);
            contentDiv.innerHTML = sanitizedHtml;
            window.Prism.highlightAllUnder(contentDiv);
        }
    } else {
        // Create new message
        messageDiv = document.createElement('div');
        messageDiv.className = 'flex w-full mt-2 space-x-2 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl';

        // Render and sanitize the message content
        const renderedHtml = window.md.render(message);
        const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, {
            ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'a'],
            ALLOWED_ATTRS: {
                'a': ['href', 'title', 'target', 'rel']
            }
        });

        messageDiv.innerHTML = `
            <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gray-300 dark:bg-gray-700"></div>
            <div class="relative flex-1">
                <!-- Action Buttons -->
                <div class="absolute right-2 top-2 flex items-center space-x-1 z-10">
                    <button
                        class="copy-button p-1.5 rounded-md bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200 shadow-sm"
                        title="Copy to clipboard"
                        data-raw-content="${message}"
                        aria-label="Copy message to clipboard">
                        <i class="fas fa-copy"></i>
                    </button>
                    <button
                        class="regenerate-button p-1.5 rounded-md bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200 shadow-sm"
                        title="Regenerate response" aria-label="Regenerate response">
                        <i class="fas fa-redo-alt"></i>
                    </button>
                </div>
                <!-- Message Content -->
                <div class="bg-gray-100 dark:bg-gray-800 p-3 pr-16 rounded-r-lg rounded-bl-lg">
                    <div class="prose dark:prose-invert prose-sm max-w-none overflow-x-auto">${sanitizedHtml}</div>
                </div>
                <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                    ${new Date().toLocaleTimeString()}
                </span>
            </div>
        `;
        chatBox.appendChild(messageDiv);

        // Apply syntax highlighting
        const contentDiv = messageDiv.querySelector('.prose');
        window.Prism.highlightAllUnder(contentDiv);
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
    console.log('DOMContentLoaded event fired');
    try {
        // Only initialize chat features if we're on a chat page
        if (!document.getElementById('chat-box')) {
            return;
        }

        // Wait for CHAT_CONFIG to be available
        let attempts = 0;
        while (!window.CHAT_CONFIG && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }

        // Verify all required dependencies
        const requiredDeps = {
            utils: window.utils,
            md: window.markdownit,
            DOMPurify: window.DOMPurify,
            Prism: window.Prism,
            FileUploadManager: window.FileUploadManager,
            TokenUsageManager: window.TokenUsageManager
        };

        const missingDeps = Object.entries(requiredDeps)
            .filter(([, dep]) => !dep)
            .map(([name]) => name);

        if (missingDeps.length > 0) {
            throw new Error(`Missing required dependencies: ${missingDeps.join(', ')}`);
        }

        await window.init();

        // Render initial assistant messages
        renderInitialAssistantMessages();
    } catch (error) {
        console.error('Error during initialization:', error);
        window.utils?.showFeedback?.(
            `Failed to initialize chat: ${error.message}. Please refresh the page.`,
            'error',
            { duration: 0 }
        );
    }
});
