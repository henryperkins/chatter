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
            const response = await fetch(`/load_chat/${conversationId}`);
            if (response.ok) {
                const data = await response.json();

                // Clear the current chat messages
                chatBox.innerHTML = '';

                // Append the messages to the chatbox
                appendMessages(data.messages);

                // Update the session storage with the current chat_id
                sessionStorage.setItem('chat_id', conversationId);
                chatId = conversationId;

                // Update the URL without reloading the page
                history.pushState({}, '', `/chat_interface?chat_id=${conversationId}`);

                // Highlight the selected conversation in the sidebar
                document.querySelectorAll('.conversation-item').forEach(item => {
                    item.classList.remove('bg-gray-100');
                });
                const currentConversationItem = document.querySelector(`.conversation-item[data-id="${conversationId}"]`);
                if (currentConversationItem) {
                    currentConversationItem.classList.add('bg-gray-100');
                }
            } else {
                const errorData = await response.json();
                showFeedback(errorData.error || 'Failed to load conversation.', 'error');
            }
        } catch (error) {
            console.error('Error loading conversation:', error);
            showFeedback('Failed to load conversation.', 'error');
        }
    }

    async function deleteConversation(conversationId, event) {
        event.stopPropagation();
        if (confirm('Are you sure you want to delete this conversation?')) {
            try {
                const response = await fetch(`/delete_chat/${conversationId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCSRFToken()
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
                        showFeedback('Conversation deleted.', 'success');
                    }
                } else {
                   const errorData = await response.json();
                   showFeedback(errorData.error || 'Failed to delete conversation.', 'error');
                }
            } catch (error) {
                console.error('Error deleting conversation:', error);
                showFeedback('Failed to delete conversation.', 'error');
            }
        }
    }

     function appendMessages(messages) {
        messages.forEach(message => {
            if (message.role === 'user') {
                appendUserMessage(message.content, message.timestamp);
            } else if (message.role === 'assistant') {
                appendAssistantMessage(message.content, message.timestamp);
            }
        });
       chatBox.scrollTop = chatBox.scrollHeight;
    }

    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) {
            showFeedback("Message cannot be empty.", "error");
            return;
        }
        if (message.length > 1000) {
            showFeedback("Message is too long. Maximum length is 1000 characters.", "error");
            return;
        }


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
                    'X-CSRFToken': getCSRFToken() // Include CSRF token here
                },
                body: JSON.stringify({ chat_id: chatId, message: message }),
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

    function appendUserMessage(message, timestamp = null) {
        const userMessageDiv = document.createElement('div');
        userMessageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end';
         const formattedTimestamp = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString()
        userMessageDiv.innerHTML = `
            <div>
                <div class="bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                    <p class="text-sm">${message}</p>
                </div>
                <span class="text-xs text-gray-500 leading-none">${formattedTimestamp}</span>
            </div>
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300">
                <!-- User avatar placeholder -->
            </div>
        `;
        chatBox.appendChild(userMessageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendAssistantMessage(message, timestamp = null) {
        const assistantMessageDiv = document.createElement('div');
        assistantMessageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs';
         const formattedTimestamp = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString()
        assistantMessageDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300">
                <!-- Assistant avatar placeholder -->
            </div>
            <div>
                <div class="bg-gray-300 p-3 rounded-r-lg rounded-bl-lg">
                    <p class="text-sm">${message}</p>
                </div>
                <span class="text-xs text-gray-500 leading-none">${formattedTimestamp}</span>
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
                <!-- Assistant avatar placeholder -->
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

    function showFeedback(message, type) {
        feedbackMessage.textContent = message;
         feedbackMessage.className = `fixed bottom-4 right-4 p-4 rounded-lg ${type === 'success' ? 'bg-green-100 border-green-400 text-green-700' : 'bg-red-100 border-red-400 text-red-700'}`;
        feedbackMessage.classList.remove('hidden');
        setTimeout(() => feedbackMessage.classList.add('hidden'), 3000);
    }


    function getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    }

     // Handle model selection change event.
     if (modelSelect) {
         modelSelect.addEventListener('change', async function() {
            const selectedModelId = this.value;
            try{
            const response = await fetch(`/models/default/${selectedModelId}`, {
                method: 'POST',
                headers: {
                  'X-CSRFToken': getCSRFToken()
                }
            });
            if(response.ok) {
                showFeedback('Default model updated.', 'success');
                // You may want to reload models here, but not required.

            }
            else {
                const errorData = await response.json();
                showFeedback(errorData.error || "Failed to update default model.", "error");
            }
            } catch(error) {
                 console.error('Error updating default model: ', error);
                  showFeedback("Failed to update default model.", "error");
            }
        });
    }


     // Initial setup
     loadConversations();
     adjustTextareaHeight(messageInput);
     });
