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
 * Orchestrates chat initialization
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
 * Binds "delete chat" buttons
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
 * Sets up drag & drop for file uploads
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

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

/**
 * Creates a new chat on server
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
 * Handles model changes in the dropdown
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
 * Cleanup routine on page unload
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
