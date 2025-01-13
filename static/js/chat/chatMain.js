// chatMain.js
// The primary entry point that initializes chat UI, sets up events, etc.

import { showFeedback, fetchWithCSRF, debounce } from '../utils.js'; // or your path
import { instanceId } from './chatState.js';
import { adjustTextareaHeight, setupScrollObserver } from './chatUI.js';
import { processFiles } from './chatFiles.js';
import {
  sendMessage,
  editChatTitle,
  deleteChat,
  regenerateResponse
} from './chatMessages.js';

/**
 * Initializes the chat interface with comprehensive setup and event handling.
 * 
 * @description
 * This function sets up the entire chat interface, ensuring proper initialization
 * only occurs once per instance. It configures DOM elements, event listeners,
 * file handling, message sending, and various interactive features.
 * 
 * @throws {Error} If critical UI elements are missing or initialization fails
 * 
 * @remarks
 * - Prevents multiple initializations using a unique instance key
 * - Sets up textarea constraints and dynamic height adjustment
 * - Configures scroll and resize observers
 * - Handles message sending via Enter key and send button
 * - Manages file uploads and drag-and-drop functionality
 * - Sets up event listeners for chat actions like copying and regenerating messages
 * - Prepares mobile layout and cleanup mechanisms
 * 
 * @example
 * // Typically called when the DOM is fully loaded
 * document.addEventListener('DOMContentLoaded', initializeChat);
 */
function initializeChat() {
  console.debug('Initializing chat interface...');

  // Avoid multiple init
  const initKey = `chat_initialized_${instanceId}`;
  if (window[initKey]) {
    console.debug('Chat already initialized for this instance, skipping');
    return;
  }
  window[initKey] = true;

  // Required DOM elements
  const messageInput = document.getElementById('message-input');
  const sendButton   = document.getElementById('send-button');
  const chatBox      = document.getElementById('chat-box');

  if (!messageInput || !sendButton || !chatBox) {
    console.error('Required elements not found');
    showFeedback('Critical UI elements are missing. Please reload the page.', 'error');
    return;
  }

  // Setup text area constraints
  messageInput.style.minHeight = '2.5rem';
  messageInput.style.maxHeight = window.innerWidth < 768 ? '6rem' : '12rem';
  adjustTextareaHeight(messageInput);

  // Observe chat scroll
  setupScrollObserver(chatBox);

  // Observe textarea resizing
  const resizeObserver = new ResizeObserver(() => {
    adjustTextareaHeight(messageInput);
  });
  resizeObserver.observe(messageInput);

  // Attach event: typing in message box
  messageInput.addEventListener('input', debounce(() => {
    adjustTextareaHeight(messageInput);
  }, 100));

  // Press Enter to send
  messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !sendButton.disabled) {
      e.preventDefault();
      sendMessage(messageInput, sendButton, chatBox);
    }
  });

  // Send button
  sendButton.addEventListener('click', (e) => {
    e.preventDefault();
    if (!sendButton.disabled) {
      sendMessage(messageInput, sendButton, chatBox);
    }
  }, { passive: true });

  // Handle file input
  const fileInput = document.getElementById('file-input');
  const uploadButton = document.getElementById('upload-button');
  if (fileInput && uploadButton) {
    uploadButton.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      try {
        if (!e.target.files) {
          showFeedback('No files selected', 'error');
          return;
        }
        const files = Array.from(e.target.files);
        processFiles(files);
      } catch (error) {
        console.error('Error selecting files:', error);
        showFeedback('Failed to process files', 'error');
      } finally {
        e.target.value = '';
      }
    });
  }

  // "New Chat" button
  const newChatBtn = document.getElementById('new-chat-btn');
  if (newChatBtn) {
    newChatBtn.addEventListener('click', createNewChat);
  }

  // Model select changes
  const modelSelect = document.getElementById('model-select');
  if (modelSelect) {
    modelSelect.addEventListener('change', handleModelChange);
  }

  // Handle message actions (copy/regenerate)
  chatBox.addEventListener('click', async (event) => {
    const target = event.target.closest('button');
    if (!target) return;

    try {
      if (target.classList.contains('copy-button')) {
        // Copy text content
        const content = target.closest('.max-w-3xl').querySelector('.prose').textContent;
        await navigator.clipboard.writeText(content);
        showFeedback('Copied to clipboard!', 'success');
      } else if (target.classList.contains('regenerate-button')) {
        // Regenerate
        await regenerateResponse(target, chatBox);
      }
    } catch (error) {
      console.error('Error in chatBox click handler:', error);
      showFeedback('Failed to perform action', 'error');
    }
  });

  // Setup chat deletion buttons
  setupDeleteButtons();

  // Setup drag & drop
  setupDragAndDrop();

  // Mobile layout adjustments
  setupMobileLayout();

  // Cleanup on page unload
  window.addEventListener('beforeunload', cleanup);

  console.debug('Chat initialization completed successfully');
}

