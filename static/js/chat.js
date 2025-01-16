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

const windowExt = /** @type {Window & WindowExtensions} */ (window);

// Debounced handler for input
const handleMessageInput = (e) => {
    console.log('handleMessageInput called');
    adjustTextareaHeight(e.target);
};

// Throttled handler for send
const throttledSendMessage = windowExt.utils.throttle(() => {
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
function init() {
    console.log('Initializing chat interface');

    // Verify dependencies are loaded
    if (!windowExt.utils || !windowExt.md || !windowExt.DOMPurify || !windowExt.Prism) {
        console.error('Required dependencies not loaded:', {
            utils: !!windowExt.utils,
            md: !!windowExt.md,
            DOMPurify: !!windowExt.DOMPurify,
            Prism: !!windowExt.Prism
        });
        return;
    }

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

    // Attach input + keydown listeners
    messageInput.addEventListener('input', windowExt.utils.debounce(handleMessageInput, 100));
    messageInput.addEventListener('keydown', handleMessageKeydown);

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

                const response = await windowExt.utils.fetchWithCSRF(
                    `/chat/update_chat_title/${windowExt.CHAT_CONFIG.chatId}`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: newTitle.trim() })
                    }
                );

                if (response.success) {
                    const modelName = chatTitle.textContent.split('-')[1]?.trim() || '';
                    chatTitle.textContent = `${newTitle} ${modelName ? '- ' + modelName : ''}`;
                    windowExt.utils.showFeedback('Title updated successfully', 'success');
                } else {
                    throw new Error(response.error || 'Failed to update title');
                }
            } catch (error) {
                windowExt.utils.showFeedback(error.message, 'error');
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
            if (windowExt.fileUploadManager) {
                const { validFiles, errors } = windowExt.fileUploadManager.processFiles(files);
                if (errors.length > 0) {
                    errors.forEach(error =>
                        windowExt.utils.showFeedback(error.errors.join(', '), 'error')
                    );
                }
                if (validFiles.length > 0) {
                    windowExt.fileUploadManager.uploadedFiles.push(...validFiles);
                    windowExt.fileUploadManager.renderFileList();
                }
            }
        });
    }

    // Initialize FileUploadManager if needed
    const chatId = windowExt.CHAT_CONFIG.chatId;
    const userId = windowExt.CHAT_CONFIG.userId;
    const correctUploadBtn = window.innerWidth < 768 ? mobileUploadButton : uploadButton;

    if (!windowExt.fileUploadManager) {
        windowExt.fileUploadManager = new windowExt.FileUploadManager(chatId, userId, correctUploadBtn);
    }

    // Initialize TokenUsageManager if needed
    if (!windowExt.tokenUsageManager) {
        windowExt.tokenUsageManager = new window.TokenUsageManager(windowExt.CHAT_CONFIG);
        // Show token usage stats after new messages
        windowExt.tokenUsageManager.updateStats();
    }

    // Mobile menu is initialized in base.js

    // Fix chat input visibility (ensure chat box doesn't overlap the input area)
    const messageInputContainer = document.getElementById('message-input-container');
    if (chatBox && messageInputContainer) {
        chatBox.style.cssText = `
            padding-bottom: 120px !important;
            margin-bottom: 0 !important;
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
                const editUrl = windowExt.CHAT_CONFIG.editModelUrl + modelId;
                window.location.href = editUrl;
            } else {
                windowExt.utils.showFeedback('No model selected', 'error');
            }
        });
    }

    // Handle model changes
    if (modelSelect) {
        modelSelect.addEventListener('change', handleModelChange);
    }

    // Click events in chatBox (copy, regenerate, etc.)
    chatBox.addEventListener('click', handleMessageActions);

    // Set up delete chat buttons
    document.querySelectorAll('.delete-chat-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();

            const thisChatId = btn.dataset.chatId;
            if (!thisChatId) return;

            if (!confirm('Are you sure you want to delete this chat? This action cannot be undone.')) {
                return;
            }

            try {
                await windowExt.utils.withLoading(btn, async () => {
                    const response = await windowExt.utils.fetchWithCSRF(`/chat/delete_chat/${thisChatId}`, {
                        method: 'DELETE',
                    });

                    if (response.success) {
                        windowExt.utils.showFeedback('Chat deleted successfully', 'success');
                        // Remove the chat from the list or redirect if it's the current chat
                        if (thisChatId === windowExt.CHAT_CONFIG.chatId) {
                            window.location.href = '/chat/chat_interface';
                        } else {
                            btn.closest('.relative.group').remove();
                        }
                    } else {
                        throw new Error(response.error || 'Failed to delete chat');
                    }
                }, { text: '' }); // Show spinner only
            } catch (error) {
                windowExt.utils.showFeedback(error.message, 'error');
            }
        });
    });

    // Set up drag and drop
    setupDragAndDrop();

    // Cleanup on page unload
    window.addEventListener('beforeunload', cleanup);

    console.debug('Chat initialization completed successfully');
}

/**
 * Mobile menu initialization
 */
function initializeMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileMenu = document.getElementById('mobile-menu');
    const backdrop = document.getElementById('mobile-menu-backdrop');

    if (!mobileMenuToggle || !mobileMenu || !backdrop) {
        console.error('Mobile menu elements not found');
        return;
    }

    // Functions to open/close menu
    const closeMenu = () => {
        mobileMenu.classList.add('-translate-x-full');
        backdrop.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
        mobileMenuToggle.setAttribute('aria-expanded', 'false');
    };
    const openMenu = () => {
        mobileMenu.classList.remove('-translate-x-full');
        backdrop.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
        mobileMenuToggle.setAttribute('aria-expanded', 'true');
    };

    // Toggle menu
    mobileMenuToggle.addEventListener('click', () => {
        const isExpanded = mobileMenuToggle.getAttribute('aria-expanded') === 'true';
        if (isExpanded) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    // Close on backdrop
    backdrop.addEventListener('click', closeMenu);

    // Close when clicking a chat link (on mobile)
    const chatLinks = mobileMenu.querySelectorAll('a[href*="chat_interface"]');
    chatLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth < 768) {
                closeMenu();
            }
        });
    });

    // Close if resized to desktop
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 768) {
            mobileMenu.classList.remove('-translate-x-full');
            backdrop.classList.add('hidden');
            document.body.classList.remove('overflow-hidden');
        } else {
            mobileMenu.classList.add('-translate-x-full');
        }
    });

    // Escape key closes menu
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !mobileMenu.classList.contains('-translate-x-full')) {
            closeMenu();
        }
    });
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
                windowExt.utils.showFeedback('No files dropped', 'error');
                return;
            }
            const files = Array.from(e.dataTransfer.files);
            if (files.length === 0) {
                windowExt.utils.showFeedback('No files dropped', 'error');
                return;
            }
            if (windowExt.fileUploadManager) {
                const { validFiles, errors } = windowExt.fileUploadManager.processFiles(files);
                if (errors.length > 0) {
                    errors.forEach(error => windowExt.utils.showFeedback(error.errors.join(', '), 'error'));
                }
                if (validFiles.length > 0) {
                    windowExt.fileUploadManager.uploadedFiles.push(...validFiles);
                    windowExt.fileUploadManager.renderFileList();
                }
            }
        } catch (error) {
            console.error('Error handling file drop:', error);
            windowExt.utils.showFeedback('Failed to process dropped files', 'error');
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
        const sendButton = document.getElementById('send-button');
        if (messageInput) {
            // Remove exact references (not anonymous)
            messageInput.removeEventListener('input', windowExt.utils.debounce(handleMessageInput, 100));
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

/**
 * Creates a new chat
 */
async function createNewChat() {
    try {
        const newChatBtn = document.getElementById('new-chat-btn');
        if (newChatBtn) {
            newChatBtn.disabled = true;
        }

        const response = await windowExt.utils.fetchWithCSRF('/chat/new_chat', {
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
        windowExt.utils.showFeedback(error.message || 'Failed to create new chat', 'error');
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
    console.log('sendMessage function called');
    // Update token usage after sending
    if (windowExt.tokenUsageManager) {
        windowExt.tokenUsageManager.updateStats();
    }

    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    if (!messageInput || !sendButton) return;

    if (messageInput.value.trim() === '' && windowExt.fileUploadManager.uploadedFiles.length === 0) {
        windowExt.utils.showFeedback('Please enter a message or upload files.', 'error');
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
    windowExt.fileUploadManager.uploadedFiles.forEach(file => {
        formData.append('files[]', file);
    });

    // Check for streaming
    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect?.value;
    const model = windowExt.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
    const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

    try {
        await windowExt.utils.withLoading(sendButton, async () => {
            // Add CSRF token to formData
            formData.append('csrf_token', windowExt.CHAT_CONFIG.csrfToken);

            let response;
            if (useStreaming) {
                response = await fetch('/chat/', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Chat-ID': windowExt.CHAT_CONFIG.chatId,
                        'X-CSRFToken': windowExt.utils.getCSRFToken(),
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
                            appendAssistantMessage(accumulatedResponse, true);
                        }
                    }
                }

                // Final update with complete response
                appendAssistantMessage(accumulatedResponse, false);
                response = { response: accumulatedResponse };
            } else {
                response = await windowExt.utils.fetchWithCSRF('/chat/', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Chat-ID': windowExt.CHAT_CONFIG.chatId,
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
            }

            if (!response) {
                throw new Error('No response received from server');
            }
            if (response.error) {
                throw new Error(response.error);
            }

            // Clear input and files
            messageInput.value = '';
            windowExt.fileUploadManager.uploadedFiles = [];
            windowExt.fileUploadManager.renderFileList();

            // Update token usage stats after sending message
            if (windowExt.tokenUsageManager) {
                windowExt.tokenUsageManager.updateStats();
            }

            // Handle streaming vs. non-streaming
            if (response.response) {
                // For non-streaming, append final response
                if (!useStreaming) {
                    appendAssistantMessage(response.response);
                }
            } else if (!response.success) {
                throw new Error('Failed to get response from model');
            }

            // Show success feedback only for non-streaming
            if (!useStreaming) {
                windowExt.utils.showFeedback('Message sent successfully', 'success');
            }

            // Update token usage stats after assistant response
            if (windowExt.tokenUsageManager) {
                windowExt.tokenUsageManager.updateStats();
            }
        }, { text: 'Sending...' });
    } catch (error) {
        windowExt.utils.showFeedback(error.message, 'error');
    }
}

/**
 * Adjusts the textarea height dynamically
 */
function adjustTextareaHeight(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
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
        await windowExt.utils.withLoading(modelSelect, async () => {
            const response = await windowExt.utils.fetchWithCSRF('/chat/update_model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_id: modelId,
                    chat_id: windowExt.CHAT_CONFIG.chatId
                })
            });

            if (response.success) {
                const selectedOption = modelSelect.options[modelSelect.selectedIndex];
                if (selectedOption) {
                    const modelName = selectedOption.textContent;
                    const chatTitle = document.getElementById('chat-title');
                    if (chatTitle) {
                        const currentTitle = chatTitle.textContent.split('-')[0].trim();
                        chatTitle.textContent = `${currentTitle} - ${modelName}`;
                    }
                }
                modelSelect.dataset.originalValue = modelId;
                windowExt.utils.showFeedback('Model updated successfully', 'success');
            } else {
                throw new Error(response.error || 'Failed to update model');
            }
        });
    } catch (error) {
        windowExt.utils.showFeedback(error.message, 'error');
        modelSelect.value = originalValue; // Revert selection
    }
}

/**
 * Handle message actions like Copy and Regenerate
 */
async function handleMessageActions(event) {
    const target = event.target.closest('button');
    if (!target) return;

    try {
        if (target.classList.contains('copy-button')) {
            const rawContent = target.dataset.rawContent;
            const content = rawContent || target.closest('.max-w-3xl').querySelector('.prose').textContent;
            await navigator.clipboard.writeText(content);
            windowExt.utils.showFeedback('Copied to clipboard!', 'success');
        } else if (target.classList.contains('regenerate-button')) {
            await regenerateResponse(target);
        }
    } catch (error) {
        console.error('Error handling message action:', error);
        windowExt.utils.showFeedback('Failed to perform action', 'error');
    }
}

/**
 * Regenerate the assistant's last response
 */
async function regenerateResponse(button) {
    // Update token usage
    if (windowExt.tokenUsageManager) {
        windowExt.tokenUsageManager.updateStats();
    }
    button.disabled = true;

    try {
        const chatId = windowExt.CHAT_CONFIG.chatId;
        if (!chatId) {
            windowExt.utils.showFeedback('Chat ID not found', 'error');
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
            windowExt.utils.showFeedback('No message found to regenerate', 'error');
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
        const model = windowExt.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
        const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

        let responseData;
        if (useStreaming) {
            formData.append('csrf_token', windowExt.CHAT_CONFIG.csrfToken);
            const response = await fetch('/chat/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': windowExt.CHAT_CONFIG.chatId,
                    'X-CSRFToken': windowExt.utils.getCSRFToken(),
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
                        appendAssistantMessage(accumulatedResponse, true);
                    }
                }
            }

            // Final update
            appendAssistantMessage(accumulatedResponse, false);
            responseData = { response: accumulatedResponse };
        } else {
            responseData = await windowExt.utils.fetchWithCSRF('/chat/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Chat-ID': windowExt.CHAT_CONFIG.chatId,
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
        windowExt.utils.showFeedback(error.message, 'error');
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
function appendAssistantMessage(message, isStreaming = false) {
    if (!message || typeof message !== 'string') {
        console.error('Invalid message content.');
        return;
    }

    let messageDiv;
    let contentDiv;

    if (isStreaming && document.getElementById('chat-box').lastElementChild) {
        messageDiv = document.getElementById('chat-box').lastElementChild;
        contentDiv = messageDiv.querySelector('.prose');
        if (!contentDiv) {
            console.error('Content div not found in existing message');
            return;
        }
    } else {
        messageDiv = document.createElement('div');
        messageDiv.className = 'flex w-full mt-2 space-x-2 max-w-[90%] sm:max-w-xl md:max-w-2xl lg:max-w-3xl';
        messageDiv.setAttribute('role', 'listitem');
        messageDiv.innerHTML = `
            <div class="flex-shrink-0 h-8 w-8 rounded-full bg-gray-300 dark:bg-gray-700" role="img" aria-label="Assistant avatar"></div>
            <div class="relative flex-1">
                <!-- Action Buttons -->
                <div class="absolute right-2 top-2 flex items-center space-x-1 z-10">
                    <button class="copy-button p-1.5 rounded-md bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200 shadow-sm"
                            title="Copy to clipboard"
                            data-raw-content="${message}"
                            aria-label="Copy message to clipboard">
                        <i class="fas fa-copy"></i>
                    </button>
                    <button class="regenerate-button p-1.5 rounded-md bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200 shadow-sm"
                            title="Regenerate response"
                            aria-label="Regenerate response">
                        <i class="fas fa-redo-alt"></i>
                    </button>
                </div>

                <!-- Message Content -->
                <div class="bg-gray-100 dark:bg-gray-800 p-3 pr-16 rounded-r-lg rounded-bl-lg">
                    <div class="prose dark:prose-invert prose-sm max-w-none overflow-x-auto"></div>
                </div>
                <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                    ${new Date().toLocaleTimeString()}
                </span>
            </div>
        `;
        contentDiv = messageDiv.querySelector('.prose');
    }

    try {
        const renderedHtml = windowExt.md.render(message);
        const sanitizedHtml = windowExt.DOMPurify.sanitize(renderedHtml, {
            ALLOWED_TAGS: [
                'b', 'i', 'em', 'strong', 'a', 'p', 'blockquote', 'code', 'pre',
                'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br',
                'hr', 'span', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
            ],
            ALLOWED_ATTR: ['href', 'src', 'alt', 'class', 'aria-label', 'role']
        });

        contentDiv.innerHTML = sanitizedHtml;
        windowExt.Prism.highlightAllUnder(contentDiv);

        // Make code blocks accessible
        contentDiv.querySelectorAll('pre').forEach(pre => {
            pre.setAttribute('role', 'region');
            pre.setAttribute('aria-label', 'Code block');
            pre.tabIndex = 0;
        });

        // Only append if we haven't appended yet (streaming vs final)
        if (!isStreaming || !document.getElementById('chat-box').lastElementChild) {
            document.getElementById('chat-box').appendChild(messageDiv);
        }

        document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;
    } catch (error) {
        console.error('Error rendering markdown:', error);
        contentDiv.innerHTML = `<pre>${windowExt.DOMPurify.sanitize(message)}</pre>`;
    }
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

// Initialize markdown-it once
windowExt.md = windowExt.markdownit({
    html: true,
    linkify: true,
    typographer: true
});

/**
 * Auto-init once the DOM is ready
 */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('DOMContentLoaded event fired');
        if (windowExt.CHAT_CONFIG) {
            init();
        } else {
            console.error('Chat configuration not found');
        }
    });
} else {
    // DOM is already ready
    console.log('DOM already loaded');
    if (windowExt.CHAT_CONFIG) {
        init();
    } else {
        console.error('Chat configuration not found');
    }
}
