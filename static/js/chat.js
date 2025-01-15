/* static/js/chat.js */

// Ensure dependencies are available through window
const TokenUsageManager = window.TokenUsageManager;
const FileUploadManager = window.FileUploadManager;
const { fetchWithCSRF, showFeedback, debounce, throttle } = window.utils;

// Debounced handler for input
const handleMessageInput = (e) => {
    adjustTextareaHeight(e.target);
};

// Throttled handler for send
const throttledSendMessage = throttle(() => {
    sendMessage();
}, 1000);

// Keydown handler
const handleMessageKeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
};

function init() {
        // Verify dependencies
        if (!window.utils || !window.md || !window.DOMPurify || !window.Prism || !window.FileUploadManager) {
            console.error('Required dependencies not loaded');
            return;
        }

        // Initialize FileUploadManager with chat ID and user ID
        const chatId = window.CHAT_CONFIG.chatId;
        const userId = window.CHAT_CONFIG.userId;
        const uploadButton = window.innerWidth < 768 ? document.getElementById('mobile-upload-button') : document.getElementById('upload-button');
        
        if (!window.fileUploadManager) {
            window.fileUploadManager = new window.FileUploadManager(chatId, userId, uploadButton);
        }

        // Initialize TokenUsageManager
        if (!window.tokenUsageManager) {
            window.tokenUsageManager = new TokenUsageManager(window.CHAT_CONFIG);
            // Show token usage stats after new messages
            window.tokenUsageManager.updateStats();
        }

        // Initialize mobile menu
        initializeMobileMenu();

        // Cache and verify DOM elements
        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');
        const chatBox = document.getElementById('chat-box');
        const messageInputContainer = document.getElementById('message-input-container');
        const modelSelect = document.getElementById('model-select');
        const newChatBtn = document.getElementById('new-chat-btn');
        const editTitleBtn = document.getElementById('edit-title-btn');
        const editModelBtn = document.getElementById('edit-model-btn');
        const deleteButtons = document.querySelectorAll('.delete-chat-btn');

        if (!messageInput || !sendButton || !chatBox) {
            console.error('Critical UI elements are missing. Please reload the page.');
            return;
        }

        // Fix chat input visibility
        if (chatBox && messageInputContainer) {
            // Ensure chat box doesn't overlap with input
            chatBox.style.cssText = `
                padding-bottom: 120px !important;
                margin-bottom: 0 !important;
            `;
            
            // Make sure input container is visible and properly styled
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

            // Add dark mode styles
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

        // *** CHANGED ***: Use named functions for addEventListener.
        messageInput.addEventListener('input', debounce(handleMessageInput, 100));
        messageInput.addEventListener('keydown', handleMessageKeydown);
        sendButton.addEventListener('click', throttledSendMessage);

        if (newChatBtn) {
            newChatBtn.addEventListener('click', createNewChat);
        }

        if (editTitleBtn) {
            editTitleBtn.addEventListener('click', async () => {
                try {
                    const chatTitle = document.getElementById('chat-title');
                    const currentTitle = chatTitle?.textContent?.split('-')[0].trim() || 'New Chat';
                    const newTitle = prompt('Enter new chat title:', currentTitle);
        
                    if (!newTitle || newTitle === currentTitle) return;

                    const response = await window.utils.fetchWithCSRF(`/chat/update_chat_title/${chatId}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ title: newTitle.trim() })
                    });

                    if (response.success) {
                        const modelName = chatTitle.textContent.split('-')[1]?.trim() || '';
                        chatTitle.textContent = `${newTitle} ${modelName ? '- ' + modelName : ''}`;
                        window.utils.showFeedback('Title updated successfully', 'success');
                    } else {
                        throw new Error(response.error || 'Failed to update title');
                    }
                } catch (error) {
                    window.utils.showFeedback(error.message, 'error');
                }
            });
        }

        if (editModelBtn) {
            editModelBtn.addEventListener('click', () => {
                const modelId = modelSelect?.value;
                if (modelId) {
                    window.location.href = `${window.CHAT_CONFIG.editModelUrl}${modelId}`;
                } else {
                    window.utils.showFeedback('No model selected', 'error');
                }
            });
        }

        if (modelSelect) {
            modelSelect.addEventListener('change', handleModelChange);
        }

        if (chatBox) {
            chatBox.addEventListener('click', handleMessageActions);
        }

        // Set up delete chat buttons
        deleteButtons.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const chatId = btn.dataset.chatId;
                if (!chatId) return;

                if (!confirm('Are you sure you want to delete this chat? This action cannot be undone.')) {
                    return;
                }

                try {
                    await window.utils.withLoading(btn, async () => {
                        const response = await window.utils.fetchWithCSRF(`/chat/delete_chat/${chatId}`, {
                            method: 'DELETE',
                        });

                        if (response.success) {
                            window.utils.showFeedback('Chat deleted successfully', 'success');
                            // Remove the chat from the list or redirect if it's the current chat
                            if (chatId === window.CHAT_CONFIG.chatId) {
                                window.location.href = '/chat/chat_interface';
                            } else {
                                btn.closest('.relative.group').remove();
                            }
                        } else {
                            throw new Error(response.error || 'Failed to delete chat');
                        }
                    }, { text: '' }); // Empty text to just show spinner
                } catch (error) {
                    window.utils.showFeedback(error.message, 'error');
                }
            });
        });

        // Set up drag and drop
        setupDragAndDrop();

        // Cleanup on page unload
        window.addEventListener('beforeunload', cleanup);

        console.debug('Chat initialization completed successfully');
    }

    function initializeMobileMenu() {
        const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        const mobileMenu = document.getElementById('mobile-menu');
        const backdrop = document.getElementById('mobile-menu-backdrop');

        if (!mobileMenuToggle || !mobileMenu || !backdrop) {
            console.error('Mobile menu elements not found');
            return;
        }

        // Function to close menu
        const closeMenu = () => {
            mobileMenu.classList.add('-translate-x-full');
            backdrop.classList.add('hidden');
            document.body.classList.remove('overflow-hidden');
            mobileMenuToggle.setAttribute('aria-expanded', 'false');
        };

        // Function to open menu
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

        // Close menu when clicking backdrop
        backdrop.addEventListener('click', closeMenu);

        // Close menu when clicking a chat link on mobile
        const chatLinks = mobileMenu.querySelectorAll('a[href*="chat_interface"]');
        chatLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 768) { // Only on mobile
                    closeMenu();
                }
            });
        });

        // Close menu on window resize if switching to desktop
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768) {
                mobileMenu.classList.remove('-translate-x-full');
                backdrop.classList.add('hidden');
                document.body.classList.remove('overflow-hidden');
            } else {
                mobileMenu.classList.add('-translate-x-full');
            }
        });

        // Handle escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !mobileMenu.classList.contains('-translate-x-full')) {
                closeMenu();
            }
        });
    }

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
                    showFeedback('No files dropped', 'error');
                    return;
                }
                const files = Array.from(e.dataTransfer.files);
                if (files.length === 0) {
                    showFeedback('No files dropped', 'error');
                    return;
                }
                const { validFiles, errors } = window.fileUploadManager.processFiles(files);
                if (errors.length > 0) {
                    errors.forEach(error => showFeedback(error.errors.join(', '), 'error'));
                }
                if (validFiles.length > 0) {
                    window.fileUploadManager.uploadedFiles.push(...validFiles);
                    window.fileUploadManager.renderFileList();
                }
            } catch (error) {
                console.error('Error handling file drop:', error);
                showFeedback('Failed to process dropped files', 'error');
            } finally {
                dropZone.classList.add('hidden');
            }
        });
    }

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function cleanup() {
        try {
            // Remove event listeners
            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            if (messageInput) {
                // *** CHANGED ***: Remove the matching references, not anonymous.
                messageInput.removeEventListener('input', handleMessageInput);
                messageInput.removeEventListener('keydown', handleMessageKeydown);
            }
            if (sendButton) {
                // *** CHANGED ***: Remove the throttled function reference.
                sendButton.removeEventListener('click', throttledSendMessage);
                // Removed removeEventListener for 'touchend' because it was never added.
            }
            console.debug('Chat cleanup completed successfully');
        } catch (error) {
            console.error('Error during cleanup:', error);
        }
    }

    async function createNewChat() {
        try {
            const newChatBtn = document.getElementById('new-chat-btn');
            if (newChatBtn) {
                newChatBtn.disabled = true;
            }

            const response = await fetchWithCSRF('/chat/new_chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (response.success && response.chat_id) {
                window.location.href = `/chat/chat_interface?chat_id=${response.chat_id}`;
            } else {
                throw new Error(response.error || 'Failed to create new chat');
            }
        } catch (error) {
            console.error('Error creating new chat:', error);
            showFeedback(error.message || 'Failed to create new chat', 'error');
        } finally {
            const newChatBtn = document.getElementById('new-chat-btn');
            if (newChatBtn) {
                newChatBtn.disabled = false;
            }
        }
    }

    async function sendMessage() {
        // Update token usage after sending message
        if (window.tokenUsageManager) {
            window.tokenUsageManager.updateStats();
        }
        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');

        if (!messageInput || !sendButton) return;

        if (messageInput.value.trim() === '' && window.fileUploadManager.uploadedFiles.length === 0) {
            showFeedback('Please enter a message or upload files.', 'error');
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

        // *** CHANGED ***: Removed second appendUserMessage() call here — it was duplicated.

        // Add files if present
        window.fileUploadManager.uploadedFiles.forEach(file => {
            formData.append('files[]', file);
        });

        // Get model info for streaming
        const modelSelect = document.getElementById('model-select');
        const modelId = modelSelect?.value;
        const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
        const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

        try {
            await window.utils.withLoading(sendButton, async () => {
                // Add CSRF token to formData
                formData.append('csrf_token', window.CHAT_CONFIG.csrfToken);
                
                let response;
                if (useStreaming) {
                    response = await fetch('/chat/', {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-Chat-ID': window.CHAT_CONFIG.chatId,
                            'X-CSRFToken': window.utils.getCSRFToken(),
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
                    response = await fetchWithCSRF('/chat/', {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-Chat-ID': window.CHAT_CONFIG.chatId,
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

                // Clear input and files regardless of response type
                messageInput.value = '';
                window.fileUploadManager.uploadedFiles = [];
                window.fileUploadManager.renderFileList();

                // Handle both streaming and non-streaming responses
                if (response.response) {
                    appendAssistantMessage(response.response);
                } else if (!response.success) {
                    throw new Error('Failed to get response from model');
                }

                // Show success feedback only for non-streaming responses
                if (!useStreaming) {
                    showFeedback('Message sent successfully', 'success');
                }
            }, { text: 'Sending...' });
        } catch (error) {
            showFeedback(error.message, 'error');
        }
    }

    function adjustTextareaHeight(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = `${textarea.scrollHeight}px`;
    }

    async function handleModelChange() {
        const modelSelect = document.getElementById('model-select');
        if (!modelSelect) return;

        const modelId = modelSelect.value;
        const originalValue = modelSelect.dataset.originalValue;

        try {
            await window.utils.withLoading(modelSelect, async () => {
                const response = await fetchWithCSRF('/chat/update_model', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        model_id: modelId,
                        chat_id: window.CHAT_CONFIG.chatId
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
                    } else {
                        console.error('Selected option is undefined');
                    }
                    modelSelect.dataset.originalValue = modelId;
                    showFeedback('Model updated successfully', 'success');
                } else {
                    throw new Error(response.error || 'Failed to update model');
                }
            });
        } catch (error) {
            showFeedback(error.message, 'error');
            modelSelect.value = originalValue; // Restore original selection
        }
    }

    async function handleMessageActions(event) {
        const target = event.target.closest('button');
        if (!target) return;

        try {
            if (target.classList.contains('copy-button')) {
                const rawContent = target.dataset.rawContent;
                const content = rawContent || target.closest('.max-w-3xl').querySelector('.prose').textContent;
                await navigator.clipboard.writeText(content);
                showFeedback('Copied to clipboard!', 'success');
            } else if (target.classList.contains('regenerate-button')) {
                await regenerateResponse(target);
            }
        } catch (error) {
            console.error('Error handling message action:', error);
            showFeedback('Failed to perform action', 'error');
        }
    }

    async function regenerateResponse(button) {
        // Update token usage after regenerating response
        if (window.tokenUsageManager) {
            window.tokenUsageManager.updateStats();
        }
        button.disabled = true;
        try {
            const chatId = new URLSearchParams(window.location.search).get('chat_id');
            if (!chatId) {
                showFeedback('Chat ID not found', 'error');
                return;
            }

            const messages = Array.from(document.getElementById('chat-box').children);
            let lastUserMessage = null;
            for (let i = messages.length - 1; i >= 0; i--) {
                const messageDiv = messages[i];
                if (messageDiv.querySelector('.bg-blue-600')) {
                    lastUserMessage = messageDiv.querySelector('.text-sm').textContent;
                    break;
                }
            }

            if (!lastUserMessage) {
                showFeedback('No message found to regenerate', 'error');
                return;
            }

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

            // Get model info for streaming
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
                        'X-CSRFToken': window.utils.getCSRFToken(),
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
                responseData = { response: accumulatedResponse };
            } else {
                responseData = await fetchWithCSRF('/chat/', {
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
            showFeedback(error.message, 'error');
        } finally {
            button.disabled = false;
            removeTypingIndicator();
        }
    }

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
                    <!-- Action Buttons - Positioned absolutely to the right -->
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

                    <!-- Message Content - With padding to prevent overlap -->
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
            const renderedHtml = window.md.render(message);
            const sanitizedHtml = window.DOMPurify.sanitize(renderedHtml, {
                ALLOWED_TAGS: [
                    'b', 'i', 'em', 'strong', 'a', 'p', 'blockquote', 'code', 'pre',
                    'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br',
                    'hr', 'span', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
                ],
                ALLOWED_ATTR: ['href', 'src', 'alt', 'class', 'aria-label', 'role']
            });

            contentDiv.innerHTML = sanitizedHtml;
            window.Prism.highlightAllUnder(contentDiv);

            // Make code blocks accessible
            contentDiv.querySelectorAll('pre').forEach(pre => {
                pre.setAttribute('role', 'region');
                pre.setAttribute('aria-label', 'Code block');
                pre.tabIndex = 0;
            });

            // Only append the message div if it's not already in the chat box
            if (!isStreaming || !document.getElementById('chat-box').lastElementChild) {
                document.getElementById('chat-box').appendChild(messageDiv);
            }

            document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;
        } catch (error) {
            console.error('Error rendering markdown:', error);
            contentDiv.innerHTML = `<pre>${window.DOMPurify.sanitize(message)}</pre>`;
        }
    }

    // Function to append user message to chat box
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
                    <p class="text-[15px] leading-normal break-words overflow-x-auto">${message}</p>
                </div>
                <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
                    ${new Date().toLocaleTimeString()}
                </span>
            </div>
        `;
        document.getElementById('chat-box').appendChild(messageDiv);
        document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;
    }

// Initialize chat interface
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
