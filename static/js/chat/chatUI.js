// chatUI.js
// Handles UI-related actions: appending messages, typing indicators, etc.

import { showFeedback } from '../utils.js'; // Adjust path if needed

/**
 * Automatically adjusts the height of a textarea to match its content.
 * 
 * @param {HTMLTextAreaElement} textarea - The textarea element to resize dynamically.
 * @description This function sets the textarea's height to 'auto' and then sets it to the scroll height,
 * effectively expanding the textarea vertically to accommodate all of its content without scrollbars.
 */
export function adjustTextareaHeight(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = `${textarea.scrollHeight}px`;
}

/**
 * Sets up an IntersectionObserver to dynamically add visibility effects to chat messages.
 * 
 * @param {HTMLElement} chatBox - The container element holding chat messages.
 * @description Observes each message within the chat box and adds a 'visible' class when the message becomes partially visible, enabling lazy loading and fade-in animations.
 * 
 * @example
 * const chatContainer = document.getElementById('chat-messages');
 * setupScrollObserver(chatContainer);
 * 
 * @performance Lightweight observer with low performance overhead
 * @see https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API
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
 * Escapes special HTML characters in a string to prevent XSS attacks.
 * @param {string} unsafe - The input string containing potentially unsafe HTML characters.
 * @returns {string} A sanitized string with HTML special characters replaced by their corresponding HTML entities.
 * @example
 * // returns "&lt;script&gt;alert('XSS')&lt;/script&gt;"
 * escapeHtml('<script>alert('XSS')</script>')
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
 * Displays a "typing..." indicator in the chat box to signal that the assistant is composing a response.
 * 
 * @param {HTMLElement} chatBox - The container element where the typing indicator will be added.
 * @description Removes any existing typing indicator and creates a new animated indicator with an avatar, 
 * typing dots animation, and current timestamp. The indicator is automatically scrolled into view.
 * 
 * @example
 * const chatContainer = document.getElementById('chat-messages');
 * showTypingIndicator(chatContainer);
 * 
 * @accessibility Adds ARIA attributes to improve screen reader experience
 * @performance O(1) time complexity for DOM manipulation
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
 * Removes the "typing..." indicator from the chat box.
 * 
 * @description Finds and removes the typing indicator element from the DOM. 
 * If the indicator is not found, it logs a warning to the console.
 * 
 * @throws {Error} Implicitly handles cases where the indicator cannot be removed.
 * 
 * @example
 * // Remove the typing indicator when a message is sent or typing stops
 * removeTypingIndicator();
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
 * Appends a user message to the chat box with a blue message bubble.
 * @param {HTMLElement} chatBox - The container element where messages are displayed.
 * @param {string} message - The text content of the user's message.
 * @description Creates a styled message div with the user's message, applies blue styling, 
 * escapes HTML to prevent XSS, and automatically scrolls the chat box to the bottom.
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
 * Appends an assistant message to the chat box with markdown rendering and syntax highlighting.
 * 
 * @param {HTMLElement} chatBox - The container element for chat messages.
 * @param {string} message - The markdown-formatted message content.
 * @param {boolean} [isStreaming=false] - Indicates whether the message is being streamed/updated incrementally.
 * 
 * @description
 * This function handles rendering assistant messages with the following features:
 * - Markdown rendering using global markdown library
 * - HTML sanitization to prevent XSS attacks
 * - Syntax highlighting for code blocks
 * - Accessibility improvements for code regions
 * - Copy and regenerate message buttons
 * - Timestamp display
 * 
 * @throws {Error} Logs an error if message rendering fails.
 * 
 * @example
 * // Append a new assistant message
 * appendAssistantMessage(chatBoxElement, '# Hello, world!');
 * 
 * @example
 * // Stream an incremental message update
 * appendAssistantMessage(chatBoxElement, 'Additional content', true);
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
