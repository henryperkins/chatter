// Initialize required libraries
const md = window.markdownit({
    html: false,
    linkify: true,
    typographer: true,
    highlight(str, lang) {
        if (lang && Prism.languages[lang]) {
            return Prism.highlight(str, Prism.languages[lang], lang);
        }
        return '';
    }
});

// Global variables and state
let uploadedFiles = [];
const MAX_FILES = 5;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_MESSAGE_LENGTH = 1000;
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

// Add at the top of chat.js after initial declarations
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded');
    
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
    
    console.log('Elements found:', {
        messageInput: !!messageInput,
        sendButton: !!sendButton,
        chatBox: !!chatBox,
        fileInput: !!fileInput,
        uploadButton: !!uploadButton,
        uploadedFilesDiv: !!uploadedFilesDiv,
        modelSelect: !!modelSelect,
        newChatBtn: !!newChatBtn,
        dropZone: !!dropZone

    });

    // Verify critical elements exist
    if (!messageInput || !sendButton || !chatBox) {
        console.error('Critical chat elements not found');
        return;
    }

    // Initialize event listeners
    initializeEventListeners();
    
    // Set up file drag and drop
    setupDragAndDrop();
    
    // Initialize message input
    adjustTextareaHeight(messageInput);
});

// Initialize DOM elements and event listeners
// document.addEventListener('DOMContentLoaded', function() {
//     // Cache DOM elements
//     messageInput = document.getElementById('message-input');
//     sendButton = document.getElementById('send-button');
//     chatBox = document.getElementById('chat-box');
//     fileInput = document.getElementById('file-input');
//     uploadButton = document.getElementById('upload-button');
//     uploadedFilesDiv = document.getElementById('uploaded-files');
//     modelSelect = document.getElementById('model-select');
//     newChatBtn = document.getElementById('new-chat-btn');
//     dropZone = document.getElementById('drop-zone');

//     // Verify critical elements exist
//     if (!messageInput || !sendButton || !chatBox) {
//         console.error('Critical chat elements not found');
//         return;
//     }

//     // Initialize event listeners
//     initializeEventListeners();
    
//     // Set up file drag and drop
//     setupDragAndDrop();
    
//     // Initialize message input
//     adjustTextareaHeight(messageInput);
// });

function initializeEventListeners() {
    // Message input handlers
    messageInput.addEventListener('input', function() {
        adjustTextareaHeight(this);
    });

    messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Send button handler
    // sendButton.addEventListener('click', sendMessage);

    // Initialize send button handler
    if (sendButton) {
        console.log('Adding click handler to send button');
        sendButton.addEventListener('click', async function(e) {
            e.preventDefault();
            console.log('Send button clicked');
            
            // if (!messageInput.value.trim() && uploadedFiles.length === 0) {
            //     console.log('No message or files to send');
            //     return;
            // }

            // try {
            //     console.log('Creating FormData');
            //     const formData = new FormData();
            //     formData.append('message', messageInput.value.trim());
                
            //     console.log('Getting CSRF token');
            //     const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            //     console.log('CSRF token found:', !!csrfToken);

            //     console.log('Sending fetch request to /chat');
            //     const response = await fetch('/chat', {
            //         method: 'POST',
            //         headers: {
            //             'X-CSRFToken': csrfToken,
            //             'X-Requested-With': 'XMLHttpRequest'
            //         },
            //         body: formData
            //     });

            //     console.log('Response received:', response.status);
            //     const data = await response.json();
            //     console.log('Response data:', data);
                
            // } catch (error) {
            //     console.error('Error in send handler:', error);
            // }
            sendMessage();
        });
    } else {
        console.error('Send button not found in DOM');
    }

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

// Message sending functionality
async function sendMessage() {
    if (!messageInput.value.trim() && uploadedFiles.length === 0) {
        showFeedback('Please enter a message or upload files.', 'error');
        console.log('No message or files to send');
        return;
    }

    if (messageInput.value.length > MAX_MESSAGE_LENGTH) {
        showFeedback(`Message too long. Maximum length is ${MAX_MESSAGE_LENGTH} characters.`, 'error');
        return;
    }

    // Disable input controls
    messageInput.disabled = true;
    sendButton.disabled = true;

    // Show loading state
    sendButton.innerHTML = '<span class="animate-spin">↻</span>';

    // Create form data
    const formData = new FormData();
    formData.append('message', messageInput.value.trim());
    uploadedFiles.forEach(file => formData.append('files[]', file));

    try {
        // Append user message immediately
        appendUserMessage(messageInput.value.trim());
        messageInput.value = '';
        adjustTextareaHeight(messageInput);

        // Show typing indicator
        showTypingIndicator();

        console.log('Getting CSRF token');
        const csrfToken = getCSRFToken();
        console.log('CSRF token found:', !!csrfToken);

        console.log('Sending fetch request to /chat');
        // Send request
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        });

        console.log('Response received:', response.status);

        // Remove typing indicator
        removeTypingIndicator();

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Response data:', data);
        
        // Handle successful response
        if (data.response) {
            appendAssistantMessage(data.response);
            uploadedFiles = [];
            renderFileList();
        }

        // Handle file upload results
        if (data.excluded_files) {
            data.excluded_files.forEach(file => {
                showFeedback(`Failed to upload ${file.filename}: ${file.error}`, 'error');
            });
        }

    } catch (error) {
        console.error('Error sending message:', error);
        showFeedback('Failed to send message. Please try again.', 'error');
        removeTypingIndicator();
    } finally {
        // Re-enable input controls
        messageInput.disabled = false;
        sendButton.disabled = false;
        sendButton.innerHTML = 'Send';
    }
}

