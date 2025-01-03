// Markdown Rendering Setup
const renderer = new marked.Renderer();
renderer.code = function(code, language) {
    const escapedCode = code.replace(/</g, '<').replace(/>/g, '>');
    return `
        <div class="code-block">
            <pre><code class="${language || ''}">${escapedCode}</code></pre>
            <button class="copy-button" onclick="copyCode(this)">Copy</button>
        </div>
    `;
};

marked.setOptions({
    breaks: true,
    gfm: true,
    sanitize: true,
    renderer: renderer
});

function renderMarkdown(content) {
    return marked.parse(content);
}

function copyCode(button) {
    const code = button.previousElementSibling?.textContent;
    if (code) {
        navigator.clipboard.writeText(code)
            .then(() => {
                button.textContent = 'Copied!';
                setTimeout(() => button.textContent = 'Copy', 2000);
            })
            .catch(err => {
                console.error('Failed to copy:', err);
                button.textContent = 'Failed';
                setTimeout(() => button.textContent = 'Copy', 2000);
            });
    }
}

// Chat Functionality
document.addEventListener('DOMContentLoaded', function() {
    const chatBox = document.getElementById('chat-box');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const newChatBtn = document.getElementById('new-chat-btn');
    const conversationList = document.getElementById('chat-list');
    const modelSelect = document.getElementById('model-select');
    const editModelBtn = document.getElementById('edit-model-btn');
    const deleteModelBtn = document.getElementById('delete-model-btn');
    const feedbackMessage = document.getElementById('feedback-message');

    let chatId = sessionStorage.getItem('chat_id') || '';
    const isAdmin = document.body.dataset.isAdmin === 'true';

    // Convert existing messages to markdown
    document.querySelectorAll('.markdown-content').forEach(el => {
        el.innerHTML = renderMarkdown(el.textContent);
    });

    // Textarea height adjustment
    function adjustTextareaHeight(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
    }

    messageInput.addEventListener('input', function() {
        adjustTextareaHeight(this);
    });

    // New Chat functionality
    if (newChatBtn) {
        newChatBtn.addEventListener('click', async function() {
            try {
                const response = await fetch('/new_chat', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCSRFToken()
                    }
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        window.location.href = '/chat_interface';
                    }
                } else {
                    showFeedback('Failed to create new chat', 'error');
                }
            } catch (error) {
                console.error('Error creating new chat:', error);
                showFeedback('Error creating new chat', 'error');
            }
        });
    }

    // Conversation Management
    async function loadConversations() {
        try {
            const response = await fetch('/conversations', {
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            });
            if (response.ok) {
                const conversations = await response.json();
                renderConversations(conversations);
            } else {
                showFeedback('Failed to load conversations.', 'error');
            }
        } catch (error) {
            console.error('Error loading conversations:', error);
            showFeedback('Failed to load conversations.', 'error');
        }
    }

    function renderConversations(conversations) {
        conversationList.innerHTML = conversations.map(conv => `
            <div class="flex items-center px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-100 ${conv.id === chatId ? 'bg-gray-100' : ''}" data-id="${conv.id}">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
                </svg>
                <span class="flex-grow">${conv.title || 'Untitled Conversation'}</span>
                <button class="delete-conversation-btn" data-id="${conv.id}">
                    <svg class="w-4 h-4 text-gray-500 hover:text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                    </svg>
                </button>
            </div>
        `).join('');
    }

    async function loadConversation(conversationId) {
        try {
            const response = await fetch(`/load_chat/${conversationId}`, {
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            });

            if (response.ok) {
                const data = await response.json();
                chatBox.innerHTML = '';

                // Update chat ID in session storage
                sessionStorage.setItem('chat_id', conversationId);
                chatId = conversationId;

                // Update messages
                if (data.messages) {
                    data.messages.forEach(msg => {
                        if (msg.role === 'user') {
                            appendUserMessage(msg.content, msg.timestamp);
                        } else if (msg.role === 'assistant') {
                            appendAssistantMessage(msg.content, msg.timestamp);
                        }
                    });
                }

                // Update URL without page reload
                history.pushState({}, '', `/chat_interface?chat_id=${conversationId}`);

                // Update visual selection
                document.querySelectorAll('.conversation-item').forEach(item => {
                    item.classList.remove('bg-gray-100');
                });
                const currentConversationItem = document.querySelector(`[data-id="${conversationId}"]`);
                if (currentConversationItem) {
                    currentConversationItem.classList.add('bg-gray-100');
                }
            } else {
                const errorData = await response.json();
                showFeedback(errorData.error || 'Failed to load conversation', 'error');
            }
        } catch (error) {
            console.error('Error loading conversation:', error);
            showFeedback('Error loading conversation', 'error');
        }
    }

    // Message Handling
    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message && !document.querySelector('#file-list').children.length) {
            showFeedback("Please enter a message or upload files.", "error");
            return;
        }
        if (message.length > 1000) {
            showFeedback("Message is too long. Maximum length is 1000 characters.", "error");
            return;
        }

        // Get uploaded file contents
        const fileContents = [];
        const fileList = document.querySelectorAll('#file-list div');
        fileList.forEach(fileDiv => {
            const fileName = fileDiv.textContent
                .replace('×', '') // Remove the remove button text
                .trim();

            // Get content from sessionStorage
            const fileData = JSON.parse(sessionStorage.getItem(`file_${fileName}`));
            if (fileData) {
                fileContents.push({
                    name: fileName,
                    content: fileData.content
                });
            }
        });

        appendUserMessage(message);
        messageInput.value = '';
        adjustTextareaHeight(messageInput);
        messageInput.disabled = true;
        sendButton.disabled = true;
        showTypingIndicator();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    chat_id: chatId,
                    message: message,
                    files: fileContents
                }),
            });

            if (response.ok) {
                const data = await response.json();
                removeTypingIndicator();
                if (data.response) {
                    appendAssistantMessage(data.response);
                } else {
                    showFeedback(data.error || 'An error occurred while processing your message.', 'error');
                }
            } else {
                const errorData = await response.json();
                removeTypingIndicator();
                showFeedback(errorData.error || 'An error occurred while processing your message.', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            removeTypingIndicator();
            showFeedback('An error occurred while sending the message.', 'error');
        } finally {
            messageInput.disabled = false;
            sendButton.disabled = false;
            messageInput.focus();
        }
    }

    // Message Display Functions
    function appendUserMessage(message, timestamp = null) {
        const userMessageDiv = document.createElement('div');
        userMessageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end';
        const formattedTimestamp = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
        userMessageDiv.innerHTML = `
            <div>
                <div class="bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                    <div class="text-sm markdown-content">${message}</div>
                </div>
                <span class="text-xs text-gray-500 leading-none">${formattedTimestamp}</span>
            </div>
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
        `;
        userMessageDiv.querySelector('.markdown-content').innerHTML = renderMarkdown(message);
        chatBox.appendChild(userMessageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendAssistantMessage(message, timestamp = null) {
        const assistantMessageDiv = document.createElement('div');
        assistantMessageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs';
        const formattedTimestamp = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
        assistantMessageDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
            <div>
                <div class="bg-gray-300 p-3 rounded-r-lg rounded-bl-lg">
                    <div class="text-sm markdown-content">${message}</div>
                </div>
                <span class="text-xs text-gray-500 leading-none">${formattedTimestamp}</span>
            </div>
        `;
        assistantMessageDiv.querySelector('.markdown-content').innerHTML = renderMarkdown(message);
        chatBox.appendChild(assistantMessageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Typing Indicator
    function showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs typing-indicator';
        typingDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
            <div>
                <div class="bg-gray-300 p-3 rounded-r-lg rounded-bl-lg">
                    <p class="text-sm">...</p>
                </div>
                <span class="text-xs text-gray-500 leading-none">Typing...</span>
            </div>
        `;
        chatBox.appendChild(typingDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function removeTypingIndicator() {
        const typingIndicator = chatBox.querySelector('.typing-indicator');
        if (typingIndicator) {
            chatBox.removeChild(typingIndicator);
        }
    }

    // Feedback Messages
    function showFeedback(message, type) {
        feedbackMessage.textContent = message;
        feedbackMessage.className = `fixed bottom-4 right-4 p-4 rounded-lg ${type === 'success' ? 'bg-green-100 border-green-400 text-green-700' : 'bg-red-100 border-red-400 text-red-700'}`;
        feedbackMessage.classList.remove('hidden');
        setTimeout(() => feedbackMessage.classList.add('hidden'), 3000);
    }

    // Admin Model Management
    if (isAdmin) {
        if (modelSelect) {
            modelSelect.addEventListener('change', function() {
                const selectedModelId = this.value;
                editModelBtn.dataset.modelId = selectedModelId;
                deleteModelBtn.dataset.modelId = selectedModelId;
            });

            editModelBtn.addEventListener('click', function() {
                const modelId = this.dataset.modelId;
                if (modelId) {
                    window.location.href = `/models/${modelId}/edit`;
                } else {
                    showFeedback('Please select a model to edit.', 'error');
                }
            });

            deleteModelBtn.addEventListener('click', function() {
                const modelId = this.dataset.modelId;
                if (modelId) {
                    if (confirm('Are you sure you want to delete this model? Chats using this model will be migrated to the default model.')) {
                        fetch(`/models/${modelId}`, {
                            method: 'DELETE',
                            headers: {
                                'X-CSRFToken': getCSRFToken()
                            },
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                showFeedback('Model deleted successfully.', 'success');
                                window.location.reload();
                            } else {
                                showFeedback('Error: ' + (data.error || 'Failed to delete model.'), 'error');
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            showFeedback('An error occurred while deleting the model.', 'error');
                        });
                    }
                } else {
                    showFeedback('Please select a model to delete.', 'error');
                }
            });
        }
    }

    // CSRF Token Helper
    function getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    }

    // File Upload Handling
    const fileInput = document.getElementById('file-input');
    const uploadButton = document.getElementById('upload-button');

    uploadButton.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', async function() {
        if (!this.files || this.files.length === 0) return;

        const formData = new FormData();
        for (const file of this.files) {
            formData.append('file', file);
        }

        uploadButton.disabled = true;
        uploadButton.innerHTML = `
            <div class="flex items-center">
                <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Uploading...
            </div>
        `;

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRFToken()
                },
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    showFeedback('Files uploaded successfully!', 'success');
                    // Show uploaded files
                    const uploadedFilesDiv = document.getElementById('uploaded-files');
                    const fileListDiv = document.getElementById('file-list');
                    fileListDiv.innerHTML = ''; // Clear previous files

                    Array.from(this.files).forEach(file => {
                        const fileDiv = document.createElement('div');
                        fileDiv.className = 'flex items-center bg-white px-2 py-1 rounded border text-sm';
                        fileDiv.innerHTML = `
                            <svg class="w-4 h-4 mr-1 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path>
                            </svg>
                            ${file.name}
                            <button class="ml-2 text-red-500 hover:text-red-700" onclick="removeFile(this)">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                </svg>
                            </button>
                        `;
                        fileListDiv.appendChild(fileDiv);
                    });

                    uploadedFilesDiv.classList.remove('hidden');
                } else {
                    showFeedback(data.error || 'Failed to upload files', 'error');
                }
            } else {
                const errorData = await response.json();
                showFeedback(errorData.error || 'Failed to upload files', 'error');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showFeedback('An error occurred during upload', 'error');
        } finally {
            uploadButton.disabled = false;
            uploadButton.innerHTML = `
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path>
                </svg>
                Upload
            `;
            fileInput.value = ''; // Clear input
        }
    });

    // Initial Setup
    loadConversations();
    adjustTextareaHeight(messageInput);

    // Event Listeners
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keyup', function(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    conversationList.addEventListener('click', async function(event) {
        const target = event.target;
        const conversationItem = target.closest('div[data-id]');
        const deleteBtn = target.closest('.delete-conversation-btn');

        if (deleteBtn) {
            const conversationId = deleteBtn.dataset.id;
            await deleteConversation(conversationId, event);
        } else if (conversationItem) {
            const conversationId = conversationItem.dataset.id;
            await loadConversation(conversationId);
        }
    });
});
