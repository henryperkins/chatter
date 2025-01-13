// chatUI.js
// Handles UI-related actions: appending messages, typing indicators, etc.

import { showFeedback } from '../utils.js'; // Adjust path if needed

/**
 * Automatically resizes a <textarea> to fit its content.
 */
export function adjustTextareaHeight(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = `${textarea.scrollHeight}px`;
}

/**
 * Sets up an IntersectionObserver on chat messages for lazy loading/fade-ins.
 */
export function setupScrollObserver(chatBox) {
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

  chatBox.querySelectorAll('.message').forEach(message => {
    observer.observe(message);
  });
}

/**
 * Simple HTML escape function.
 */
export function escapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Shows a "typing..." indicator in the chat.
 */
export function showTypingIndicator(chatBox) {
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

/**
 * Removes the "typing..." indicator from the chat.
 */
export function removeTypingIndicator() {
  const indicator = document.getElementById('typing-indicator');
  if (indicator && indicator.parentNode) {
    indicator.parentNode.removeChild(indicator);
  } else {
    console.warn('Typing indicator element not found or already removed.');
  }
}

/**
 * Appends a user (blue) message to the chat box.
 */
export function appendUserMessage(chatBox, message) {
  const messageDiv = document.createElement('div');
  messageDiv.className = 'flex w-full mt-2 space-x-3 max-w-2xl ml-auto justify-end';
  messageDiv.setAttribute('role', 'listitem');
  messageDiv.innerHTML = `
    <div>
      <div class="relative bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
        <p class="text-sm break-words overflow-x-auto">${escapeHtml(message)}</p>
      </div>
      <span class="text-xs text-gray-500 dark:text-gray-400 leading-none">
        ${new Date().toLocaleTimeString()}
      </span>
    </div>
  `;
  chatBox.appendChild(messageDiv);
  chatBox.scrollTop = chatBox.scrollHeight;
}

/**
 * Appends an assistant (gray) message to the chat box.
 * Supports "streaming" updates if isStreaming=true.
 */
export function appendAssistantMessage(chatBox, message, isStreaming = false) {
  if (!message || typeof message !== 'string') {
    console.error('Invalid message content.');
    return;
  }

  // Using global vendor libraries on window
  const md = window.md;
  const DOMPurify = window.DOMPurify;
  const Prism = window.Prism;

  let messageDiv;
  let contentDiv;

  if (isStreaming && chatBox.lastElementChild) {
    // Update the last message chunk
    messageDiv = chatBox.lastElementChild;
    contentDiv = messageDiv.querySelector('.prose');
    if (!contentDiv) {
      console.error('Content div not found in existing message');
      return;
    }
  } else {
    // Create a new message bubble
    messageDiv = document.createElement('div');
    messageDiv.className = 'flex w-full mt-2 space-x-3 max-w-3xl';
    messageDiv.setAttribute('role', 'listitem');
    messageDiv.innerHTML = `
      <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700"
           role="img" aria-label="Assistant avatar"></div>
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

  // Safely render the markdown
  try {
    const renderedHtml = md.render(message);
    const sanitizedHtml = DOMPurify.sanitize(renderedHtml, {
      ALLOWED_TAGS: [
        'b','i','em','strong','a','p','blockquote','code','pre','ul','ol','li',
        'h1','h2','h3','h4','h5','h6','br','hr','span','img','table','thead',
        'tbody','tr','th','td'
      ],
      ALLOWED_ATTR: ['href','src','alt','class','aria-label','role']
    });

    contentDiv.innerHTML = sanitizedHtml;

    // Syntax highlighting
    Prism.highlightAllUnder(contentDiv);

    // Make code blocks accessible
    contentDiv.querySelectorAll('pre').forEach(pre => {
      pre.setAttribute('role', 'region');
      pre.setAttribute('aria-label', 'Code block');
      pre.tabIndex = 0;
    });

    // Only append if this is a fresh message or if no lastElementChild
    if (!isStreaming || !chatBox.lastElementChild) {
      chatBox.appendChild(messageDiv);
    }

    chatBox.scrollTop = chatBox.scrollHeight;
  } catch (error) {
    console.error('Error rendering markdown:', error);
    contentDiv.innerHTML = `<pre>${DOMPurify.sanitize(message)}</pre>`;
  }
}
