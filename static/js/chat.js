// static/js/chat.js

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const chatBox = document.getElementById('chat-box');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const fileInput = document.getElementById('file-input');
    const uploadStatus = document.getElementById('upload-status');
    const newChatBtn = document.getElementById('new-chat-btn');
    const conversationList = document.getElementById('chat-list');
    const contextTextarea = document.getElementById('context-textarea');
    const saveContextBtn = document.getElementById('save-context-btn');
    const clearContextBtn = document.getElementById('clear-context-btn');
    const modelSelect = document.getElementById('model-select');
    const addModelBtn = document.getElementById('add-model-btn');
    const editModelBtn = document.getElementById('edit-model-btn');
    const deleteModelBtn = document.getElementById('delete-model-btn');

    // Helper Functions
    function adjustTextareaHeight(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
    }

    // Auto-resize message input
    messageInput.addEventListener('input', function() {
        adjustTextareaHeight(this);
    });

    // Save context
    if (saveContextBtn) {
        saveContextBtn.addEventListener('click', async () => {
            const context = contextTextarea.value.trim();
            try {
                await fetch(`/chat/{{ chat_id }}/context`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ context })
                });
                alert('Context saved successfully');
            } catch (error) {
                console.error('Error saving context:', error);
                alert('Failed to save context');
            }
        });
    }

    // Clear context
    if (clearContextBtn) {
        clearContextBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to clear the context?')) {
                contextTextarea.value = '';
            }
        });
    }

    // Load conversations
    async function loadConversations() {
        try {
            const response = await fetch('/conversations');
            const conversations = await response.json();
            renderConversations(conversations);
        } catch (error) {
            console.error('Error loading conversations:', error);
        }
    }

    // Render conversations in sidebar
    function renderConversations(conversations) {
        conversationList.innerHTML = conversations.map(conv => `
            <div class="conversation-item ${conv.id === '{{ chat_id }}' ? 'active' : ''}" 
                 data-id="${conv.id}">
                ${conv.title || 'Untitled Conversation'}
                <i class="fas fa-trash float-right delete-conversation-btn" data-id="${conv.id}"></i>
            </div>
        `).join('');
    }

    // Event delegation for conversation items
    conversationList.addEventListener('click', function(event) {
        const target = event.target;
        const conversationItem = target.closest('.conversation-item');
        const deleteBtn = target.closest('.delete-conversation-btn');

        if (deleteBtn) {
            const conversationId = deleteBtn.dataset.id;
            deleteConversation(conversationId, event);
        } else if (conversationItem) {
            const conversationId = conversationItem.dataset.id;
            loadConversation(conversationId);
        }
    });

    // Load a specific conversation
    async function loadConversation(conversationId) {
        window.location.href = `/chat/${conversationId}`;
    }

    // Delete a conversation
    async function deleteConversation(conversationId, event) {
        event.stopPropagation();
        if (confirm('Are you sure you want to delete this conversation?')) {
            try {
                await fetch(`/conversations/${conversationId}`, { method: 'DELETE' });
                loadConversations();
            } catch (error) {
                console.error('Error deleting conversation:', error);
            }
        }
    }

    // Start new chat
    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => {
            window.location.href = '/new-chat';
        });
    }

    // Send message function
    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;
        
        // Display user's message
        const userMessageDiv = document.createElement('div');
        userMessageDiv.className = 'message user';
        userMessageDiv.innerHTML = `<strong>user:</strong> ${message}`;
        chatBox.appendChild(userMessageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    
        // Add loading indicator for assistant's response
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message assistant loading';
        loadingDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Thinking...';
        chatBox.appendChild(loadingDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    
        // Clear input and disable controls
        messageInput.value = '';
        messageInput.style.height = 'auto';
        messageInput.disabled = true;
        sendButton.disabled = true;
    
        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ chat_id: '{{ chat_id }}', message: message }),
            });
            const data = await response.json();
            // Remove loading indicator
            chatBox.removeChild(loadingDiv);
    
            // Display assistant's response
            const assistantMessageDiv = document.createElement('div');
            assistantMessageDiv.className = 'message assistant';
            assistantMessageDiv.innerHTML = `<strong>assistant:</strong> ${marked.parse(data.response)}`;
            chatBox.appendChild(assistantMessageDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
        } catch (error) {
            console.error('Error:', error);
            // Remove loading indicator and show error
            chatBox.removeChild(loadingDiv);
            const errorDiv = document.createElement('div');
            errorDiv.className = 'message system';
            errorDiv.innerHTML = '<strong>system:</strong> An error occurred while sending the message.';
            chatBox.appendChild(errorDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
        } finally {
            messageInput.disabled = false;
            sendButton.disabled = false;
            messageInput.focus();
        }
    }

    // File upload handling
    if (fileInput) {
        fileInput.addEventListener('change', () => {
            const files = fileInput.files;
            if (!files.length) return;
    
            uploadStatus.style.display = 'block';
            uploadStatus.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';
    
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
    
            fetch('/upload', {
                method: 'POST',
                body: formData,
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    uploadStatus.innerHTML = `<i class="fas fa-check-circle" style="color: green;"></i> Files uploaded: ${data.files.join(', ')}`;
                } else {
                    uploadStatus.innerHTML = `<i class="fas fa-times-circle" style="color: red;"></i> Error: ${data.error}`;
                }
                setTimeout(() => {
                    uploadStatus.style.display = 'none';
                }, 3000);
            })
            .catch(error => {
                console.error('Error:', error);
                uploadStatus.innerHTML = `<i class="fas fa-times-circle" style="color: red;"></i> Upload failed`;
                setTimeout(() => {
                    uploadStatus.style.display = 'none';
                }, 3000);
            });
        });
    }

    // Event listeners for sending message
    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }
    if (messageInput) {
        messageInput.addEventListener('keyup', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        });
    }

    // Model Management Functions
    async function loadModels() {
        try {
            const response = await fetch('/models');
            const models = await response.json();
            modelSelect.innerHTML = '<option value="">Select Model</option>' +
                models.map(model => `
                    <option value="${model.id}" ${model.is_default ? 'selected' : ''}>
                        ${model.name}${model.is_default ? ' (Default)' : ''}
                    </option>
                `).join('');
        } catch (error) {
            console.error('Error loading models:', error);
        }
    }

    // Add new model
    if (addModelBtn) {
        addModelBtn.addEventListener('click', () => {
            const name = prompt('Enter model name:');
            if (!name) return;
            
            const description = prompt('Enter model description (optional):');
            const apiEndpoint = prompt('Enter API endpoint:');
            const apiKey = prompt('Enter API key:');
            
            fetch('/models', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    name,
                    description,
                    api_endpoint: apiEndpoint,
                    api_key: apiKey
                }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadModels();
                } else {
                    alert('Error adding model: ' + data.error);
                }
            })
            .catch(error => console.error('Error adding model:', error));
        });
    }

    // Edit selected model
    if (editModelBtn) {
        editModelBtn.addEventListener('click', () => {
            const modelId = modelSelect.value;
            if (!modelId) return alert('Please select a model to edit');
            
            const name = prompt('Enter new model name:');
            if (!name) return;
            
            const description = prompt('Enter new model description (optional):');
            const apiEndpoint = prompt('Enter new API endpoint:');
            const apiKey = prompt('Enter new API key:');
            
            fetch(`/models/${modelId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    name,
                    description,
                    api_endpoint: apiEndpoint,
                    api_key: apiKey
                }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadModels();
                } else {
                    alert('Error updating model: ' + data.error);
                }
            })
            .catch(error => console.error('Error updating model:', error));
        });
    }

    // Delete selected model
    if (deleteModelBtn) {
        deleteModelBtn.addEventListener('click', () => {
            const modelId = modelSelect.value;
            if (!modelId) return alert('Please select a model to delete');
            
            if (confirm('Are you sure you want to delete this model?')) {
                fetch(`/models/${modelId}`, {
                    method: 'DELETE',
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        loadModels();
                    } else {
                        alert('Error deleting model: ' + data.error);
                    }
                })
                .catch(error => console.error('Error deleting model:', error));
            }
        });
    }

    // Initialize
    loadConversations();
    loadModels();
    adjustTextareaHeight(messageInput);
});