(function () {
    // Destructure required functions from utils
    const { getCSRFToken, showFeedback, debounce, fetchWithCSRF } = utils;

    // Function to edit chat title
    async function editChatTitle(chatId) {
        const newTitle = prompt('Enter new chat title:');
        if (newTitle) {
            try {
                const response = await makeFetchRequest(`/update_chat_title/${chatId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({ title: newTitle })
                });
                if (response.success) {
                    document.getElementById('chat-title').textContent = newTitle;
                    showFeedback('Chat title updated successfully', 'success');
                } else {
                    throw new Error(response.error || 'Unknown error');
                }
            } catch (error) {
                console.error('Error updating chat title:', error);
                showFeedback('Failed to update chat title', 'error');
            }
        }
    }

    // Function to delete a chat
    async function deleteChat(chatId) {
        if (confirm('Are you sure you want to delete this chat?')) {
            try {
                const response = await makeFetchRequest(`/delete_chat/${chatId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                if (response.success) {
                    location.reload();
                } else {
                    throw new Error(response.error || 'Unknown error');
                }
            } catch (error) {
                console.error('Error deleting chat:', error);
                showFeedback('Failed to delete chat', 'error');
            }
        }
    }


    // Expose functions to the global scope
    window.editChatTitle = editChatTitle;
    window.deleteChat = deleteChat;

    // Global variables and state
    let uploadedFiles = [];
    const MAX_FILES = 5;
    const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
    const MAX_MESSAGE_LENGTH = 1000;
    const FEEDBACK_TIMEOUT = 3000;
    const ALLOWED_FILE_TYPES = [
        'text/plain',
        'application/pdf',
        'text/x-python',
        'application/javascript',
        'text/markdown',
        'image/jpeg',
        'image/png',
        'text/csv'
    ];

    // DOM Elements Cache
    let messageInput, sendButton, chatBox, fileInput, uploadButton,
        uploadedFilesDiv, modelSelect, newChatBtn, dropZone;

    // DOM Content Loaded
    document.addEventListener('DOMContentLoaded', function () {
        console.debug('DOMContentLoaded event triggered. Initializing elements.');
        
        // Cache DOM elements
        messageInput = document.getElementById('message-input');
        sendButton = document.getElementById('send-button');
        chatBox = document.getElementById('chat-box');
        fileInput = document.getElementById('file-input');
        uploadButton = document.getElementById('upload-button');
        uploadedFilesDiv = document.getElementById('uploaded-files');
        modelSelect = document.getElementById('model-select');
        newChatBtn = document.getElementById('new-chat-btn');
        dropZone = document.getElementById('drop-zone');

        // Verify critical elements exist
        if (!messageInput || !sendButton || !chatBox) {
            console.error('Critical chat elements not found');
            showFeedback('Chat interface not loaded properly', 'error');
            return;
        }

        // Cache DOM elements
        messageInput = document.getElementById('message-input');
        sendButton = document.getElementById('send-button');
        chatBox = document.getElementById('chat-box');
        fileInput = document.getElementById('file-input');
        uploadButton = document.getElementById('upload-button');
        uploadedFilesDiv = document.getElementById('uploaded-files');
        modelSelect = document.getElementById('model-select');
        newChatBtn = document.getElementById('new-chat-btn');
        dropZone = document.getElementById('drop-zone');

        console.log('Message input:', messageInput);
        console.log('Send button:', sendButton);
        console.log('Chat box:', chatBox);

        // Verify critical elements exist
        if (!messageInput || !sendButton || !chatBox) {
            console.error('Critical chat elements not found');
            showFeedback('Chat interface not loaded properly', 'error');
            return;
        }

        console.debug('Elements initialized:', { messageInput, sendButton, chatBox });

        // Initialize event listeners
        initializeEventListeners();

        // Set up file drag and drop
        setupDragAndDrop();

        // Initialize message input
        adjustTextareaHeight(messageInput);

        // Test send button functionality
        console.log('Testing send button click handler...');
        sendButton.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Send button clicked'); // Debugging statement
            sendMessage();
        });
    });

    function initializeEventListeners() {
        console.debug('Initializing event listeners.');
        
        // Verify critical elements exist
        if (!messageInput || !sendButton || !chatBox) {
            console.error('Critical chat elements not found');
            return;
        }

        // Message input handlers
        messageInput.addEventListener('input', debounce(function () {
            adjustTextareaHeight(this);
        }, 300));

        messageInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // Send button handler
        console.debug('Initializing sendButton:', sendButton);
        sendButton.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Send button clicked');
            sendMessage();
        });

        // File upload handlers
        if (fileInput && uploadButton) {
            uploadButton.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', handleFileSelect);
        }

        // New chat button handler
        if (newChatBtn) {
            newChatBtn.addEventListener('click', createNewChat);
        }

        // Model selection handler
        if (modelSelect) {
            modelSelect.addEventListener('change', handleModelChange);
        }

        // Chat box message action handlers
        if (chatBox) {
            chatBox.addEventListener('click', handleMessageActions);
        }
    }

    async function sendMessage() {
        console.log('sendMessage function called'); // Debugging statement
        console.debug('Send button clicked. Preparing to send message:', messageInput.value.trim());
        console.debug('Uploaded files:', uploadedFiles);

        // Validate input
        if (!messageInput.value.trim() && uploadedFiles.length === 0) {
            showFeedback('Please enter a message or upload files.', 'error');
            return;
        }

        // Check if chatBox exists
        if (!chatBox) {
            console.error('Chat box element not found');
            showFeedback('Chat interface not loaded properly', 'error');
            return;
        }

        if (messageInput.value.length > MAX_MESSAGE_LENGTH) {
            showFeedback(`Message too long. Maximum length is ${MAX_MESSAGE_LENGTH} characters.`, 'error');
            return;
        }

        // Disable input controls
        messageInput.disabled = true;
        sendButton.disabled = true;
        sendButton.innerHTML = '<span class="animate-spin">↻</span>';

        try {
            // Create form data
            const formData = new FormData();
            formData.append('message', messageInput.value.trim());
            uploadedFiles.forEach(file => formData.append('files[]', file));

            // Append user message immediately
            appendUserMessage(messageInput.value.trim());
            messageInput.value = '';
            adjustTextareaHeight(messageInput);

            // Show typing indicator
            showTypingIndicator();

            console.debug('Making POST request to /chat with formData:', formData);
            console.log('CSRF Token:', getCSRFToken());

            console.log('Preparing to send request to /chat'); // Debugging statement
            const data = await fetchWithCSRF('/chat', {
                method: 'POST',
                body: formData,
            });

            console.log('Response from server:', data);

            if (data.response) {
                appendAssistantMessage(data.response);
                uploadedFiles = [];
                renderFileList();
            }

            if (data.excluded_files) {
                data.excluded_files.forEach(file => {
                    showFeedback(`Failed to upload ${file.filename}: ${file.error}`, 'error');
                });
            }
        } catch (error) {
            console.error('Error sending message:', error);
            console.error('Error details:', error.stack);
            showFeedback(`Error: ${error.message}`, 'error');
        } finally {
            messageInput.disabled = false;
            sendButton.disabled = false;
            sendButton.innerHTML = 'Send';
            removeTypingIndicator();
            messageInput.focus();
        }
    }

    function appendUserMessage(message) {
        console.debug('Appending user message:', message);
        const messageDiv = document.createElement('div');
        messageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end';
        messageDiv.innerHTML = `
            <div>
                <div class="relative bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                    <p class="text-sm">${escapeHtml(message)}</p>
                </div>
                <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
            </div>
        `;
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendAssistantMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'flex w-full mt-2 space-x-3 max-w-lg';
        messageDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700"></div>
            <div class="relative max-w-lg">
                <div class="bg-gray-100 dark:bg-gray-800 p-3 rounded-r-lg rounded-bl-lg">
                    <div class="prose dark:prose-invert prose-sm max-w-none"></div>
                </div>
                <span class="text-xs text-gray-500 dark:text-gray-400 leading-none">
                    ${new Date().toLocaleTimeString()}
                </span>
            </div>
        `;

        const contentDiv = messageDiv.querySelector('.prose');
        if (contentDiv) {
            const renderedHtml = md.render(message);
            const sanitizedHtml = DOMPurify.sanitize(renderedHtml, {
                ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a'],
                ALLOWED_ATTR: ['href']
            });
            contentDiv.innerHTML = sanitizedHtml;
            Prism.highlightAllUnder(contentDiv);
        }

        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function handleFileSelect(event) {
        const files = Array.from(event.target.files);
        processFiles(files);
    }

    function processFiles(files) {
        const validFiles = [];
        const errors = [];

        files.forEach(file => {
            if (!ALLOWED_FILE_TYPES.includes(file.type)) {
                errors.push(`${file.name}: Unsupported file type`);
            } else if (file.size > MAX_FILE_SIZE) {
                errors.push(`${file.name}: File too large (max ${MAX_FILE_SIZE / 1024 / 1024}MB)`);
            } else if (uploadedFiles.length + validFiles.length >= MAX_FILES) {
                errors.push(`${file.name}: Maximum number of files reached`);
            } else {
                validFiles.push(file);
            }
        });

        if (errors.length > 0) {
            showFeedback(errors.join('\n'), 'error');
        }

        if (validFiles.length > 0) {
            uploadedFiles = uploadedFiles.concat(validFiles);
            renderFileList();
            showFeedback(`${validFiles.length} file(s) ready to upload`, 'success');
        }
    }

    function renderFileList() {
        if (!uploadedFilesDiv) return;

        const fileList = document.getElementById('file-list');
        if (!fileList) return;

        fileList.innerHTML = '';
        uploadedFiles.forEach((file, index) => {
            const fileDiv = document.createElement('div');
            fileDiv.className = 'flex items-center justify-between bg-gray-100 dark:bg-gray-800 p-2 rounded mb-2';
            fileDiv.innerHTML = `
                <span class="text-sm truncate">${escapeHtml(file.name)}</span>
                <button class="text-red-500 hover:text-red-700" data-index="${index}">
                    Remove
                </button>
            `;
            fileList.appendChild(fileDiv);
        });

        uploadedFilesDiv.classList.toggle('hidden', uploadedFiles.length === 0);
    }

    function removeFile(index) {
        uploadedFiles.splice(index, 1);
        renderFileList();
    }

    function adjustTextareaHeight(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = `${textarea.scrollHeight}px`;
    }

    function showTypingIndicator() {
        let indicator = document.getElementById('typing-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'typing-indicator';
            indicator.className = 'flex items-center space-x-2 p-3 bg-gray-100 dark:bg-gray-800 rounded-lg mb-2';
            indicator.innerHTML = `
                <div class="typing-animation">
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <div class="dot"></div>
                </div>
                <span class="text-sm text-gray-500">Assistant is typing...</span>
            `;
            chatBox.appendChild(indicator);
        }
        indicator.style.display = 'flex';
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    }

    function showFeedback(message, type = 'info') {
        const feedbackDiv = document.getElementById('feedback-message') || createFeedbackElement();
        feedbackDiv.className = `fixed top-4 left-1/2 transform -translate-x-1/2 p-4 rounded-lg shadow-lg z-50 ${
            type === 'error' ? 'bg-red-500' : type === 'success' ? 'bg-green-500' : 'bg-blue-500'
        } text-white`;
        feedbackDiv.textContent = message;
        feedbackDiv.classList.remove('hidden');

        setTimeout(() => {
            feedbackDiv.classList.add('hidden');
        }, FEEDBACK_TIMEOUT);
    }

    function createFeedbackElement() {
        const div = document.createElement('div');
        div.id = 'feedback-message';
        document.body.appendChild(div);
        return div;
    }

    function getCSRFToken() {
        const tokenElement = document.querySelector('meta[name="csrf-token"]');
        if (!tokenElement) {
            console.error('CSRF token meta element not found');
            return '';
        }
        const token = tokenElement.getAttribute('content');
        if (!token) {
            console.error('CSRF token content is empty');
            return '';
        }
        console.log('Retrieved CSRF token:', token);
        return token;
    }

    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&")
            .replace(/</g, "<")
            .replace(/>/g, ">")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function setupDragAndDrop() {
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
            dropZone.classList.add('hidden');
            const files = Array.from(e.dataTransfer.files);
            processFiles(files);
        });
    }

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    async function createNewChat() {
        try {
            const data = await makeFetchRequest('/chat/new_chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            if (data.success) {
                window.location.href = `/chat/chat_interface?chat_id=${data.chat_id}`;
            } else {
                throw new Error(data.error || 'Failed to create new chat');
            }
        } catch (error) {
            console.error('Error creating new chat:', error);
            showFeedback('Failed to create new chat', 'error');
        }
    }

    function handleModelChange() {
        const modelId = modelSelect.value;
        localStorage.setItem('selectedModel', modelId);
    }

    async function handleMessageActions(event) {
        const target = event.target.closest('button');
        if (!target) return;

        try {
            if (target.classList.contains('copy-button')) {
                const content = target.closest('.max-w-lg').querySelector('.prose').textContent;
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
        button.disabled = true;
        try {
            const chatId = new URLSearchParams(window.location.search).get('chat_id');
            if (!chatId) {
                showFeedback('Chat ID not found', 'error');
                return;
            }

            const messages = Array.from(chatBox.children);
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

            while (chatBox.lastElementChild &&
                !chatBox.lastElementChild.querySelector('.bg-blue-600')) {
                chatBox.lastElementChild.remove();
            }
            if (chatBox.lastElementChild) {
                chatBox.lastElementChild.remove();
            }

            showTypingIndicator();

            const formData = new FormData();
            formData.append('message', lastUserMessage);

            const data = await makeFetchRequest('/chat', {
                method: 'POST',
                body: formData,
            });

            if (data.response) {
                appendAssistantMessage(data.response);
            } else {
                throw new Error(data.error || 'Failed to regenerate response');
            }
        } catch (error) {
            console.error('Error regenerating response:', error);
            showFeedback(error.message, 'error');
        } finally {
            button.disabled = false;
            removeTypingIndicator();
        }
    }

    async function makeFetchRequest(url, options = {}) {
        const defaultHeaders = {
            'X-CSRFToken': getCSRFToken(),
            'X-Requested-With': 'XMLHttpRequest',
        };

        options.headers = { ...defaultHeaders, ...options.headers };

        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'An error occurred.');
            }
            return await response.json();
        } catch (error) {
            console.error('Fetch error:', error);
            throw error;
        }
    }

    window.removeFile = removeFile;
})();
