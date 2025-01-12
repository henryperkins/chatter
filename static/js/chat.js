(function () {
  // Access utility functions from window.utils
  const { showFeedback, debounce, fetchWithCSRF } = window.utils;

  // Access markdown-it instance from the global window object
  const md = window.markdownit().use(window.markdownitPrism);
  const DOMPurify = window.DOMPurify;
  const Prism = window.Prism;

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

  // DOM Elements Cache - declared at the top for better scope
  let messageInput, sendButton, chatBox, fileInput, uploadButton,
    uploadedFilesDiv, modelSelect, newChatBtn, dropZone;

  // Initialize chat interface
  function initializeChat() {
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

    // Set up core event listeners
    sendButton.addEventListener('click', (e) => {
      e.preventDefault();
      if (!sendButton.disabled) {
        sendMessage();
      }
    });

    messageInput.addEventListener('input', debounce(function() {
      adjustTextareaHeight(this);
    }, 300));

    messageInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey && !sendButton.disabled) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Set up file handling
    if (fileInput && uploadButton) {
      uploadButton.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', handleFileSelect);
    }

    // Set up additional handlers
    if (newChatBtn) {
      newChatBtn.addEventListener('click', createNewChat);
    }
    if (modelSelect) {
      modelSelect.addEventListener('change', handleModelChange);
    }
    if (chatBox) {
      chatBox.addEventListener('click', handleMessageActions);
    }

    // Initialize UI
    setupDragAndDrop();
    adjustTextareaHeight(messageInput);
  }

  // Only initialize once when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeChat);
  } else {
    initializeChat();
  }

  async function sendMessage() {
    if (messageInput.value.trim() === '' && uploadedFiles.length === 0) {
      showFeedback('Please enter a message or upload files.', 'error');
      return;
    }

    if (messageInput.value.length > MAX_MESSAGE_LENGTH) {
      showFeedback(`Message too long. Maximum length is ${MAX_MESSAGE_LENGTH} characters.`, 'error');
      return;
    }

    const originalButtonText = sendButton.innerHTML;
    const messageText = messageInput.value.trim();

    try {
      // Disable controls and show loading state
      messageInput.disabled = true;
      sendButton.disabled = true;
      sendButton.innerHTML = '<span class="animate-spin">↻</span> Sending...';

      // Prepare form data
      const formData = new FormData();
      formData.append('message', messageText);
      uploadedFiles.forEach(file => formData.append('files[]', file));

      // Update UI immediately
      appendUserMessage(messageText);
      messageInput.value = '';
      adjustTextareaHeight(messageInput);
      showTypingIndicator();

      // Send request
      const chatId = window.CHAT_CONFIG.chatId;
      const data = await window.utils.fetchWithCSRF('/chat/', {
        method: 'POST',
        body: formData,
        headers: {
          'X-Chat-ID': chatId
        }
      });

      // Handle response
      if (data.response) {
        appendAssistantMessage(data.response);
        uploadedFiles = [];
        renderFileList();
      } else {
        throw new Error('No response received from server');
      }

      // Handle any excluded files
      if (Array.isArray(data.excluded_files)) {
        data.excluded_files.forEach(file => {
          showFeedback(`Failed to upload ${file.filename}: ${file.error}`, 'error');
        });
      }
    } catch (error) {
      showFeedback(error.message || 'Failed to send message', 'error');
      // Restore message on failure
      messageInput.value = messageText;
      adjustTextareaHeight(messageInput);
    } finally {
      messageInput.disabled = false;
      sendButton.disabled = false;
      sendButton.innerHTML = originalButtonText;
      // Remove typing indicator after assistant's message is appended
      removeTypingIndicator();
      messageInput.focus();
    }
  }

  async function editChatTitle(chatId) {
    const newTitle = prompt('Enter new chat title:');
    if (newTitle) {
      try {
        const response = await fetchWithCSRF(`/chat/update_chat_title/${chatId}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
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

  async function deleteChat(chatId) {
    if (confirm('Are you sure you want to delete this chat?')) {
      try {
        const response = await fetchWithCSRF(`/chat/delete_chat/${chatId}`, {
          method: 'DELETE',
          headers: {}
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
        ALLOWED_TAGS: [
          'b', 'i', 'em', 'strong', 'a', 'p', 'blockquote', 'code', 'pre',
          'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br',
          'hr', 'span', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
        ],
        ALLOWED_ATTR: ['href', 'src', 'alt', 'class']
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
    if (indicator) {
      indicator.remove();
    }

    indicator = document.createElement('div');
    indicator.id = 'typing-indicator';
    indicator.className = 'flex w-full mt-2 space-x-3 max-w-lg';
    indicator.innerHTML = `
      <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700"></div>
      <div class="relative max-w-lg">
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

    chatBox.appendChild(indicator);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
      indicator.style.display = 'none';
    }
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
      const data = await fetchWithCSRF('/chat/new_chat', {
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

      const data = await fetchWithCSRF('/chat/', {
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

  // Expose necessary functions to global scope
  window.editChatTitle = editChatTitle;
  window.deleteChat = deleteChat;
  window.removeFile = removeFile;
})();