/**
 * Sets up event listeners for delete chat buttons across the interface.
 * 
 * @description Finds all elements with the '.delete-chat-btn' class and attaches click event listeners
 * that trigger the deletion of a specific chat by its unique identifier.
 * 
 * @remarks
 * - Iterates through all delete buttons in the document
 * - Retrieves the unique chat ID from the button's data attribute
 * - Adds a click event listener that calls the global `deleteChat` function with the specific chat ID
 * 
 * @throws {Error} Silently handles cases where a delete button lacks a valid chat ID
 */
function setupDeleteButtons() {
  const deleteButtons = document.querySelectorAll('.delete-chat-btn');
  deleteButtons.forEach(btn => {
    const chatId = btn.dataset.chatId;
    if (chatId) {
      btn.addEventListener('click', () => deleteChat(chatId));
    }
  });
}

/**
 * Sets up drag and drop functionality for file uploads in the chat interface.
 * 
 * @description
 * Configures a drop zone for file uploads with event listeners to handle:
 * - Preventing default drag and drop behaviors
 * - Showing/hiding the drop zone during drag events
 * - Processing dropped files
 * 
 * @throws {Error} If file processing encounters an unexpected issue
 * 
 * @example
 * // Automatically called during chat interface initialization
 * setupDragAndDrop();
 * 
 * @remarks
 * - Requires a DOM element with id 'drop-zone'
 * - Uses `showFeedback()` for user notifications
 * - Supports multiple file drops
 */
function setupDragAndDrop() {
  const dropZone = document.getElementById('drop-zone');
  if (!dropZone) return;

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
  });

  dropZone.addEventListener('dragenter', () => {
    dropZone.classList.remove('hidden');
  });

  dropZone.addEventListener('dragleave', (e) => {
    // Hide if you leave the drop zone
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

/**
 * Prevents the default event behavior and stops event propagation.
 * 
 * @param {Event} e - The event object to prevent default actions for.
 * @description Stops the browser's default event handling and prevents the event from bubbling up the DOM tree.
 * Commonly used in event handlers to prevent unwanted default behaviors like form submissions or link navigation.
 */
function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

/**
 * Creates a new chat by sending a POST request to the server.
 * 
 * @async
 * @throws {Error} Throws an error if the chat creation fails or the server returns an error.
 * @returns {Promise<void>} Redirects to the new chat interface if successful.
 * 
 * @description
 * This function sends a request to create a new chat. On successful creation, it automatically
 * redirects the user to the new chat interface. If an error occurs during chat creation,
 * it displays an error feedback message and re-enables the new chat button.
 * 
 * @example
 * // Typically called when a user clicks a "New Chat" button
 * document.getElementById('new-chat-btn').addEventListener('click', createNewChat);
 */
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
      throw new Error(data.error || 'Failed to create new chat: Unknown error.');
    }
  } catch (error) {
    console.error('Error creating new chat:', error);
    showFeedback(error.message || 'Failed to create new chat', 'error');
    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) {
      newChatBtn.disabled = false;
    }
  }
}

/**
 * Handles changing the chat model via dropdown selection.
 * 
 * @async
 * @description Updates the current chat's model on the server and manages UI feedback.
 * Persists the selected model in local storage and handles potential errors gracefully.
 * 
 * @throws {Error} Throws an error if the model update request fails
 * 
 * @returns {Promise<void>}
 * 
 * @example
 * // Triggered when user selects a new model from the dropdown
 * document.getElementById('model-select').addEventListener('change', handleModelChange);
 */
async function handleModelChange() {
  const modelSelect = document.getElementById('model-select');
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
    if (originalValue) {
      modelSelect.value = originalValue;
    }
  }
}

/**
 * Removes event listeners from message input and send button to prevent memory leaks.
 * 
 * @description Safely removes event listeners attached to the message input and send button
 * during the chat interface initialization. This helps prevent potential memory leaks and
 * ensures clean page unloading.
 * 
 * @throws {Error} Logs and captures any errors that occur during the cleanup process.
 * 
 * @example
 * // Typically called automatically on page unload
 * window.addEventListener('unload', cleanup);
 */
function cleanup() {
  try {
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    if (messageInput) {
      messageInput.removeEventListener('input', () => {});
      messageInput.removeEventListener('keydown', () => {});
    }
    if (sendButton) {
      sendButton.removeEventListener('click', () => {});
      sendButton.removeEventListener('touchend', () => {});
    }
    console.debug('Chat cleanup completed successfully');
  } catch (error) {
    console.error('Error during cleanup:', error);
  }
}

// Initialize as soon as DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeChat);
} else {
  initializeChat();
}

// Optionally expose some functions globally (e.g., for inline onclick handlers)
window.editChatTitle = (chatId) =>
  import('./chatMessages.js').then(m => m.editChatTitle(chatId));
window.deleteChat = (chatId) =>
  import('./chatMessages.js').then(m => m.deleteChat(chatId));
window.removeFile = (index) =>
  import('./chatFiles.js').then(m => m.removeFile(index));