// Message display functions
function appendUserMessage(message) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end';
    messageDiv.innerHTML = `
        <div>
            <div class="relative bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                <p class="text-sm">${escapeHtml(message)}</p>
                <button class="edit-message-button absolute -left-6 top-2 text-gray-500 hover:text-gray-700">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                              d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                    </svg>
                </button>
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
            <div class="absolute right-0 top-0 flex space-x-2">
                <button class="copy-button p-1 text-gray-500 hover:text-gray-700" title="Copy to clipboard">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                              d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"/>
                    </svg>
                </button>
                <button class="regenerate-button p-1 text-gray-500 hover:text-gray-700" title="Regenerate response">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                    </svg>
                </button>
            </div>
            <span class="text-xs text-gray-500 dark:text-gray-400 leading-none">
                ${new Date().toLocaleTimeString()}
            </span>
        </div>
    `;

    const contentDiv = messageDiv.querySelector('.prose');
    if (contentDiv) {
        contentDiv.innerHTML = md.render(message);
        Prism.highlightAllUnder(contentDiv);
    }

    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// File handling functions
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
            <button class="text-red-500 hover:text-red-700" onclick="removeFile(${index})">
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

// Utility functions
function adjustTextareaHeight(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
}

function showTypingIndicator() {
    const indicator = document.createElement('div');
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
    chatBox.scrollTop = chatBox.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
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
    }, 3000);
}

function createFeedbackElement() {
    const div = document.createElement('div');
    div.id = 'feedback-message';
    document.body.appendChild(div);
    return div;
}

function getCSRFToken() {
    const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (!token) {
        throw new Error('CSRF token not found');
    }
    return token;
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&")
        .replace(/</g, "<")
        .replace(/>/g, ">")
        .replace(/"/g, """)
        .replace(/'/g, "'");
}

// Message action handlers
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
        } else if (target.classList.contains('edit-message-button')) {
            editLastMessage();
        }
    } catch (error) {
        console.error('Error handling message action:', error);
        showFeedback('Failed to perform action', 'error');
    }
}

// Response regeneration
async function regenerateResponse(button) {
    button.disabled = true;
    try {
        const chatId = new URLSearchParams(window.location.search).get('chat_id');
        if (!chatId) {
            showFeedback('Chat ID not found', 'error');
            return;
        }

        // Get last user message
        const messages = Array.from(chatBox.children);
        let lastUserMessage = null;
        for (let i = messages.length - 1; i >= 0; i--) {
            const messageDiv = messages[i];
            if (messageDiv.querySelector('.bg-blue-600')) {
                const content = messageDiv.querySelector('.text-sm').textContent;
                lastUserMessage = content;
                break;
            }
        }

        if (!lastUserMessage) {
            showFeedback('No message found to regenerate', 'error');
            return;
        }

        // Remove messages after last user message
        while (chatBox.lastElementChild && 
               !chatBox.lastElementChild.querySelector('.bg-blue-600')) {
            chatBox.lastElementChild.remove();
        }
        if (chatBox.lastElementChild) {
            chatBox.lastElementChild.remove();
        }

        // Show typing indicator
        showTypingIndicator();

        // Send regenerate request
        const formData = new FormData();
        formData.append('message', lastUserMessage);

        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        });

        const data = await response.json();
        
        if (response.ok && data.response) {
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

// Message editing
function editLastMessage() {
    const messages = Array.from(chatBox.children);
    let lastUserMessageElement = null;

    // Find last user message
    for (let i = messages.length - 1; i >= 0; i--) {
        const messageDiv = messages[i];
        if (messageDiv.querySelector('.bg-blue-600')) {
            lastUserMessageElement = messageDiv;
            break;
        }
    }

    if (!lastUserMessageElement) {
        showFeedback('No message found to edit', 'error');
        return;
    }

    // Get message content
    const messageContent = lastUserMessageElement.querySelector('.text-sm').textContent;

    // Set message in input
    messageInput.value = messageContent;
    adjustTextareaHeight(messageInput);

    // Remove messages after and including the last user message
    while (chatBox.lastElementChild !== lastUserMessageElement) {
        chatBox.lastElementChild.remove();
    }
    lastUserMessageElement.remove();

    // Focus input
    messageInput.focus();
    showFeedback('Message ready to edit', 'success');
}

// New chat creation
async function createNewChat() {
    try {
        const response = await fetch('/chat/new_chat', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const data = await response.json();
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

// Model selection handling
function handleModelChange() {
    const modelId = modelSelect.value;
    localStorage.setItem('selectedModel', modelId);
}

// Drag and drop setup
function setupDragAndDrop() {
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    document.addEventListener('dragenter', () => {
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

// Export functions that need to be globally accessible
window.removeFile = removeFile;