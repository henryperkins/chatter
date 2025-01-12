(function () {
  // Create a unique instance ID for this initialization
  const instanceId = Date.now();

  function init() {
    // Verify dependencies
    if (!window.utils || !window.md || !window.DOMPurify || !window.Prism) {
      console.error('Required dependencies not loaded');
      return;
    }

    // Access utility functions and dependencies
    const { showFeedback, fetchWithCSRF } = window.utils;
    const DOMPurify = window.DOMPurify;
    const Prism = window.Prism;
    const md = window.md;

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
      try {
        console.debug('Initializing chat interface...');

        // Use instance-specific initialization flag
        const initKey = `chat_initialized_${instanceId}`;
        if (window[initKey]) {
          console.debug('Chat already initialized for this instance, skipping');
          return;
        }
        window[initKey] = true;

        // Cache and verify DOM elements
        console.debug('Caching DOM elements...');
        const requiredElements = {
          'message-input': el => {
            console.debug('Found message-input');
            messageInput = el;
          },
          'send-button': el => {
            console.debug('Found send-button');
            sendButton = el;
          },
          'chat-box': el => {
            console.debug('Found chat-box');
            chatBox = el;
          }
        };

        const optionalElements = {
          'file-input': el => fileInput = el,
          'upload-button': el => uploadButton = el,
          'uploaded-files': el => uploadedFilesDiv = el,
          'model-select': el => modelSelect = el,
          'new-chat-btn': el => newChatBtn = el,
          'drop-zone': el => dropZone = el,
          'edit-title-btn': el => el.addEventListener('click', () => {
            const chatId = window.CHAT_CONFIG?.chatId;
            if (chatId) {
              editChatTitle(chatId);
            } else {
              showFeedback('Chat ID not found', 'error');
            }
          })
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
            console.debug(`Element #${id} initialized`);
          }
        }

        if (missingElements) {
          showFeedback('Critical UI elements are missing. Please reload the page.', 'error');
          return;
        }

        // Set optional elements if they exist
        console.debug('Setting up optional elements...');
        for (const [id, setter] of Object.entries(optionalElements)) {
          const element = document.getElementById(id);
          if (element) {
            console.debug(`Found optional element: ${id}`);
            setter(element);
          } else {
            console.debug(`Optional element not found: ${id}`);
          }
        }

        // Initialize chat box for accessibility
        if (chatBox) {
          chatBox.setAttribute('role', 'log');
          chatBox.setAttribute('aria-live', 'polite');
          chatBox.setAttribute('aria-label', 'Chat messages');
        }

        // Mobile-specific setup
        if (window.innerWidth < 768) {
          // Adjust textarea height for mobile
          messageInput.style.minHeight = '2.5rem';
          messageInput.style.maxHeight = '6rem';

          // Handle mobile menu
          const sidebar = document.getElementById('sidebar');
          const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
          const backdrop = document.createElement('div');
          backdrop.id = 'sidebar-backdrop';
          backdrop.className = 'fixed inset-0 bg-black bg-opacity-50 z-modal-backdrop hidden transition-opacity duration-300 ease-in-out opacity-0';
          backdrop.setAttribute('aria-hidden', 'true');
          document.body.appendChild(backdrop);

          if (sidebar && mobileMenuToggle) {
            sidebar.classList.add('-translate-x-full');

            mobileMenuToggle.addEventListener('click', () => {
              sidebar.classList.remove('-translate-x-full');
              backdrop.classList.remove('hidden');
              requestAnimationFrame(() => {
                backdrop.classList.remove('opacity-0');
              });
              sidebar.setAttribute('aria-expanded', 'true');
            });

            backdrop.addEventListener('click', () => {
              sidebar.classList.add('-translate-x-full');
              backdrop.classList.add('opacity-0');
              setTimeout(() => {
                backdrop.classList.add('hidden');
              }, 300);
              sidebar.setAttribute('aria-expanded', 'false');
            });

            // Add keyboard navigation
            document.addEventListener('keydown', (e) => {
              if (e.key === 'Escape' && !sidebar.classList.contains('-translate-x-full')) {
                backdrop.click();
              }
            });
          }
        }

        // Set up file handling
        console.debug('Setting up file handling...');
        if (fileInput && uploadButton) {
          console.debug('Attaching file input handlers');
          uploadButton.addEventListener('click', () => {
            console.debug('Upload button clicked');
            fileInput.click();
          });
          fileInput.addEventListener('change', handleFileSelect);
        } else {
          console.debug('File input elements not found');
        }

        // Set up additional handlers
        console.debug('Setting up additional handlers...');
        if (newChatBtn) {
          console.debug('Attaching new chat button handler');
          newChatBtn.addEventListener('click', createNewChat);
        }
        if (modelSelect) {
          console.debug('Attaching model select handler');
          modelSelect.addEventListener('change', handleModelChange);
          
          // Set up edit model button handler
          const editModelBtn = document.getElementById('edit-model-btn');
          if (editModelBtn) {
            editModelBtn.addEventListener('click', () => {
              const selectedModelId = modelSelect.value;
              if (selectedModelId) {
                const baseEditUrl = window.CHAT_CONFIG.editModelUrl;
                const editUrl = baseEditUrl.replace('/0', `/${selectedModelId}`);
                window.location.href = editUrl;
              } else {
                showFeedback('No model selected', 'error');
              }
            });
          }
        }
        if (chatBox) {
          console.debug('Attaching chat box message action handlers');
          chatBox.addEventListener('click', handleMessageActions);
        }

        // Set up delete chat buttons
        console.debug('Setting up delete chat buttons...');
        const deleteButtons = document.querySelectorAll('.delete-chat-btn');
        console.debug(`Found ${deleteButtons.length} delete buttons`);
        deleteButtons.forEach(btn => {
          const chatId = btn.dataset.chatId;
          console.debug(`Setting up delete button for chat ${chatId}`);
          btn.addEventListener('click', () => {
            console.debug(`Delete button clicked for chat ${chatId}`);
            if (chatId) {
              deleteChat(chatId);
            } else {
              showFeedback('Chat ID not found', 'error');
            }
          });
        });

        // Set up core event listeners
        console.debug('Setting up core event listeners...');

        // Set up core event listeners
        console.debug('Attaching send button click handler');
        sendButton.addEventListener('click', handleSendButtonClick);
        console.debug('Attaching message input handlers');
        messageInput.addEventListener('input', handleMessageInput);
        messageInput.addEventListener('keydown', handleMessageKeydown);

        // Add touch event listeners for mobile
        if ('ontouchstart' in window) {
          console.debug('Setting up mobile touch handlers');
          messageInput.addEventListener('touchstart', handleMessageInput);
          sendButton.addEventListener('touchend', handleSendButtonClick);
        }

        // Initialize UI
        setupDragAndDrop();
        adjustTextareaHeight(messageInput);

        console.debug('Chat initialization completed successfully');
      } catch (error) {
        console.error('Error initializing chat:', error);
        showFeedback('Failed to initialize chat interface', 'error');
      }
    }

    // Initialize chat interface
    initializeChat();

    async function sendMessage() {
      console.debug('sendMessage called');
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
      sendButton.innerHTML = '<span class="animate-spin" aria-hidden="true">↻</span> <span class="sr-only">Sending...</span>';

      try {
        // Prepare form data
        const formData = new FormData();
        formData.append('message', messageText);
        uploadedFiles.forEach(file => formData.append('files[]', file));

        // Add CSRF token to FormData
        formData.append('csrf_token', utils.getCSRFToken());

        // Update UI immediately
        appendUserMessage(messageText);
        messageInput.value = '';
        adjustTextareaHeight(messageInput);
        showTypingIndicator();

        // Send request
        const chatId = window.CHAT_CONFIG?.chatId;
        console.debug('Using chat ID:', chatId);
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
      console.debug('Send button clicked');
      e.preventDefault();
      if (!sendButton.disabled) {
        console.debug('Send button not disabled, proceeding with send');
        sendMessage().catch(error => {
          console.error('Error in sendMessage:', error);
          showFeedback('Failed to send message', 'error');
        });
      } else {
        console.debug('Send button is disabled, ignoring click');
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
      try {
        const newTitle = prompt('Enter new chat title:');
        if (!newTitle) return;

        if (newTitle.length > 100) {
          showFeedback('Title must be under 100 characters', 'error');
          return;
        }

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
      try {
        if (!confirm('Are you sure you want to delete this chat?')) {
          return;
        }

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

    function appendUserMessage(message) {
      console.debug('Appending user message:', message);
      const messageDiv = document.createElement('div');
      messageDiv.className = 'flex w-full mt-2 space-x-3 max-w-2xl ml-auto justify-end';
      messageDiv.setAttribute('role', 'listitem');
      messageDiv.innerHTML = `
        <div>
          <div class="relative bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
            <p class="text-sm break-words overflow-x-auto">${escapeHtml(message)}</p>
          </div>
          <span class="text-xs text-gray-500 dark:text-gray-400 leading-none">${new Date().toLocaleTimeString()}</span>
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
      messageDiv.className = 'flex w-full mt-2 space-x-3 max-w-3xl';
      messageDiv.setAttribute('role', 'listitem');
      messageDiv.innerHTML = `
        <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700" role="img" aria-label="Assistant avatar"></div>
        <div class="relative max-w-3xl">
          <div class="bg-gray-100 dark:bg-gray-800 p-3 rounded-r-lg rounded-bl-lg">
            <div class="prose dark:prose-invert prose-sm max-w-none overflow-x-auto"></div>
          </div>
          <div class="absolute right-0 top-0 flex space-x-2">
            <button class="copy-button p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-200"
                    title="Copy to clipboard" aria-label="Copy message to clipboard">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"/>
              </svg>
            </button>
            <button class="regenerate-button p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                    title="Regenerate response">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
              </svg>
            </button>
          </div>
          <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
            ${new Date().toLocaleTimeString()}
          </span>
        </div>
      `;

      const contentDiv = messageDiv.querySelector('.prose');
      if (contentDiv) {
        try {
          const renderedHtml = md.render(message);
          const sanitizedHtml = DOMPurify.sanitize(renderedHtml, {
            ALLOWED_TAGS: [
              'b', 'i', 'em', 'strong', 'a', 'p', 'blockquote', 'code', 'pre',
              'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br',
              'hr', 'span', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
            ],
            ALLOWED_ATTR: ['href', 'src', 'alt', 'class', 'aria-label', 'role']
          });
          contentDiv.innerHTML = sanitizedHtml;
          Prism.highlightAllUnder(contentDiv);

          // Make code blocks accessible
          contentDiv.querySelectorAll('pre').forEach(pre => {
            pre.setAttribute('role', 'region');
            pre.setAttribute('aria-label', 'Code block');
            pre.tabIndex = 0;
          });
        } catch (error) {
          console.error('Error rendering markdown:', error);
          contentDiv.innerHTML = `<pre>${DOMPurify.sanitize(message)}</pre>`;
        }
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
          <button class="text-red-500 hover:text-red-700 transition-colors duration-200"
                  data-index="${index}"
                  aria-label="Remove ${escapeHtml(file.name)}">
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
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
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
          const content = target.closest('.max-w-3xl').querySelector('.prose').textContent;
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

    // Expose necessary functions to global scope
    window.editChatTitle = editChatTitle;
    window.deleteChat = deleteChat;
    window.removeFile = removeFile;
  }

  // Initialize either when DOM is ready or immediately if already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
