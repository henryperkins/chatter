/* static/js/chat.js */

// Constants for file handling
let uploadedFiles = [];
const MAX_FILES = 5;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
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

// Helper Functions
function adjustTextareaHeight(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
}

function renderMarkdown(content) {
    return DOMPurify.sanitize(marked.parse(content));
}

// Show feedback to the user (re-usable)
function showFeedback(message, type = "success") {
    const feedbackMessage = document.getElementById("feedback-message");
    feedbackMessage.textContent = message;
    feedbackMessage.className = `fixed bottom-4 right-4 p-4 rounded-lg ${
        type === "success"
            ? "bg-green-100 border border-green-400 text-green-700"
            : "bg-red-100 border border-red-400 text-red-700"
    }`;
    feedbackMessage.classList.remove("hidden");
    setTimeout(() => feedbackMessage.classList.add("hidden"), 3000);
}

// Retrieve the CSRF token from a meta tag if your Flask app uses CSRF protection
function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content");
}

// File Handling Functions
function handleFileUpload(files) {
    const filesArray = Array.from(files);

    // Check total count
    if (uploadedFiles.length + filesArray.length > MAX_FILES) {
        showFeedback(`You can upload up to ${MAX_FILES} files at a time.`, "error");
        return;
    }

    // Validate file type & size
    const validFiles = filesArray.filter((file) => {
        if (!ALLOWED_FILE_TYPES.includes(file.type)) {
            showFeedback(`File type not allowed: ${file.name}`, "error");
            return false;
        }
        if (file.size > MAX_FILE_SIZE) {
            showFeedback(`File ${file.name} exceeds the 10MB size limit.`, "error");
            return false;
        }
        return true;
    });

    uploadedFiles = uploadedFiles.concat(validFiles);
    renderFileList();

    if (validFiles.length > 0) {
        showFeedback(`${validFiles.length} file(s) queued for upload.`, "success");
    }
}

function renderFileList() {
    if (!fileListDiv) return;

    fileListDiv.innerHTML = "";
    uploadedFiles.forEach((file, index) => {
        const fileDiv = document.createElement("div");
        fileDiv.className = "flex items-center justify-between bg-white px-2 py-1 rounded border text-sm";
        fileDiv.innerHTML = `
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-1 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"/>
                </svg>
                ${file.name}
            </div>
            <button class="text-red-500 hover:text-red-700 remove-file-button" data-index="${index}">
                Remove
            </button>
        `;
        fileListDiv.appendChild(fileDiv);
    });

    // Show/hide uploaded files container
    if (uploadedFilesDiv) {
        if (uploadedFiles.length > 0) {
            uploadedFilesDiv.classList.remove("hidden");
        } else {
            uploadedFilesDiv.classList.add("hidden");
        }
    }

    // Attach event listeners for removing files
    document.querySelectorAll(".remove-file-button").forEach((button) => {
        button.addEventListener("click", function() {
            const index = parseInt(this.dataset.index);
            uploadedFiles.splice(index, 1);
            renderFileList();
        });
    });
}

// Message Handling Functions
async function sendMessage() {
    const message = messageInput.value.trim();

    // Check if either a message or files are present
    if (!message && uploadedFiles.length === 0) {
        showFeedback("Please enter a message or upload files.", "error");
        return;
    }

    // Append the user's message to the chat window if not empty
    if (message) {
        appendUserMessage(message);
        messageInput.value = "";
        adjustTextareaHeight(messageInput);
    }

    // Prepare form data
    const formData = new FormData();
    formData.append("message", message);
    uploadedFiles.forEach((file) => {
        formData.append("files[]", file);
    });
    formData.append("csrf_token", getCSRFToken());

    sendButton.disabled = true;
    messageInput.disabled = true;

    // Show the upload progress bar if there are files
    if (uploadedFiles.length > 0) {
        uploadProgress.classList.remove("hidden");
        uploadProgressBar.style.width = "0%";
    }

    // If using URL-based chat_id:
    // const sendMessageUrl = `/chat?chat_id=${chatId}`;
    // If using session-based approach (default from your code):
    const sendMessageUrl = "/chat";

    try {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", sendMessageUrl, true);

        xhr.upload.addEventListener("progress", function(event) {
            if (event.lengthComputable) {
                const percentComplete = (event.loaded / event.total) * 100;
                uploadProgressBar.style.width = `${percentComplete}%`;
            }
        });

        xhr.addEventListener("load", function() {
            uploadProgress.classList.add("hidden");
            sendButton.disabled = false;
            messageInput.disabled = false;

            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                if (data.response) {
                    appendAssistantMessage(data.response);
                    // Clear the file list on success
                    uploadedFiles = [];
                    renderFileList();
                }
                if (data.excluded_files && data.excluded_files.length > 0) {
                    showFeedback(
                        `Some files were excluded: ${data.excluded_files.join(", ")}`,
                        "error"
                    );
                }
            } else {
                let errorMsg = "An error occurred.";
                try {
                    const errorData = JSON.parse(xhr.responseText);
                    errorMsg = errorData.error || errorMsg;
                } catch (parseErr) {
                    // fallback
                }
                showFeedback(errorMsg, "error");
            }
        });

        xhr.addEventListener("error", function() {
            uploadProgress.classList.add("hidden");
            sendButton.disabled = false;
            messageInput.disabled = false;
            showFeedback("An error occurred while sending the message.", "error");
        });

        xhr.send(formData);
    } catch (error) {
        console.error("Error sending message:", error);
        uploadProgress.classList.add("hidden");
        sendButton.disabled = false;
        messageInput.disabled = false;
        showFeedback("An error occurred. Please try again later.", "error");
    }
}

function appendUserMessage(message) {
    const userMessageDiv = document.createElement("div");
    userMessageDiv.className = "flex w-full mt-2 space-x-3 max-w-xs ml-auto justify-end";
    userMessageDiv.innerHTML = `
        <div>
            <div class="bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                <div class="text-sm markdown-content">${message}</div>
            </div>
            <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
        </div>
        <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
    `;
    userMessageDiv.querySelector(".markdown-content").innerHTML = renderMarkdown(message);
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
    assistantMessageDiv.querySelector(".markdown-content").innerHTML = renderMarkdown(message);
    chatBox.appendChild(assistantMessageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Event Listeners
if (messageInput) {
    messageInput.addEventListener("input", function() {
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
    sendButton.addEventListener("click", sendMessage);
}

if (fileInput && uploadButton) {
    uploadButton.addEventListener("click", () => {
        fileInput.click();
    });
    fileInput.addEventListener("change", function() {
        if (this.files && this.files.length > 0) {
            handleFileUpload(this.files);
        }
    });
}

// Model Selection and Editing
if (modelSelect && editModelButton) {
    modelSelect.addEventListener("change", function() {
        const selectedModelId = this.value;
        if (selectedModelId) {
            editModelButton.dataset.modelId = selectedModelId;
            editModelButton.disabled = false;
        } else {
            delete editModelButton.dataset.modelId;
            editModelButton.disabled = true;
        }
    });

    editModelButton.addEventListener("click", function() {
        const modelId = this.dataset.modelId;
        if (modelId) {
            window.location.href = `/edit-model/${modelId}`;
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
                    // If you want to pass the new chat ID via URL:
                    // window.location.href = `/chat_interface?chat_id=${data.chat_id}`;
                    // Otherwise, rely on session-based approach:
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
}

// Drag and Drop
const dropZone = document.getElementById("drop-zone");
const messageInputArea = document.querySelector(".message-input-area");

if (dropZone && messageInputArea) {
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
}
