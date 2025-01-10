// static/js/chat.js

// Global functions for message actions
// Helper functions used by global functions
function showTypingIndicator() {
  const chatBox = document.getElementById("chat-box");
  if (!chatBox) return;
  
  const typingIndicator = document.createElement("div");
  typingIndicator.id = "typing-indicator";
  typingIndicator.className = "flex w-full mt-2 space-x-3 max-w-3xl";
  typingIndicator.innerHTML = `
    <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700"></div>
    <div class="flex-grow">
      <div class="bg-gray-100 dark:bg-gray-800 p-3 rounded-r-lg rounded-bl-lg">
        <p class="text-sm text-gray-500 dark:text-gray-400">Assistant is typing...</p>
      </div>
      <span class="text-xs text-gray-500 dark:text-gray-400 leading-none">${new Date().toLocaleTimeString()}</span>
    </div>
  `;
  chatBox.appendChild(typingIndicator);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function removeTypingIndicator() {
  const typingIndicator = document.getElementById("typing-indicator");
  if (typingIndicator) {
    typingIndicator.remove();
  }
}

function getCSRFToken() {
  return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

function showFeedback(message, type = "info") {
  const feedbackDiv = document.createElement("div");
  feedbackDiv.className = `fixed bottom-4 right-4 p-4 rounded-lg shadow-lg ${
    type === "error"
      ? "bg-red-500 text-white"
      : type === "success"
      ? "bg-green-500 text-white"
      : "bg-blue-500 text-white"
  }`;
  feedbackDiv.innerHTML = message;
  document.body.appendChild(feedbackDiv);
  setTimeout(() => {
    feedbackDiv.remove();
  }, 3000);
}

window.regenerateResponse = async function(event) {
  try {
    const button = event.currentTarget;
    if (button) {
      // Add temporary animation class
      button.classList.add('animate-ping');
      setTimeout(() => button.classList.remove('animate-ping'), 200);
    }

    const chatId = new URLSearchParams(window.location.search).get("chat_id");
    if (!chatId) {
      showFeedback("No chat ID found", "error");
      return;
    }

    showFeedback("Regenerating response...", "info");

    // Get the chat context
    const contextResponse = await fetch(`/get_chat_context/${chatId}`);
    if (!contextResponse.ok) {
      throw new Error("Failed to get chat context");
    }
    const contextData = await contextResponse.json();
    const messages = contextData.messages;

    if (messages.length < 2) return;

    // Get the last user message
    let lastUserMessage;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserMessage = messages[i].content;
        break;
      }
    }

    if (!lastUserMessage) return;

    // Remove messages after the last user message
    const messageElements = Array.from(document.getElementById("chat-box").children);
    let lastUserMessageIndex = -1;
    for (let i = messageElements.length - 1; i >= 0; i--) {
      const messageDiv = messageElements[i];
      if (messageDiv.querySelector(".bg-blue-600")) {
        lastUserMessageIndex = i;
        break;
      }
    }

    if (lastUserMessageIndex !== -1) {
      const chatBox = document.getElementById("chat-box");
      while (chatBox.children.length > lastUserMessageIndex + 1) {
        chatBox.lastElementChild.remove();
      }
    }

    // Resend the last user message
    const formData = new FormData();
    formData.append("message", lastUserMessage);

    showTypingIndicator();
    const response = await fetch("/chat", {
      method: "POST",
      headers: {
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: formData
    });

    removeTypingIndicator();

    if (response.ok) {
      const data = await response.json();
      if (data.response) {
        appendAssistantMessage(data.response);
      }
    } else {
      const error = await response.json();
      showFeedback(error.error || "An error occurred", "error");
    }
  } catch (error) {
    removeTypingIndicator();
    showFeedback("An error occurred while regenerating response", "error");
  }
};

window.editLastMessage = function() {
  try {
    const chatBox = document.getElementById("chat-box");
    const messageInput = document.getElementById("message-input");
    if (!chatBox || !messageInput) {
      showFeedback("Required elements not found", "error");
      return;
    }

    const messages = Array.from(chatBox.children);
    let lastUserMessage;
    let lastUserMessageElement;

    // Find the last user message
    for (let i = messages.length - 1; i >= 0; i--) {
      const messageDiv = messages[i];
      if (messageDiv.querySelector(".bg-blue-600")) {
        const messageContent = messageDiv.querySelector(".bg-blue-600 .text-sm");
        if (messageContent) {
          lastUserMessage = messageContent.textContent;
          lastUserMessageElement = messageDiv.closest(".flex");
          break;
        }
      }
    }

    if (!lastUserMessage) {
      showFeedback("No message found to edit", "error");
      return;
    }

    // Set the message in the input
    messageInput.value = lastUserMessage;
    messageInput.style.height = 'auto';
    messageInput.style.height = messageInput.scrollHeight + 'px';

    // Remove messages after the last user message
    while (chatBox.lastElementChild && chatBox.lastElementChild !== lastUserMessageElement) {
      chatBox.lastElementChild.remove();
    }
    if (lastUserMessageElement) {
      lastUserMessageElement.remove();
    }

    // Focus on the input and show feedback
    messageInput.focus();
    showFeedback("Message ready to edit", "success");
  } catch (error) {
    console.error("Error editing message:", error);
    showFeedback("Error editing message", "error");
  }
};

window.copyToClipboard = async function(text) {
  if (!text) {
    showFeedback("No text to copy", "error");
    return;
  }
  
  const button = event.currentTarget;
  if (button) {
    // Add temporary animation class
    button.classList.add('animate-ping');
    setTimeout(() => button.classList.remove('animate-ping'), 200);
  }

  try {
    await navigator.clipboard.writeText(text);
    showFeedback("Copied to clipboard!", "success");
  } catch (err) {
    console.error("Copy error:", err);
    showFeedback("Failed to copy text", "error");
  }
};

(function () {
  // Debug statement to confirm the file is loaded
  console.log("chat.js loaded");

  // Constants for file handling
  let uploadedFiles = [];
  const MAX_FILES = 5;
  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
  const MAX_MESSAGE_LENGTH = 1000; // Maximum message length
  const ALLOWED_FILE_TYPES = [
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/x-python",
    "application/javascript",
    "text/markdown",
    "image/jpeg",
    "image/png",
  ];

  // Get DOM elements
  const chatBox = document.getElementById("chat-box");
  const messageInput = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const newChatBtn = document.getElementById("new-chat-btn");
  const fileListDiv = document.getElementById("file-list");
  const uploadedFilesDiv = document.getElementById("uploaded-files");
  const uploadProgress = document.getElementById("upload-progress");
  const uploadProgressBar = document.getElementById("upload-progress-bar");
  const feedbackMessage = document.getElementById("feedback-message");
  const fileInput = document.getElementById("file-input");
  const uploadButton = document.getElementById("upload-button");
  const modelSelect = document.getElementById("model-select");
  const editModelButton = document.getElementById("edit-model-btn");
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const offCanvasMenu = document.getElementById("off-canvas-menu");
  const offCanvasClose = document.getElementById("off-canvas-close");
  const overlay = document.getElementById("overlay");

  // Helper Functions
  function adjustTextareaHeight(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }

  // Initialize markdown-it with Prism.js highlighting
  const defaultLanguage = "plaintext";

  const md = window.markdownit({
    html: false,
    linkify: true,
    typographer: true,
    highlight: function (str, lang) {
      if (lang && Prism.languages[lang]) {
        return `<pre class="language-${lang}"><code>${Prism.highlight(
          str,
          Prism.languages[lang],
          lang
        )}</code></pre>`;
      } else {
        return `<pre class="language-plaintext"><code>${Prism.highlight(
          str,
          Prism.languages.plaintext,
          "plaintext"
        )}</code></pre>`;
      }
    },
  });

  // Render Markdown content safely
  function renderMarkdown(content) {
    const html = md.render(content);

    // Check if DOMPurify is available
    if (typeof DOMPurify !== "undefined" && DOMPurify.sanitize) {
      return DOMPurify.sanitize(html, {
        USE_PROFILES: { html: true },
        ALLOWED_TAGS: [
          "p",
          "strong",
          "em",
          "br",
          "ul",
          "ol",
          "li",
          "a",
          "img",
          "pre",
          "code",
        ],
        ALLOWED_ATTR: ["href", "target", "rel", "src", "alt", "class", "style"],
      });
    }

    // Fallback basic sanitization
    return html
      .replace(/<script.*?>.*?<\/script>/gi, "")
      .replace(/on\w+="[^"]*"/gi, "");
  }

  // File Handling Functions
  function handleFileUpload(files) {
    const filesArray = Array.from(files);
    const invalidFiles = [];
    const validFiles = [];

    filesArray.forEach((file) => {
      if (!ALLOWED_FILE_TYPES.includes(file.type)) {
        invalidFiles.push(`${file.name} (unsupported type)`);
      } else if (file.size > MAX_FILE_SIZE) {
        invalidFiles.push(`${file.name} (exceeds size limit)`);
      } else {
        validFiles.push(file);
      }
    });

    uploadedFiles = uploadedFiles.concat(validFiles);
    renderFileList();

    if (invalidFiles.length > 0) {
      showFeedback(
        `Some files were not added: ${invalidFiles.join(", ")}`,
        "error"
      );
    }

    if (validFiles.length > 0) {
      showFeedback(`${validFiles.length} file(s) ready to upload.`, "success");
    }
  }

  function renderFileList() {
    if (!fileListDiv) return;

    fileListDiv.innerHTML = "";
    uploadedFiles.forEach((file, index) => {
      const fileDiv = document.createElement("div");
      fileDiv.className =
        "flex items-center justify-between bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded text-sm";
      fileDiv.innerHTML = `
        <div class="flex items-center">
          <svg class="w-4 h-4 mr-2 text-green-500" fill="currentColor" viewBox="0 0 20 20">
            <path d="M16.707 5.293a1 1 0 00-1.414-1.414L9 10.172 5.707 6.879A1 1 0 004.293 8.293l4 4c.39.39 1.024.39 1.414 0l7-7z" />
          </svg>
          ${file.name}
        </div>
        <button class="text-red-500 hover:text-red-700 remove-file-button" data-index="${index}">
          Remove
        </button>
      `;
      fileListDiv.appendChild(fileDiv);
    });

    if (uploadedFilesDiv) {
      uploadedFilesDiv.classList.toggle("hidden", uploadedFiles.length === 0);
    }

    document.querySelectorAll(".remove-file-button").forEach((button) => {
      button.addEventListener("click", function () {
        const index = parseInt(this.dataset.index);
        uploadedFiles.splice(index, 1);
        renderFileList();
      });
    });
  }

  // Typing Indicator Functions
  function showTypingIndicator() {
    const typingIndicator = document.createElement("div");
    typingIndicator.id = "typing-indicator";
    typingIndicator.className = "flex w-full mt-2 space-x-3 max-w-3xl";
    typingIndicator.innerHTML = `
      <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
      <div class="flex-grow">
        <div class="bg-gray-100 dark:bg-gray-800 p-3 rounded-r-lg rounded-bl-lg">
          <p class="text-sm text-gray-500">Assistant is typing...</p>
        </div>
        <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
      </div>
    `;
    chatBox.appendChild(typingIndicator);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function removeTypingIndicator() {
    const typingIndicator = document.getElementById("typing-indicator");
    if (typingIndicator) {
      typingIndicator.remove();
    }
  }

  // Message Handling Functions
  async function sendMessage(e) {
    if (e && e.preventDefault) {
      e.preventDefault();
    }

    const message = messageInput.value.trim();
    if (!message && uploadedFiles.length === 0) {
      showFeedback("Please enter a message or upload files.", "error");
      return false;
    }

    if (message) {
      appendUserMessage(message);
      messageInput.value = "";
      adjustTextareaHeight(messageInput);
    }

    const formData = new FormData();
    formData.append("message", message);
    uploadedFiles.forEach((file) => {
      formData.append("files[]", file);
    });

    // Disable input controls
    sendButton.disabled = true;
    messageInput.disabled = true;

    // Show loading spinner on send button
    sendButton.innerHTML = `
      <svg class="animate-spin h-5 w-5 text-white mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
    `;

    // Show typing indicator
    showTypingIndicator();

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "X-CSRFToken": getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest"
        },
        body: formData
      });

      // Remove typing indicator and re-enable inputs
      removeTypingIndicator();
      sendButton.disabled = false;
      messageInput.disabled = false;
      sendButton.innerHTML = "<span>Send</span>";

      if (response.ok) {
        const data = await response.json();
        if (data.response) {
          appendAssistantMessage(data.response);
          uploadedFiles = [];
          renderFileList();
        }
        if (data.excluded_files && data.excluded_files.length > 0) {
          const errorMessages = data.excluded_files
            .map((file) => `${file.filename}: ${file.error}`)
            .join("<br>");
          showFeedback(`File upload errors:<br>${errorMessages}`, "error");
        }
        if (data.included_files && data.included_files.length > 0) {
          const fileNames = data.included_files
            .map((file) => file.filename)
            .join(", ");
          showFeedback(`Files uploaded successfully: ${fileNames}`, "success");
        }
      } else {
        const error = await response.json();
        showFeedback(error.error || "An error occurred", "error");
      }
    } catch (error) {
      removeTypingIndicator();
      sendButton.disabled = false;
      messageInput.disabled = false;
      sendButton.innerHTML = "<span>Send</span>";
      showFeedback("An error occurred while sending the message", "error");
    }
  }


  // Function to delete a chat
  async function deleteChat(chatId) {
    if (!confirm("Are you sure you want to delete this chat?")) return;

    try {
      const response = await fetch(`/delete_chat/${chatId}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest"
        }
      });

      const data = await response.json();
      if (data.success) {
        // If we're currently viewing the deleted chat, redirect to a new chat
        if (window.location.href.includes(chatId)) {
          window.location.href = "/chat_interface";
        } else {
          // Otherwise just remove the chat from the list with animation
          const chatElement = document
            .querySelector(`.delete-chat-btn[data-chat-id="${chatId}"]`)
            .closest(".relative");
          if (chatElement) {
            chatElement.remove();
          }
        }
      } else {
        showFeedback("Failed to delete chat", "error");
      }
    } catch (error) {
      console.error("Error:", error);
      showFeedback("An error occurred while deleting the chat", "error");
    }
  }

  // Function to edit a chat title
  async function editChatTitle(chatId) {
    const newTitle = prompt("Enter the new title for this chat:");
    if (!newTitle || !newTitle.trim()) return;

    try {
      const response = await fetch(`/update_chat_title/${chatId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ title: newTitle })
      });

      const data = await response.json();
      if (data.success) {
        // Update the title in the UI
        const chatTitleElement = document.getElementById("chat-title");
        if (chatTitleElement) {
          const parts = chatTitleElement.textContent.split(" - ");
          const modelName = parts.length > 1 ? parts[1] : "";
          chatTitleElement.textContent = `${newTitle} - ${modelName}`;
        }
      } else {
        showFeedback(data.error || "Failed to update chat title", "error");
      }
    } catch (error) {
      console.error("Error:", error);
      showFeedback("An error occurred while updating the chat title", "error");
    }
  }

  // Event Listeners
  if (messageInput) {
    messageInput.addEventListener("input", function () {
      adjustTextareaHeight(this);
    });
    messageInput.addEventListener("keyup", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  if (sendButton) {
    sendButton.addEventListener("click", (e) => {
      sendMessage(e);
    });
  }

  // Handle form submission if the send button is inside a form
  const chatForm = document.getElementById("chat-form");
  if (chatForm) {
    chatForm.addEventListener("submit", (e) => {
      sendMessage(e);
    });
  }

  if (fileInput && uploadButton) {
    uploadButton.addEventListener("click", () => {
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      if (this.files && this.files.length > 0) {
        handleFileUpload(this.files);
      }
    });
  }

  // Model Selection and Editing
  if (modelSelect && editModelButton) {
    // Function to update the edit button state
    function updateEditButtonState() {
      const selectedModelId = modelSelect.value;
      if (selectedModelId) {
        editModelButton.dataset.modelId = selectedModelId;
        editModelButton.disabled = false;
      } else {
        delete editModelButton.dataset.modelId;
        editModelButton.disabled = true;
      }
    }

    // Initial state on page load
    updateEditButtonState();

    modelSelect.addEventListener("change", function () {
      updateEditButtonState();
    });

    editModelButton.addEventListener("click", function () {
      const modelId = this.dataset.modelId;
      if (modelId) {
        window.location.href = `/model/edit-model/${modelId}`;
      }
    });
  }

  // New Chat Button
  if (newChatBtn) {
    newChatBtn.addEventListener("click", async () => {
      try {
        const response = await fetch("/new_chat", {
          method: "POST",
          headers: {
            "X-CSRFToken": getCSRFToken(),
            "X-Requested-With": "XMLHttpRequest"
          }
        });
        if (response.ok) {
          const data = await response.json();
          if (data.success) {
            window.location.href = `/chat_interface?chat_id=${data.chat_id}`;
          }
        } else {
          showFeedback("Failed to create a new chat.", "error");
        }
      } catch (error) {
        console.error("Error creating new chat:", error);
        showFeedback("Error creating new chat.", "error");
      }
    });
  }

  // Function to apply markdown and syntax highlighting to messages
  function formatMessages() {
    document.querySelectorAll('.prose, .markdown-content').forEach(element => {
      if (element.classList.contains('prose')) {
        // Assistant messages are already rendered by Flask
        Prism.highlightAllUnder(element);
      } else {
        // User messages need markdown rendering
        const content = element.textContent;
        element.innerHTML = renderMarkdown(content);
        Prism.highlightAllUnder(element);
      }
    });
  }

  // Add event listeners for new features
  document.addEventListener("DOMContentLoaded", function () {
    // Apply formatting to all messages
    formatMessages();

    // Edit title button
    const editTitleBtn = document.getElementById("edit-title-btn");
    if (editTitleBtn) {
      editTitleBtn.addEventListener("click", function () {
        const chatId = new URLSearchParams(window.location.search).get("chat_id");
        if (chatId) {
          editChatTitle(chatId);
        }
      });
    }

    // Delete chat buttons
    document.querySelectorAll(".delete-chat-btn").forEach(button => {
      button.addEventListener("click", function (event) {
        event.preventDefault();
        const chatId = this.getAttribute("data-chat-id");
        deleteChat(chatId);
      });
    });

    // Message action buttons using event delegation
    const chatBox = document.getElementById("chat-box");
    if (chatBox) {
      chatBox.addEventListener("click", async function (e) {
        const target = e.target.closest("button");
        if (!target) return;

        try {
          // Copy button
          if (target.classList.contains("copy-button")) {
            const messageContent = target.closest(".max-w-lg").querySelector(".prose, .markdown-content")?.textContent;
            if (messageContent) {
              await window.copyToClipboard(messageContent);
            } else {
              showFeedback("No content found to copy", "error");
            }
          }
          // Regenerate button
          else if (target.classList.contains("regenerate-button")) {
            await window.regenerateResponse(e);
          }
          // Edit button
          else if (target.classList.contains("edit-message-button")) {
            window.editLastMessage();
          }
        } catch (error) {
          console.error("Error handling button click:", error);
          showFeedback("An error occurred", "error");
        }
      });
    }
  });

  // Modify appendAssistantMessage to include copy and regenerate buttons
  function appendAssistantMessage(message) {
    const assistantMessageDiv = document.createElement("div");
    assistantMessageDiv.className = "flex w-full mt-2 space-x-3 max-w-xs";
    assistantMessageDiv.innerHTML = `
      <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700"></div>
      <div class="relative max-w-lg">
        <div class="bg-gray-300 dark:bg-gray-800 p-3 rounded-r-lg rounded-bl-lg">
          <div class="text-sm markdown-content dark:text-gray-200"></div>
        </div>
        <div class="absolute right-0 top-0 flex space-x-2">
          <button class="copy-button p-1 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300" title="Copy to clipboard">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
            </svg>
          </button>
          <button class="regenerate-button p-1 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300" title="Regenerate response">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
        <span class="text-xs text-gray-500 dark:text-gray-400 leading-none">${new Date().toLocaleTimeString()}</span>
      </div>
    `;
    assistantMessageDiv.querySelector(".markdown-content").innerHTML = renderMarkdown(message);
    chatBox.appendChild(assistantMessageDiv);
    Prism.highlightAllUnder(assistantMessageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // Modify appendUserMessage to include edit button
  function appendUserMessage(message) {
    const userMessageDiv = document.createElement("div");
    userMessageDiv.className = "flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end";
    userMessageDiv.innerHTML = `
      <div>
        <div class="relative bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
          <div class="text-sm markdown-content"></div>
          <button class="edit-message-button absolute -left-6 top-2 text-gray-500 hover:text-gray-700" title="Edit message">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
        </div>
        <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
      </div>
      <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-700"></div>
    `;
    userMessageDiv.querySelector(".markdown-content").innerHTML = renderMarkdown(message);
    chatBox.appendChild(userMessageDiv);
    Prism.highlightAllUnder(userMessageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // Function to show feedback messages
  function showFeedback(message, type = "info") {
    const feedbackDiv = document.createElement("div");
    feedbackDiv.className = `fixed bottom-4 right-4 p-4 rounded-lg shadow-lg ${
      type === "error"
        ? "bg-red-500 text-white"
        : type === "success"
        ? "bg-green-500 text-white"
        : "bg-blue-500 text-white"
    }`;
    feedbackDiv.innerHTML = message;
    document.body.appendChild(feedbackDiv);
    setTimeout(() => {
      feedbackDiv.remove();
    }, 3000);
  }

})();
