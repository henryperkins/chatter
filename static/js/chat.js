// static/js/chat.js

let uploadedFiles = [];
const MAX_FILES = 5;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

const ALLOWED_FILE_TYPES = [
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/x-python',
    'application/javascript',
    'text/markdown',
    'image/jpeg',
    'image/png'
];

document.addEventListener("DOMContentLoaded", function () {
  const chatBox = document.getElementById("chat-box");
  const messageInput = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const newChatBtn = document.getElementById("new-chat-btn");
  const fileListDiv = document.getElementById("file-list");
  const dropZone = document.getElementById("drop-zone");
  const uploadedFilesDiv = document.getElementById("uploaded-files");
  const uploadProgress = document.getElementById("upload-progress");
  const uploadProgressBar = document.getElementById("upload-progress-bar");
  const feedbackMessage = document.getElementById("feedback-message");
  const fileInput = document.getElementById("file-input");
  const uploadButton = document.getElementById("upload-button");

  // Ensure textarea grows as the user types
  messageInput.addEventListener("input", function () {
    adjustTextareaHeight(this);
  });

  // --- Helper Functions ---

  function adjustTextareaHeight(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }

  function showFeedback(message, type = "success") {
    feedbackMessage.textContent = message;
    feedbackMessage.className = `fixed bottom-4 right-4 p-4 rounded-lg ${
      type === "success"
        ? "bg-green-100 border-green-400 text-green-700"
        : "bg-red-100 border-red-400 text-red-700"
    }`;
    feedbackMessage.classList.remove("hidden");
    setTimeout(() => feedbackMessage.classList.add("hidden"), 3000);
  }

  function renderMarkdown(content) {
    return DOMPurify.sanitize(marked.parse(content));
  }

  function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute("content");
  }

  // --- File Handling ---

  function handleFileUpload(files) {
    const filesArray = Array.from(files);

    if (uploadedFiles.length + filesArray.length > MAX_FILES) {
      showFeedback(
        `You can upload up to ${MAX_FILES} files at a time.`,
        "error"
      );
      return;
    }

    const validFiles = filesArray.filter((file) => {
      if (file.size > MAX_FILE_SIZE) {
        showFeedback(
          `File ${file.name} exceeds the 10MB size limit and was not added.`,
          "error"
        );
        return false;
      }
      return true;
    });

    uploadedFiles = uploadedFiles.concat(validFiles);
    renderFileList(uploadedFiles);
  }

  function renderFileList(files) {
    const fileListDiv = document.getElementById("file-list");
    fileListDiv.innerHTML = "";

    files.forEach((file, index) => {
      const fileDiv = document.createElement("div");
      fileDiv.className =
        "flex items-center justify-between bg-white px-2 py-1 rounded border text-sm";
      fileDiv.innerHTML = `
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-1 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M5.5 3A2.5 2.5 0 003 5.5v9A2.5 2.5 0 005.5 17h9a2.5 2.5 0 002.5-2.5v-9A2.5 2.5 0 0014.5 3h-9zM5.5 4a1.5 1.5 0 011.5 1.5V14a1.5 1.5 0 01-1.5 1.5H6a.5.5 0 01-.5-.5V5.5zM14.5 4A1.5 1.5 0 0013 5.5v8.939l-1.562-1.562a.5.5 0 10-.707.707l2.417 2.417a.5.5 0 00.708 0l2.417-2.417a.5.5 0 10-.707-.707L14 14.439V5.5a1.5 1.5 0 00-1.5-1.5h-7a.5.5 0 000 1h7z" clip-rule="evenodd"></path>
                </svg>
                ${file.name}
            </div>
            <button class="text-red-500 hover:text-red-700 remove-file-button" data-index="${index}">
                Remove
            </button>
        `;
      fileListDiv.appendChild(fileDiv);

      // Optionally, add a preview for text files
      if (file.type.startsWith("text/")) {
        const reader = new FileReader();
        reader.onload = function (e) {
          const preview = document.createElement("pre");
          preview.className =
            "text-xs bg-gray-100 p-2 rounded mt-1 overflow-x-auto";
          preview.textContent =
            e.target.result.substring(0, 500) +
            (e.target.result.length > 500 ? "..." : "");
          fileDiv.appendChild(preview);
        };
        reader.readAsText(file);
      }

      fileListDiv.appendChild(fileDiv);
    });

    // Add event listeners to remove buttons
    document.querySelectorAll(".remove-file-button").forEach((button) => {
      button.addEventListener("click", function () {
        const index = parseInt(this.dataset.index);
        uploadedFiles.splice(index, 1);
        renderFileList(uploadedFiles);
      });
    });

    // Show or hide uploaded files section
    const uploadedFilesDiv = document.getElementById("uploaded-files");
    if (files.length > 0) {
      uploadedFilesDiv.classList.remove("hidden");
    } else {
      uploadedFilesDiv.classList.add("hidden");
    }
  }

  // --- Drag and Drop ---
  const dropZone = document.getElementById("drop-zone");
  const messageInputArea = document.querySelector(".message-input-area");

  ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
    messageInputArea.addEventListener(eventName, preventDefaults, false);
    dropZone.addEventListener(eventName, preventDefaults, false);
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  messageInputArea.addEventListener("dragover", () => {
    dropZone.classList.remove("hidden");
    dropZone.classList.add("drop-zone-active");
  });

  ["dragleave", "drop"].forEach((eventName) => {
    messageInputArea.addEventListener(eventName, () => {
      dropZone.classList.add("hidden");
      dropZone.classList.remove("drop-zone-active");
    });
  });

  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFileUpload(files);
    dropZone.classList.add("hidden");
  });

  // --- File Input ---
  uploadButton.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", function () {
    if (this.files && this.files.length > 0) {
      handleFileUpload(this.files);
    }
  });

  // --- Sending the Message ---
  async function sendMessage() {
    const message = messageInput.value.trim();

    // Prevent sending empty messages when files are present
    if (!message && uploadedFiles.length === 0) {
      showFeedback("Please enter a message or upload files.", "error");
      return;
    }

    // Create FormData and append message and files
    const formData = new FormData();
    formData.append("message", message);
    uploadedFiles.forEach((file) => {
      formData.append("files", file);
    });

    alert("Send button clicked!");
    console.log("Preparing to send message:", message);
    console.log("Uploaded files:", uploadedFiles);

    // Disable send button
    sendButton.disabled = true;

    // Send the request
    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "X-CSRFToken": getCSRFToken(),
        },
        body: formData,
      });

      console.log("Response status:", response.status);

      if (!response.ok) {
        const errorData = await response.json();
        console.error("Error response:", errorData);
        showFeedback(errorData.error || "An error occurred.", "error");
        return;
      }

      const data = await response.json();
      console.log("Response data:", data);

      if (data.response) {
        appendAssistantMessage(data.response);
      } else {
        showFeedback(
          data.error || "An error occurred while processing your message.",
          "error"
        );
      }

      // Display excluded files
      if (data.excluded_files && data.excluded_files.length > 0) {
        showFeedback(
          `The following files were excluded: ${data.excluded_files.join(
            ", "
          )}`,
          "error"
        );
      }

      // Clear uploaded files after sending
      uploadedFiles = [];
      renderFileList(uploadedFiles);
    } catch (error) {
      console.error("Error sending message:", error);
      showFeedback("An error occurred. Please try again later.", "error");
    } finally {
      // Re-enable send button
      sendButton.disabled = false;
      messageInput.value = "";
    }
  }

  // --- Display Messages in the Chat ---
  function appendUserMessage(message) {
    const userMessageDiv = document.createElement("div");
    userMessageDiv.className =
      "flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end";
    userMessageDiv.innerHTML = `
      <div>
          <div class="bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
              <div class="text-sm markdown-content">${message}</div>
          </div>
          <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
      </div>
      <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
    `;
    userMessageDiv.querySelector(".markdown-content").innerHTML =
      renderMarkdown(message);
    chatBox.appendChild(userMessageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function appendAssistantMessage(message) {
    const assistantMessageDiv = document.createElement("div");
    assistantMessageDiv.className = "flex w-full mt-2 space-x-3 max-w-xs";
    assistantMessageDiv.innerHTML = `
      <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
      <div>
          <div class="bg-gray-300 p-3 rounded-r-lg rounded-bl-lg">
              <div class="text-sm markdown-content">${message}</div>
          </div>
          <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
      </div>
    `;
    assistantMessageDiv.querySelector(".markdown-content").innerHTML =
      renderMarkdown(message);
    chatBox.appendChild(assistantMessageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // --- Event Listeners ---
  sendButton.addEventListener("click", sendMessage);
  messageInput.addEventListener("keyup", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  newChatBtn?.addEventListener("click", async () => {
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
          window.location.href = "/chat_interface";
        }
      } else {
        showFeedback("Failed to create a new chat.", "error");
      }
    } catch (error) {
      console.error("Error creating new chat:", error);
      showFeedback("Error creating new chat.", "error");
    }
  });

  // --- Edit Model ---
  const editModelButton = document.getElementById("edit-model-btn");
  editModelButton?.addEventListener("click", async () => {
    const modelId = editModelButton.dataset.modelId;
    const updatedData = {
      name: "Updated Model Name", // Example data
      description: "Updated description",
    };

    try {
      const response = await fetch(`/models/${modelId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify(updatedData),
      });

      if (response.ok) {
        showFeedback("Model updated successfully.", "success");
      } else {
        const errorData = await response.json();
        showFeedback(errorData.error || "Failed to update model.", "error");
      }
    } catch (error) {
      console.error("Error updating model:", error);
      showFeedback("An error occurred while updating the model.", "error");
    }
  });
});
