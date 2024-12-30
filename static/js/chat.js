// DOM Elements
const chatBox = document.getElementById('chat-box');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

// Auto-resize textarea
messageInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// Send message function
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    // Disable input while processing
    messageInput.value = '';
    messageInput.style.height = 'auto';
    messageInput.disabled = true;
    sendButton.disabled = true;

    try {
        // Add user message to chat
        appendMessage('user', message);

        // Send message to server
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message }),
        });

        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const data = await response.json();
        
        // Add assistant's response to chat
        appendMessage('assistant', data.response);

    } catch (error) {
        console.error('Error:', error);
        appendMessage('system', 'An error occurred while sending the message.');
    } finally {
        // Re-enable input
        messageInput.disabled = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

// Append message to chat box
function appendMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const header = document.createElement('div');
    header.className = 'message-header';
    
    const icon = document.createElement('i');
    icon.className = `fas fa-${role === 'user' ? 'user' : 'robot'}`;
    
    const roleSpan = document.createElement('span');
    roleSpan.className = 'message-role';
    roleSpan.textContent = role;
    
    const timeSpan = document.createElement('span');
    timeSpan.className = 'message-time';
    timeSpan.textContent = new Date().toLocaleTimeString();
    
    header.appendChild(icon);
    header.appendChild(roleSpan);
    header.appendChild(timeSpan);
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = content; // Using innerHTML to render markdown
    
    messageDiv.appendChild(header);
    messageDiv.appendChild(contentDiv);
    
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Start new chat
async function startNewChat() {
    try {
        const response = await fetch('/new_chat', {
            method: 'POST',
        });
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
        const data = await response.json();
        window.location.reload(); // Reload to show new chat
        
    } catch (error) {
        console.error('Error starting new chat:', error);
        alert('Failed to start new chat');
    }
}

// Load existing chat
async function loadChat(chatId) {
    try {
        const response = await fetch(`/load_chat/${chatId}`);
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
        const data = await response.json();
        
        // Clear current chat
        chatBox.innerHTML = '';
        
        // Load messages
        data.messages.forEach(msg => {
            appendMessage(msg.role, msg.content);
        });
        
        // Update active chat in sidebar
        document.querySelectorAll('.chat-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`[onclick="loadChat('${chatId}')"]`).classList.add('active');
        
    } catch (error) {
        console.error('Error loading chat:', error);
        alert('Failed to load chat');
    }
}

// Delete chat
async function deleteChat(chatId, event) {
    event.stopPropagation(); // Prevent chat loading when clicking delete
    
    if (!confirm('Are you sure you want to delete this chat?')) {
        return;
    }
    
    try {
        const response = await fetch(`/delete_chat/${chatId}`, {
            method: 'DELETE',
        });
        
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
        // Remove chat from sidebar
        const chatItem = document.querySelector(`[onclick="loadChat('${chatId}')"]`).parentNode;
        chatItem.remove();
        
        // If deleted current chat, start a new one
        if (chatItem.classList.contains('active')) {
            window.location.reload();
        }
        
    } catch (error) {
        console.error('Error deleting chat:', error);
        alert('Failed to delete chat');
    }
}

// Copy message to clipboard
function copyToClipboard() {
    const text = document.querySelector('.message.assistant .message-content').innerText;
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard');
    }).catch(err => {
        console.error('Error copying to clipboard:', err);
    });
}

// Retry sending message
function retryMessage() {
    const lastMessage = document.querySelector('.message.user .message-content').innerText;
    messageInput.value = lastMessage;
    sendMessage();
}

// Event listeners
sendButton.onclick = sendMessage;
messageInput.onkeyup = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
};

// Initialize auto-resize for textarea
messageInput.setAttribute('style', 'height:' + (messageInput.scrollHeight) + 'px;overflow-y:hidden;');