(function () {
  // Access utility functions from window.utils
  const { showFeedback, fetchWithCSRF } = window.utils;

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

  // DOM Elements Cache
  let messageInput, sendButton, chatBox, fileInput, uploadButton,
    uploadedFilesDiv, modelSelect, newChatBtn, dropZone;

  // Initialize chat interface
  function initializeChat() {
    // Prevent multiple initializations
    if (window.chatInitialized) return;
    window.chatInitialized = true;

    // Mobile-specific setup
    if (window.innerWidth < 768) {
        // Adjust textarea height for mobile
        messageInput.style.minHeight = '2.5rem';
        messageInput.style.maxHeight = '6rem';
        
        // Hide sidebar by default on mobile
        const sidebar = document.getElementById('sidebar');
        if (sidebar) {
            sidebar.classList.add('-translate-x-full');
        }
    }

    // Add touch event listeners for mobile
    if ('ontouchstart' in window) {
        messageInput.addEventListener('touchstart', handleMessageInput);
        if (sendButton) {
            sendButton.addEventListener('touchend', handleSendButtonClick);
        }
    }

    // Cache and verify DOM elements
    const requiredElements = {
      'message-input': el => messageInput = el,
      'send-button': el => sendButton = el,
      'chat-box': el => chatBox = el
    };

    const optionalElements = {
      'file-input': el => fileInput = el,
      'upload-button': el => uploadButton = el,
      'uploaded-files': el => uploadedFilesDiv = el,
      'model-select': el => modelSelect = el,
      'new-chat-btn': el => newChatBtn = el,
      'drop-zone': el => dropZone = el
    };

    let missingElements = false;

    // Verify required elements exist
    for (const [id, setter] of Object.entries(requiredElements)) {
      const element = document.getElementById(id);
      if (!element) {
        console.error(`Required element #${id} not found`);
        missingElements = true;
      } else {
        setter(element);
      }
    }

    if (missingElements) {
      showFeedback('Critical UI elements are missing. Please reload the page.', 'error');
      return;
    }

    // Set optional elements if they exist
    for (const [id, setter] of Object.entries(optionalElements)) {
      const element = document.getElementById(id);
      if (element) {
        setter(element);
      }
    }

    // Set up core event listeners
    if (!window.eventListenersAttached) {
      window.eventListenersAttached = true;

      // Set up core event listeners
      sendButton.addEventListener('click', handleSendButtonClick);
      messageInput.addEventListener('input', handleMessageInput);
      messageInput.addEventListener('keydown', handleMessageKeydown);
    }

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

    // Disable controls and show loading state
    messageInput.disabled = true;
    sendButton.disabled = true;
    sendButton.innerHTML = '<span class="animate-spin">↻</span> Sending...';

    try {
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
      const data = await fetchWithCSRF('/chat/', {
        method: 'POST',
        body: formData,
        headers: {
          'X-Chat-ID': chatId,
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      // Handle response
      if (data.response) {
        appendAssistantMessage(data.response);
        uploadedFiles = [];
        renderFileList();
      } else if (data.error) {
        throw new Error(data.error);
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
      console.error('Error sending message:', error);
      showFeedback(error.message || 'Failed to send message', 'error');
      // Restore message on failure
      messageInput.value = messageText;
      adjustTextareaHeight(messageInput);
    } finally {
      // Re-enable controls
      messageInput.disabled = false;
      sendButton.disabled = false;
      sendButton.innerHTML = originalButtonText;
      removeTypingIndicator();
      messageInput.focus();
    }
  }

  function handleSendButtonClick(e) {
    e.preventDefault();
    if (!sendButton.disabled) {
      sendMessage().catch(error => {
        console.error('Error in sendMessage:', error);
        showFeedback('Failed to send message', 'error');
      });
    }
  }

  function handleMessageInput() {
    adjustTextareaHeight(this);
  }

  function handleMessageKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey && !sendButton.disabled) {
      e.preventDefault();
      sendMessage().catch(error => {
        console.error('Error on Enter key:', error);
        showFeedback('Failed to send message', 'error');
      });
    }
  }

  async function editChatTitle(chatId) {
    const newTitle = prompt('Enter new chat title:');
    if (!newTitle) return;

    if (newTitle.length > 100) {
      showFeedback('Title must be under 100 characters', 'error');
      return;
    }

    try {
      const response = await fetchWithCSRF(`/chat/update_chat_title/${chatId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Chat-ID': window.CHAT_CONFIG.chatId,
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ title: newTitle.trim() })
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

  async function deleteChat(chatId) {
    if (confirm('Are you sure you want to delete this chat?')) {
      try {
        const response = await fetchWithCSRF(`/chat/delete_chat/${chatId}`, {
          method: 'DELETE',
          headers: {
            'X-Chat-ID': window.CHAT_CONFIG.chatId,
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
    if (!message || typeof message !== 'string') {
      console.error('Invalid message content.');
      return;
    }

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
    } else {
      console.error('Content div not found in assistant message');
    }

    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function handleFileSelect(event) {
    try {
      if (!event.target.files) {
        showFeedback('No files selected', 'error');
        return;
      }
      const files = Array.from(event.target.files);
      if (files.length === 0) {
        showFeedback('No files selected', 'error');
        return;
      }
      processFiles(files);
    } catch (error) {
      console.error('Error handling file selection:', error);
      showFeedback('Failed to process selected files', 'error');
    } finally {
      // Reset file input to allow selecting the same file again
      event.target.value = '';
    }
  }

  function processFiles(files) {
    const validFiles = [];
    const errors = [];
    const totalSize = uploadedFiles.reduce((sum, file) => sum + file.size, 0);

    for (const file of files) {
      // Check file type
      if (!ALLOWED_FILE_TYPES.includes(file.type)) {
        errors.push(`${file.name}: Unsupported file type. Allowed types: ${ALLOWED_FILE_TYPES.join(', ')}`);
        continue;
      }

      // Check individual file size
      if (file.size > MAX_FILE_SIZE) {
        errors.push(`${file.name}: File too large (max ${MAX_FILE_SIZE / 1024 / 1024}MB)`);
        continue;
      }

      // Check total size limit
      if (totalSize + file.size > MAX_FILE_SIZE * MAX_FILES) {
        errors.push(`${file.name}: Would exceed total size limit of ${MAX_FILES * MAX_FILE_SIZE / 1024 / 1024}MB`);
        continue;
      }

      // Check file count limit
      if (uploadedFiles.length + validFiles.length >= MAX_FILES) {
        errors.push(`${file.name}: Maximum number of files (${MAX_FILES}) reached`);
        continue;
      }

      // Validate file is not empty
      if (file.size === 0) {
        errors.push(`${file.name}: File is empty`);
        continue;
      }

      validFiles.push(file);
    }

    if (errors.length > 0) {
      showFeedback(errors.join('\n'), 'error', { duration: 10000 }); // Show errors longer
    }

    if (validFiles.length > 0) {
      uploadedFiles = uploadedFiles.concat(validFiles);
      renderFileList();
      showFeedback(
        `${validFiles.length} file(s) ready to upload. Total size: ${
          (uploadedFiles.reduce((sum, file) => sum + file.size, 0) / 1024 / 1024).toFixed(1)
        }MB`,
        'success'
      );
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
    if (indicator && indicator.parentNode) {
      indicator.parentNode.removeChild(indicator);
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
    if (indicator && indicator.parentNode) {
      indicator.parentNode.removeChild(indicator);
    } else {
      console.warn('Typing indicator element not found or already removed.');
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
        processFiles(files);
      } catch (error) {
        console.error('Error handling file drop:', error);
        showFeedback('Failed to process dropped files', 'error');
      }
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
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      if (data.success && data.chat_id) {
        window.location.href = `/chat/chat_interface?chat_id=${data.chat_id}`;
      } else {
        throw new Error(data.error || 'Failed to create new chat: Invalid response');
      }
    } catch (error) {
      console.error('Error creating new chat:', error);
      showFeedback(error.message || 'Failed to create new chat', 'error');
      // Re-enable the button if it was disabled
      if (newChatBtn) {
        newChatBtn.disabled = false;
      }
    }
  }

  async function handleModelChange() {
    if (!modelSelect) return;

    const modelId = modelSelect.value;
    const originalValue = modelSelect.dataset.originalValue;

    try {
      const response = await fetchWithCSRF('/chat/update_model', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Chat-ID': window.CHAT_CONFIG.chatId,
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ model_id: modelId })
      });

      if (response.success) {
        localStorage.setItem('selectedModel', modelId);
        modelSelect.dataset.originalValue = modelId;
        showFeedback('Model updated successfully', 'success');
      } else {
        throw new Error(response.error || 'Failed to update model');
      }
    } catch (error) {
      console.error('Error updating model:', error);
      showFeedback(error.message || 'Failed to update model', 'error');
      // Restore original value on error
      if (originalValue && modelSelect) {
        modelSelect.value = originalValue;
      }
    }
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
        headers: {
          'X-Chat-ID': window.CHAT_CONFIG.chatId,
          'X-Requested-With': 'XMLHttpRequest'
        }
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

  function getCSRFToken() {
    const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
    return csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute('content') : '';
  }

  // Expose necessary functions to global scope
  window.editChatTitle = editChatTitle;
  window.deleteChat = deleteChat;
  window.removeFile = removeFile;
})();
