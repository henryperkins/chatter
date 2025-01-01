document.addEventListener('DOMContentLoaded', function() {
    const chatBox = document.getElementById('chat-box');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const fileInput = document.getElementById('file-input');
    const uploadStatus = document.getElementById('upload-status');
    const newChatBtn = document.getElementById('new-chat-btn');
    const conversationList = document.getElementById('chat-list');
    const modelSelect = document.getElementById('model-select');
    const addModelBtn = document.getElementById('add-model-btn');
    const editModelBtn = document.getElementById('edit-model-btn');
    const deleteModelBtn = document.getElementById('delete-model-btn');

    function adjustTextareaHeight(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
    }

    messageInput.addEventListener('input', function() {
        adjustTextareaHeight(this);
    });

    async function loadConversations() {
        try {
            const response = await fetch('/conversations');
            if (response.ok) {
                const conversations = await response.json();
                renderConversations(conversations);
            } else {
                showToast('Failed to load conversations', 'error');
            }
        } catch (error) {
            console.error('Error loading conversations:', error);
            showToast('Failed to load conversations', 'error');
        }
    }

    function renderConversations(conversations) {
        conversationList.innerHTML = conversations.map(conv => `
            <div class="flex items-center px-3 py-2 rounded-lg cursor-pointer hover:bg-gray-100 ${conv.id === chatId ? 'bg-gray-100' : ''}" data-id="${conv.id}">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                <span class="flex-grow">${conv.title || 'Untitled Conversation'}</span>
                <button class="delete-conversation-btn" data-id="${conv.id}">
                    <svg class="w-4 h-4 text-gray-500 hover:text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                </button>
            </div>
        `).join('');
    }

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

    async function loadConversation(conversationId) {
        try {
            const response = await fetch(apiUrls.loadChat(conversationId));
            if (response.ok) {
                const data = await response.json();

                // Clear the current chat messages
                chatBox.innerHTML = '';

                // Append the messages to the chatbox
                appendMessages(data.messages);

                // Update the session storage with the current chat_id
                sessionStorage.setItem('chat_id', conversationId);

                // Update the URL without reloading the page
                history.pushState({}, '', `/chat_interface?chat_id=${conversationId}`);

                // Optionally, update the UI to reflect the current chat
                // For example, highlight the selected conversation in the sidebar
                document.querySelectorAll('.conversation-item').forEach(item => {
                    item.classList.remove('bg-gray-100');
                });
                const currentConversationItem = document.querySelector(`.conversation-item[data-id="${conversationId}"]`);
                if (currentConversationItem) {
                    currentConversationItem.classList.add('bg-gray-100');
                }
            } else {
                showToast('Failed to load conversation', 'error');
            }
        } catch (error) {
            console.error('Error loading conversation:', error);
            showToast('Failed to load conversation', 'error');
        }
    }

    async function deleteConversation(conversationId, event) {
        event.stopPropagation();
        if (confirm('Are you sure you want to delete this conversation?')) {
            try {
                const response = await fetch(apiUrls.deleteChat(conversationId), {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCSRFToken() // Include CSRF token
                    }
                });
                if (response.ok) {
                    // Check if the current chat is the one being deleted
                    if (conversationId === chatId) {
                        // Redirect to new chat only if the current chat is deleted
                        window.location.href = '/new_chat';
                    } else {
                        // Otherwise, just reload the conversations
                        await loadConversations();
                        showToast('Conversation deleted', 'success');
                    }
                } else {
                    showToast('Failed to delete conversation', 'error');
                }
            } catch (error) {
                console.error('Error deleting conversation:', error);
                showToast('Failed to delete conversation', 'error');
            }
        }
    }

    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;

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
                body: JSON.stringify({ chat_id: chatId, message: message }),
            });

            if (response.ok) {
                const data = await response.json();
                removeTypingIndicator();
                appendAssistantMessage(data.response);
            } else {
                const errorData = await response.json();
                removeTypingIndicator();
                showErrorInChat(errorData.error || 'An error occurred while processing your message.');
            }
        } catch (error) {
            console.error('Error:', error);
            removeTypingIndicator();
            showErrorInChat('An error occurred while sending the message.');
        } finally {
            messageInput.disabled = false;
            sendButton.disabled = false;
            messageInput.focus();
        }
    }

    function appendUserMessage(message) {
        const userMessageDiv = document.createElement('div');
        userMessageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end';
        userMessageDiv.innerHTML = `
            <div>
                <div class="bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                    <p class="text-sm">${message}</p>
                </div>
                <span class="text-xs text-gray-500 leading-none">${formatTimestamp(new Date())}</span>
            </div>
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300">
                <svg class="w-full h-full" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
            </div>
        `;
        chatBox.appendChild(userMessageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendAssistantMessage(message) {
        const assistantMessageDiv = document.createElement('div');
        assistantMessageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs';
        assistantMessageDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300">
                <svg class="w-full h-full" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            </div>
            <div>
                <div class="bg-gray-300 p-3 rounded-r-lg rounded-bl-lg">
                    <p class="text-sm">${marked.parse(message)}</p>
                </div>
                <span class="text-xs text-gray-500 leading-none">${formatTimestamp(new Date())}</span>
            </div>
        `;
        chatBox.appendChild(assistantMessageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function showTypingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs typing-indicator';
        loadingDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300">
                <svg class="w-full h-full" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            </div>
            <div>
                <div class="bg-gray-300 p-3 rounded-r-lg rounded-bl-lg">
                    <p class="text-sm">...</p>
                </div>
                <span class="text-xs text-gray-500 leading-none">Typing...</span>
            </div>
        `;
        chatBox.appendChild(loadingDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function removeTypingIndicator() {
        const typingIndicator = chatBox.querySelector('.typing-indicator');
        if (typingIndicator) {
            chatBox.removeChild(typingIndicator);
        }
    }

    function showErrorInChat(errorMessage) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs';
        errorDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300">
                <svg class="w-full h-full" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            </div>
            <div>
                <div class="bg-red-300 p-3 rounded-r-lg rounded-bl-lg">
                    <p class="text-sm text-red-800">${errorMessage}</p>
                </div>
            </div>
        `;
        chatBox.appendChild(errorDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function formatTimestamp(date) {
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    if (fileInput) {
        fileInput.addEventListener('change', () => {
            const files = fileInput.files;
            if (!files.length) return;

            uploadStatus.classList.remove('hidden');
            uploadStatus.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';

            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append('file', files[i]);
            }

            fetch('/upload', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCSRFToken()
                },
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
                    uploadStatus.classList.add('hidden');
                }, 3000);
            })
            .catch(error => {
                console.error('Error:', error);
                uploadStatus.innerHTML = `<i class="fas fa-times-circle" style="color: red;"></i> Upload failed`;
                setTimeout(() => {
                    uploadStatus.classList.add('hidden');
                }, 3000);
            });
        });
    }

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

    function showToast(message, type = 'success') {
        const toastContainer = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast-${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            toastContainer.removeChild(toast);
        }, 3000);
    }

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

    function getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    }

    async function handleModelChange(modelId) {
        try {
            const response = await fetch(apiUrls.setModel(modelId), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                }
            });
            if (!response.ok) throw new Error('Failed to update model');
            return true;
        } catch (error) {
            console.error('Error updating model:', error);
            return false;
        }
    }

    // Update the model select handler
    if (modelSelect) {
        modelSelect.addEventListener('change', async function() {
            const modelId = this.value;
            if (modelId) {
                const success = await handleModelChange(modelId);
                if (success) {
                    editModelBtn.dataset.modelId = modelId;
                    deleteModelBtn.dataset.modelId = modelId;
                } else {
                    this.value = ''; // Reset selection on failure
                    alert('Failed to update model selection');
                }
            }
        });
    }

    // Update delete model handler
    if (deleteModelBtn) {
        deleteModelBtn.addEventListener('click', async function() {
            const modelId = this.dataset.modelId;
            if (!modelId) {
                alert('Please select a model to delete');
                return;
            }

            if (!confirm('Are you sure you want to delete this model?')) return;

            try {
                const response = await fetch(apiUrls.deleteModel(modelId), {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCSRFToken()
                    }
                });

                if (!response.ok) throw new Error('Failed to delete model');

                // Refresh models list
                await loadModels();
                showToast('Model deleted successfully');
            } catch (error) {
                console.error('Error deleting model:', error);
                showToast('Failed to delete model', 'error');
            }
        });
    }

    // Initialize
    loadConversations();
    loadModels();
    adjustTextareaHeight(messageInput);
});

const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar = document.querySelector('.sidebar');

if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function() {
        sidebar.classList.toggle('hidden');
    });
}
