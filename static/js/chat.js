(function () {
  // Create a unique instance ID for this initialization
  const instanceId = Date.now();

  function init() {
    // Verify dependencies
    if (!window.utils || !window.md || !window.DOMPurify || !window.Prism) {
      console.error('Required dependencies not loaded');
      return;
    }

    function initializeMobileMenu() {
        const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        const mobileMenu = document.getElementById('mobile-menu');
        const backdrop = document.getElementById('mobile-menu-backdrop');

        if (!mobileMenuToggle || !mobileMenu || !backdrop) {
            console.error('Mobile menu elements not found');
            return;
        }

        // Function to close menu
        const closeMenu = () => {
            mobileMenu.classList.add('-translate-x-full');
            backdrop.classList.add('hidden');
            document.body.classList.remove('overflow-hidden');
            mobileMenuToggle.setAttribute('aria-expanded', 'false');
        };

        // Function to open menu
        const openMenu = () => {
            mobileMenu.classList.remove('-translate-x-full');
            backdrop.classList.remove('hidden');
            document.body.classList.add('overflow-hidden');
            mobileMenuToggle.setAttribute('aria-expanded', 'true');
        };

        // Toggle menu
        mobileMenuToggle.addEventListener('click', () => {
            const isExpanded = mobileMenuToggle.getAttribute('aria-expanded') === 'true';
            if (isExpanded) {
                closeMenu();
            } else {
                openMenu();
            }
        });

        // Close menu when clicking backdrop
        backdrop.addEventListener('click', closeMenu);

        // Close menu when clicking a chat link on mobile
        const chatLinks = mobileMenu.querySelectorAll('a[href*="chat_interface"]');
        chatLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 768) { // Only on mobile
                    closeMenu();
                }
            });
        });

        // Close menu on window resize if switching to desktop
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768) {
                mobileMenu.classList.remove('-translate-x-full');
                backdrop.classList.add('hidden');
                document.body.classList.remove('overflow-hidden');
            } else {
                mobileMenu.classList.add('-translate-x-full');
            }
        });

        // Handle escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !mobileMenu.classList.contains('-translate-x-full')) {
                closeMenu();
            }
        });
    }

    // Initialize mobile menu
    initializeMobileMenu();

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
        const requiredElements = {
          'message-input': el => {
            messageInput = el;
            // Optimize textarea behavior
            el.style.minHeight = '2.5rem';
            el.style.maxHeight = window.innerWidth < 768 ? '6rem' : '12rem';
            adjustTextareaHeight(el);
          },
          'send-button': el => {
            sendButton = el;
          },
          'chat-box': el => {
            chatBox = el;
            // Improve scrolling performance
            el.style.scrollBehavior = 'smooth';
            // Add intersection observer for lazy loading
            setupScrollObserver(el);
          }
        };

        // Verify required elements exist
        let missingElements = false;
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
        const optionalElements = {
          'file-input': el => fileInput = el,
          'upload-button': el => uploadButton = el,
          'uploaded-files': el => uploadedFilesDiv = el,
          'model-select': el => modelSelect = el,
          'new-chat-btn': el => newChatBtn = el,
          'drop-zone': el => dropZone = el
        };

        Object.entries(optionalElements).forEach(([id, setter]) => {
          const element = document.getElementById(id);
          if (element) setter(element);
        });

        // Add resize observer for message input
        const resizeObserver = new ResizeObserver(() => {
          if (messageInput) {
            adjustTextareaHeight(messageInput);
          }
        });

        if (messageInput) {
          resizeObserver.observe(messageInput);
        }

        // Optimize event listeners
        const eventHandlers = {
          'message-input': {
            'input': debounce(handleMessageInput, 100),
            'keydown': handleMessageKeydown
          },
          'send-button': {
            'click': handleSendButtonClick,
            'touchend': handleSendButtonClick
          }
        };

        // Attach optimized event listeners
        Object.entries(eventHandlers).forEach(([elementId, handlers]) => {
          const element = document.getElementById(elementId);
          if (element) {
            Object.entries(handlers).forEach(([event, handler]) => {
              element.addEventListener(event, handler, event === 'input' ? { passive: true } : false);
            });
          }
        });

        // Mobile-specific optimizations
        if (window.innerWidth < 768) {
          setupMobileLayout();
        }

        // Set up file handling
        if (fileInput && uploadButton) {
          setupFileHandling();
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

        // Set up delete chat buttons
        setupDeleteButtons();

        function setupModelButtons() {
            // Edit Model Button
            const editModelBtn = document.getElementById('edit-model-btn');
            if (editModelBtn) {
                editModelBtn.addEventListener('click', () => {
                    const modelSelect = document.getElementById('model-select');
                    const modelId = modelSelect?.value;
                    if (modelId) {
                        window.location.href = `${window.CHAT_CONFIG.editModelUrl}${modelId}`;
                    } else {
                        showFeedback('No model selected', 'error');
                    }
                });
            }

            // Add Model Button
            const addModelLink = document.querySelector('a[href*="add-model"]');
            if (addModelLink) {
                addModelLink.addEventListener('click', (e) => {
                    e.preventDefault();
                    window.location.href = '/model/add-model';
                });
            }

            // New Chat Button
            const newChatBtn = document.getElementById('new-chat-btn');
            if (newChatBtn) {
                newChatBtn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    try {
                        newChatBtn.disabled = true;
                        const response = await fetchWithCSRF('/chat/new_chat', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest'
                            }
                        });

                        if (response.success && response.chat_id) {
                            window.location.href = `/chat/chat_interface?chat_id=${response.chat_id}`;
                        } else {
                            throw new Error(response.error || 'Failed to create new chat');
                        }
                    } catch (error) {
                        console.error('Error creating new chat:', error);
                        showFeedback(error.message || 'Failed to create new chat', 'error');
                    } finally {
                        newChatBtn.disabled = false;
                    }
                });
            }
        }

        // Call the setup function
        setupModelButtons();

        // Set up drag and drop
        setupDragAndDrop();

        // Cleanup on page unload
        window.addEventListener('beforeunload', cleanup);

        console.debug('Chat initialization completed successfully');
      } catch (error) {
        console.error('Error initializing chat:', error);
        showFeedback('Failed to initialize chat interface', 'error');
      }
    }

    function setupMobileLayout() {
      // Adjust textarea for mobile
      if (messageInput) {
        messageInput.style.fontSize = '16px'; // Prevent zoom on iOS
      }
    }

    function setupScrollObserver(chatBox) {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              entry.target.classList.add('visible');
            }
          });
        },
        { root: chatBox, threshold: 0.1 }
      );

      // Observe message elements
      chatBox.querySelectorAll('.message').forEach(message => {
        observer.observe(message);
      });
    }

    function setupFileHandling() {
      uploadButton.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', handleFileSelect);
    }

    function setupDeleteButtons() {
      const deleteButtons = document.querySelectorAll('.delete-chat-btn');
      deleteButtons.forEach(btn => {
        const chatId = btn.dataset.chatId;
        if (chatId) {
          btn.addEventListener('click', () => deleteChat(chatId));
        }
      });
    }

    function debounce(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    }

    function cleanup() {
      try {
        // Remove event listeners
        if (messageInput) {
          messageInput.removeEventListener('input', handleMessageInput);
          messageInput.removeEventListener('keydown', handleMessageKeydown);
        }
        if (sendButton) {
          sendButton.removeEventListener('click', handleSendButtonClick);
          sendButton.removeEventListener('touchend', handleSendButtonClick);
        }
        console.debug('Chat cleanup completed successfully');
      } catch (error) {
        console.error('Error during cleanup:', error);
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

        // Update UI immediately
        appendUserMessage(messageText);
        messageInput.value = '';
        adjustTextareaHeight(messageInput);
        showTypingIndicator();

        // Get model info
        const modelSelect = document.getElementById('model-select');
        const modelId = modelSelect?.value;
        const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
        const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

        // Send request
        const chatId = window.CHAT_CONFIG?.chatId;
        console.debug('Using chat ID:', chatId);

        let responseData;

        if (useStreaming) {
          const response = await fetchWithCSRF('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
              'X-Chat-ID': chatId,
              'Accept': 'text/event-stream',
              'X-Requested-With': 'XMLHttpRequest'
            }
          });

          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let accumulatedResponse = '';

          while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const streamData = line.slice(6);
                if (streamData === '[DONE]') break;
                accumulatedResponse += streamData;
                appendAssistantMessage(accumulatedResponse, true);
              }
            }
          }

          // Final update with complete response
          appendAssistantMessage(accumulatedResponse, false);
          responseData = { response: accumulatedResponse };
        } else {
          responseData = await fetchWithCSRF('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
              'X-Chat-ID': chatId,
              'X-Requested-With': 'XMLHttpRequest'
            }
          });

          // Handle response
          if (responseData.response) {
            appendAssistantMessage(responseData.response);
          } else if (responseData.error) {
            throw new Error(responseData.error);
          } else {
            throw new Error('No response received from server');
          }
        }

        // Clean up after successful response
        uploadedFiles = [];
        renderFileList();

        // Handle any excluded files
        if (Array.isArray(responseData?.excluded_files)) {
          responseData.excluded_files.forEach(file => {
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
      console.debug('Send button clicked');
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

    function handleMessageInput(e) {
      if (e.type === 'touchstart') {
        // e.preventDefault(); // Removed to allow default touch behavior
      }
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
        // Enhanced confirmation dialog
        if (!confirm('Are you sure you want to delete this chat? This action cannot be undone.')) {
          return;
        }
    
        // Show loading state on the delete button
        const deleteBtn = document.querySelector(`button[data-chat-id="${chatId}"]`);
        if (deleteBtn) {
          deleteBtn.disabled = true;
          deleteBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
    
        const response = await fetchWithCSRF(`/chat/delete_chat/${chatId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
            'X-Chat-ID': chatId,
            'X-Requested-With': 'XMLHttpRequest'
          }
        });
    
        if (response.success) {
          // If deleting current chat, redirect to new chat
          if (chatId === window.CHAT_CONFIG.chatId) {
            window.location.href = '/chat/chat_interface';
            return;
          }
          
          // Otherwise just remove the chat from sidebar
          const chatElement = document.querySelector(`[data-chat-id="${chatId}"]`).closest('.group');
          chatElement.remove();
          
          showFeedback('Chat deleted successfully', 'success');
        } else {
          throw new Error(response.error || 'Failed to delete chat');
        }
      } catch (error) {
        console.error('Error deleting chat:', error);
        showFeedback(error.message || 'Failed to delete chat', 'error');
      } finally {
        // Reset delete button state if it exists
        const deleteBtn = document.querySelector(`button[data-chat-id="${chatId}"]`);
        if (deleteBtn) {
          deleteBtn.disabled = false;
          deleteBtn.innerHTML = '<i class="fas fa-trash-alt text-lg"></i>';
        }
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

    /**
     * Appends a message from the assistant to the chat box.
     * If the message is streaming, it updates the last message instead of creating a new one.
     * @param {string} message - The message content to append.
     * @param {boolean} [isStreaming=false] - Whether the message is part of a streaming response.
     */
    function appendAssistantMessage(message, isStreaming = false) {
      if (!message || typeof message !== 'string') {
        console.error('Invalid message content.');
        return;
      }

      // For streaming updates, update the last message instead of creating a new one
      let messageDiv;
      let contentDiv;

      if (isStreaming && chatBox.lastElementChild) {
        messageDiv = chatBox.lastElementChild;
        contentDiv = messageDiv.querySelector('.prose');
        if (!contentDiv) {
          console.error('Content div not found in existing message');
          return;
        }
      } else {
        messageDiv = document.createElement('div');
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
                <i class="fas fa-copy"></i>
              </button>
              <button class="regenerate-button p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                      title="Regenerate response">
                <i class="fas fa-sync-alt"></i>
              </button>
            </div>
            <span class="text-xs text-gray-500 dark:text-gray-400 block mt-1">
              ${new Date().toLocaleTimeString()}
            </span>
          </div>
        `;
        contentDiv = messageDiv.querySelector('.prose');
      }

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

        // Only append the message div if it's not already in the chat box
        if (!isStreaming || !chatBox.lastElementChild) {
          chatBox.appendChild(messageDiv);
        }

        chatBox.scrollTop = chatBox.scrollHeight;
      } catch (error) {
        console.error('Error rendering markdown:', error);
        contentDiv.innerHTML = `<pre>${DOMPurify.sanitize(message)}</pre>`;
      }
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

    /**
     * Displays a typing indicator in the chat box to show that the assistant is typing.
     * This function creates a new div element with a typing animation and appends it to the chat box.
     * The typing indicator is removed when the assistant's response is complete.
     */
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

    let dragAndDropInitialized = false;

    function setupDragAndDrop() {
        if (dragAndDropInitialized) return;
        dragAndDropInitialized = true;
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
        } finally {
          dropZone.classList.add('hidden'); // Ensure dropZone is hidden after drop
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
  
      // Disable select while processing
      modelSelect.disabled = true;
  
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
              // Update model name in title
              const selectedOption = modelSelect.options[modelSelect.selectedIndex];
              const modelName = selectedOption.textContent;
              const chatTitle = document.getElementById('chat-title');
              if (chatTitle) {
                  const currentTitle = chatTitle.textContent.split('-')[0].trim();
                  chatTitle.textContent = `${currentTitle} - ${modelName}`;
              }
              
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
      } finally {
          modelSelect.disabled = false;
      }
  }

    async function handleMessageActions(event) {
      const target = event.target.closest('button');
      if (!target) return;

      try {
        if (target.classList.contains('copy-button')) {
          const rawContent = target.dataset.rawContent;
          const content = rawContent || target.closest('.max-w-3xl').querySelector('.prose').textContent;
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

        // Get model info for streaming
        const modelSelect = document.getElementById('model-select');
        const modelId = modelSelect?.value;
        const model = window.models?.find(m => m.id === parseInt(modelId));
        const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

        let responseData;

        if (useStreaming) {
          const response = await fetch('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
              'X-Chat-ID': window.CHAT_CONFIG.chatId,
              'X-CSRFToken': window.utils.getCSRFToken(),
              'Accept': 'text/event-stream',
              'X-Requested-With': 'XMLHttpRequest'
            }
          });

          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let accumulatedResponse = '';

          while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const streamData = line.slice(6);
                if (streamData === '[DONE]') break;
                accumulatedResponse += streamData;
                appendAssistantMessage(accumulatedResponse, true);
              }
            }
          }

          // Final update with complete response
          appendAssistantMessage(accumulatedResponse, false);
          responseData = { response: accumulatedResponse };
        } else {
          responseData = await fetchWithCSRF('/chat/', {
            method: 'POST',
            body: formData,
            headers: {
              'X-Chat-ID': window.CHAT_CONFIG.chatId,
              'X-Requested-With': 'XMLHttpRequest'
            }
          });

          if (responseData.response) {
            appendAssistantMessage(responseData.response);
          } else {
            throw new Error(responseData.error || 'Failed to regenerate response');
          }
        } // <-- This was the missing closing brace
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
