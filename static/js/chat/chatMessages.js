// chatMessages.js
// Sends messages (with or without streaming), regenerates responses, edits titles, etc.

import { showFeedback, fetchWithCSRF } from '../utils.js'; // or adjust path
import {
  instanceId,
  uploadedFiles,
  clearFiles,
  MAX_MESSAGE_LENGTH
} from './chatState.js';
import {
  appendUserMessage,
  appendAssistantMessage,
  showTypingIndicator,
  removeTypingIndicator
} from './chatUI.js';

/**
 * Sends a user message to the server with optional file uploads.
 * 
 * @param {HTMLInputElement} messageInput - The input element containing the user's message.
 * @param {HTMLButtonElement} sendButton - The button used to send the message.
 * @param {HTMLElement} chatBox - The container element for chat messages.
 * 
 * @description
 * Handles sending messages with the following features:
 * - Validates message length and presence of content
 * - Supports both streaming and non-streaming responses
 * - Manages file uploads
 * - Provides real-time UI feedback during message sending
 * - Handles errors and displays appropriate messages
 * 
 * @throws {Error} Throws an error if message sending fails due to network or server issues.
 * 
 * @example
 * sendMessage(messageInputElement, sendButtonElement, chatBoxElement);
 */
export async function sendMessage(messageInput, sendButton, chatBox) {
  console.debug('sendMessage called');

  const text = messageInput.value.trim();
  if (!text && uploadedFiles.length === 0) {
    showFeedback('Please enter a message or upload files.', 'error');
    return;
  }
  if (text.length > MAX_MESSAGE_LENGTH) {
    showFeedback(`Message too long. Max length is ${MAX_MESSAGE_LENGTH} characters.`, 'error');
    return;
  }

  const originalButtonText = sendButton.innerHTML;
  messageInput.disabled = true;
  sendButton.disabled = true;
  sendButton.innerHTML = '<span class="animate-spin" aria-hidden="true">↻</span> Sending...';

  try {
    // Build form data
    const formData = new FormData();
    formData.append('message', text);
    uploadedFiles.forEach(file => formData.append('files[]', file));

    // Add CSRF token
    const csrfToken = window.utils.getCSRFToken();
    formData.append('csrf_token', csrfToken);

    // Show user message right away
    appendUserMessage(chatBox, text);
    messageInput.value = '';
    showTypingIndicator(chatBox);

    // Check streaming
    const chatId = window.CHAT_CONFIG?.chatId;
    const modelSelect = document.getElementById('model-select');
    const modelId = modelSelect?.value;
    const model = window.CHAT_CONFIG.models?.find(m => m.id === parseInt(modelId));
    const useStreaming = model?.supports_streaming && !model?.requires_o1_handling;

    let responseData;
    if (useStreaming) {
      // SSE or text/event-stream approach
      const response = await fetch('/chat/', {
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
            appendAssistantMessage(chatBox, accumulatedResponse, true);
          }
        }
      }
      // Final update
      appendAssistantMessage(chatBox, accumulatedResponse, false);
      responseData = { response: accumulatedResponse };
    } else {
      // Normal fetch-based response
      responseData = await fetchWithCSRF('/chat/', {
        method: 'POST',
        body: formData,
        headers: {
          'X-Chat-ID': chatId,
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      if (responseData.response) {
        appendAssistantMessage(chatBox, responseData.response);
      } else if (responseData.error) {
        throw new Error(responseData.error);
      } else {
        throw new Error('No response received from server.');
      }
    }

    // Clear files after a successful send
    clearFiles();

    // Show any excluded files
    if (Array.isArray(responseData?.excluded_files)) {
      responseData.excluded_files.forEach(file => {
        showFeedback(`Failed to upload ${file.filename}: ${file.error}`, 'error');
      });
    }
  } catch (error) {
    console.error('Error sending message:', error);
    showFeedback(error.message || 'Failed to send message', 'error');
    messageInput.value = text; // Restore the user’s text on failure
  } finally {
    messageInput.disabled = false;
    sendButton.disabled = false;
    sendButton.innerHTML = originalButtonText;
    removeTypingIndicator();
    messageInput.focus();
  }
}

/**
 * Updates the title of a specific chat.
 * @param {string} chatId - The unique identifier of the chat to be updated.
 * @throws {Error} Throws an error if the title update fails or exceeds 100 characters.
 * @description Prompts the user to enter a new chat title, validates its length, and sends a request to update the title on the server. Updates the UI with the new title if successful.
 */
export async function editChatTitle(chatId) {
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

/**
 * Deletes the specified chat after user confirmation.
 * @param {string} chatId - The unique identifier of the chat to be deleted.
 * @throws {Error} Throws an error if the chat deletion fails or is not confirmed by the user.
 * @description Prompts the user for confirmation, sends a DELETE request to the server, and reloads the page on successful deletion.
 */
export async function deleteChat(chatId) {
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

/**
 * Regenerates the last assistant response by re-sending the most recent user message.
 * 
 * @param {HTMLButtonElement} button - The regenerate response button that triggered the action.
 * @param {HTMLElement} chatBox - The container element for chat messages.
 * @throws {Error} Throws an error if chat ID is missing, no message is found, or server request fails.
 * 
 * @description
 * This function handles regenerating an AI response by:
 * - Finding the last user message in the chat
 * - Removing existing assistant messages
 * - Sending the last message back to the server
 * - Supporting both streaming and non-streaming response modes
 * - Appending the regenerated response to the chat box
 * 
 * @example
 * // Typical usage in an event listener
 * regenerateButton.addEventListener('click', () => regenerateResponse(regenerateButton, chatContainer));
 */
export async function regenerateResponse(button, chatBox) {
  button.disabled = true;
  try {
    const chatId = new URLSearchParams(window.location.search).get('chat_id');
    if (!chatId) {
      showFeedback('Chat ID not found', 'error');
      return;
    }

    // Find the last user message
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

    // Remove all assistant messages after that user message
    while (
      chatBox.lastElementChild &&
      !chatBox.lastElementChild.querySelector('.bg-blue-600')
    ) {
      chatBox.lastElementChild.remove();
    }
    if (chatBox.lastElementChild) {
      chatBox.lastElementChild.remove(); // remove the user bubble too
    }

    showTypingIndicator(chatBox);

    // Prepare form data with the last user message
    const formData = new FormData();
    formData.append('message', lastUserMessage);

    // Check if streaming
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
            appendAssistantMessage(chatBox, accumulatedResponse, true);
          }
        }
      }
      appendAssistantMessage(chatBox, accumulatedResponse, false);
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
        appendAssistantMessage(chatBox, responseData.response);
      } else {
        throw new Error(responseData.error || 'Failed to regenerate response');
      }
    }
  } catch (error) {
    console.error('Error regenerating response:', error);
    showFeedback(error.message, 'error');
  } finally {
    button.disabled = false;
    removeTypingIndicator();
  }
}
