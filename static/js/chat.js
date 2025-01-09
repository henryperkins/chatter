// static/js/chat.js

import { getCSRFToken, showFeedback } from "./utils.js";

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
        "flex items-center justify-between bg-gray-100 px-2 py-1 rounded text-sm";
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

    // Set a timeout to notify the user if response is taking too long (e.g., 15 seconds)
    const responseTimeout = setTimeout(() => {
      showFeedback(
        "The assistant is taking longer than usual to respond.",
        "info"
      );
    }, 15000);

    try {
      const response = await axios.post("/chat", formData, {
        headers: {
          "X-CSRFToken": getCSRFToken(),
        },
        onUploadProgress: function (progressEvent) {
          if (progressEvent.lengthComputable) {
            const percentComplete = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            uploadProgressBar.style.width = `${percentComplete}%`;
          }
        },
      });

      const data = response.data;

      // Clear the timeout if response is received
      clearTimeout(responseTimeout);

      // Remove typing indicator and re-enable inputs
      removeTypingIndicator();
      sendButton.disabled = false;
      messageInput.disabled = false;
      sendButton.innerHTML = "<span>Send</span>";

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
    } catch (error) {
      // Clear the timeout in case of error
      clearTimeout(responseTimeout);

      // Remove typing indicator and re-enable inputs
      removeTypingIndicator();
      sendButton.disabled = false;
      messageInput.disabled = false;
      sendButton.innerHTML = "<span>Send</span>";

      console.error("Error sending message:", error);
      const errorMsg = error.response?.data?.error || "An error occurred.";
      showFeedback(errorMsg, "error");
    }
  }

  function appendUserMessage(message) {
    const userMessageDiv = document.createElement("div");
    userMessageDiv.className =
      "flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end";
    userMessageDiv.innerHTML = `
            <div>
                <div class="bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                    <div class="text-sm markdown-content"></div>
                </div>
                <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
        `;
    // Use renderMarkdown to render the message content
    userMessageDiv.querySelector(".markdown-content").innerHTML =
      renderMarkdown(message);
    chatBox.appendChild(userMessageDiv);
    // Highlight code blocks after adding to DOM
    Prism.highlightAllUnder(userMessageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function appendAssistantMessage(message) {
    const assistantMessageDiv = document.createElement("div");
    assistantMessageDiv.className = "flex w-full mt-2 space-x-3 max-w-xs";
    assistantMessageDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
            <div>
                <div class="bg-gray-300 p-3 rounded-r-lg rounded-bl-lg">
                    <div class="text-sm markdown-content"></div>
                </div>
                <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
            </div>
        `;
    // Use renderMarkdown for the message content
    assistantMessageDiv.querySelector(".markdown-content").innerHTML =
      renderMarkdown(message);
    chatBox.appendChild(assistantMessageDiv);
    // Highlight code blocks after adding to DOM
    Prism.highlightAllUnder(assistantMessageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
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
        // Correctly construct the URL for redirection
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
          },
        });
        if (response.ok) {
          const data = await response.json();
          if (data.success) {
            // Pass the newly created chat_id to the URL
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

  // Function to delete a chat
  function deleteChat(chatId) {
    console.log("deleteChat triggered for chatId:", chatId);
    if (confirm("Are you sure you want to delete this chat?")) {
      console.log("Sending request to delete chat:", chatId);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15-second timeout
      fetch(`/delete_chat/${chatId}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        signal: controller.signal,
      })
        .then((response) => {
          clearTimeout(timeoutId);
          return response.json();
        })
        .then((data) => {
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
            alert("Failed to delete chat");
          }
        })
        .catch((error) => {
          clearTimeout(timeoutId);
          if (error.name === "AbortError") {
            alert("Request timed out. Please try again.");
          } else {
            console.error("Error:", error);
            alert("An error occurred while deleting the chat");
          }
        });
    }
  }

  // Function to edit a chat title
  function editChatTitle(chatId) {
    console.log("editChatTitle triggered for chatId:", chatId);
    const newTitle = prompt("Enter the new title for this chat:");
    if (newTitle && newTitle.trim() !== "") {
      console.log("Sending request to update chat title:", newTitle);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15-second timeout
      fetch(`/update_chat_title/${chatId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({ title: newTitle }),
        signal: controller.signal,
      })
        .then((response) => {
          clearTimeout(timeoutId);
          return response.json();
        })
        .then((data) => {
          if (data.success) {
            // Update the title in the UI
            const chatTitleElement = document.getElementById("chat-title");
            if (chatTitleElement) {
              const parts = chatTitleElement.textContent.split(" - ");
              const modelName = parts.length > 1 ? parts[1] : "";
              chatTitleElement.textContent = `${newTitle} - ${modelName}`;
            }
            alert("Chat title updated successfully!");
          } else {
            alert(data.error || "Failed to update chat title");
          }
        })
        .catch((error) => {
          clearTimeout(timeoutId);
          if (error.name === "AbortError") {
            alert("Request timed out. Please try again.");
          } else {
            console.error("Error:", error);
            alert("An error occurred while updating the chat title");
          }
        });
    }
  }
})();
