/* static/js/chat.js */

(function () {
    console.log("chat.js loaded");

    // Constants for file handling
    let uploadedFiles = [];
    const MAX_FILES = 5;
    const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
    const ALLOWED_FILE_TYPES = [
        "text/plain", "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/x-python", "application/javascript", "text/markdown",
        "image/jpeg", "image/png",
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
    const md = window.markdownit({
        html: true,
        linkify: true,
        typographer: true,
        breaks: true,
        highlight: function (str, lang) {
            if (lang && Prism.languages[lang]) {
                try {
                    return `<pre class="language-${lang}"><code>${Prism.highlight(
                        str,
                        Prism.languages[lang],
                        lang
                    )}</code></pre>`;
                } catch (e) {
                    console.error(e);
                }
            }
            return `<pre class="language-plaintext"><code>${md.utils.escapeHtml(str)}</code></pre>`;
        },
    });

    // Render Markdown content safely
    function renderMarkdown(content) {
        const html = md.render(content);
        if (typeof DOMPurify !== "undefined" && DOMPurify.sanitize) {
            return DOMPurify.sanitize(html, {
                USE_PROFILES: { html: true },
                ALLOWED_TAGS: [
                    "p", "strong", "em", "br", "ul", "ol", "li",
                    "a", "img", "pre", "code", "blockquote", "h1", "h2",
                    "h3", "h4", "h5", "h6", "hr", "table", "thead", "tbody",
                    "tr", "th", "td"
                ],
                ALLOWED_ATTR: [
                    "href", "target", "rel", "src", "alt",
                    "class", "style", "id"
                ],
            });
        }
        return html
            .replace(/<script.*?>.*?<\/script>/gi, "")
            .replace(/on\w+="[^"]*"/gi, "");
    }

    // Show feedback to the user
    window.showFeedback = function(message, type = "success") {
        const feedbackDiv = document.getElementById("feedback-message");
        if (!feedbackDiv) return;

        feedbackDiv.textContent = message;
        feedbackDiv.className = `fixed bottom-4 right-4 p-4 rounded-lg ${
            type === "success"
                ? "bg-green-100 border border-green-400 text-green-700"
                : "bg-red-100 border border-red-400 text-red-700"
        }`;
        feedbackDiv.classList.remove("hidden");
        setTimeout(() => feedbackDiv.classList.add("hidden"), 3000);
    };

    // Get CSRF token
    window.getCSRFToken = function() {
        const csrfTokenMetaTag = document.querySelector('meta[name="csrf-token"]');
        return csrfTokenMetaTag ? csrfTokenMetaTag.getAttribute("content") : "";
    };

    // File Handling Functions
    function handleFileUpload(files) {
        const filesArray = Array.from(files);
        if (uploadedFiles.length + filesArray.length > MAX_FILES) {
            showFeedback(`You can upload up to ${MAX_FILES} files at a time.`, "error");
            return;
        }

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
                        <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" />
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
        formData.append("model_id", modelSelect.value);
        uploadedFiles.forEach((file) => {
            formData.append("files[]", file);
        });

        sendButton.disabled = true;
        messageInput.disabled = true;

        if (uploadedFiles.length > 0) {
            uploadProgress.classList.remove("hidden");
            uploadProgressBar.style.width = "0%";
        }

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
            uploadProgress.classList.add("hidden");
            sendButton.disabled = false;
            messageInput.disabled = false;

            if (data.response) {
                appendAssistantMessage(data.response);
                uploadedFiles = [];
                renderFileList();
            }
            if (data.excluded_files && data.excluded_files.length > 0) {
                showFeedback(
                    `Some files were excluded: ${data.excluded_files.join(", ")}`,
                    "error"
                );
            }
        } catch (error) {
            uploadProgress.classList.add("hidden");
            sendButton.disabled = false;
            messageInput.disabled = false;

            console.error("Error sending message:", error);
            const errorMsg = error.response?.data?.error || "An error occurred.";
            showFeedback(errorMsg, "error");
        }
    }

    function appendUserMessage(message) {
        const userMessageDiv = document.createElement("div");
        userMessageDiv.className = "flex w-full mt-2 space-x-3 max-w-3xl ml-auto justify-end";
        userMessageDiv.innerHTML = `
            <div class="flex-grow">
                <div class="bg-blue-600 text-white p-3 rounded-l-lg rounded-br-lg">
                    <div class="text-sm markdown-content prose prose-invert max-w-none"></div>
                </div>
                <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
        `;
        userMessageDiv.querySelector(".markdown-content").innerHTML = renderMarkdown(message);
        chatBox.appendChild(userMessageDiv);
        Prism.highlightAllUnder(userMessageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendAssistantMessage(message) {
        const assistantMessageDiv = document.createElement("div");
        assistantMessageDiv.className = "flex w-full mt-2 space-x-3 max-w-3xl";
        assistantMessageDiv.innerHTML = `
            <div class="flex-shrink-0 h-10 w-10 rounded-full bg-gray-300"></div>
            <div class="flex-grow">
                <div class="bg-gray-100 dark:bg-gray-800 p-3 rounded-r-lg rounded-bl-lg">
                    <div class="text-sm markdown-content prose dark:prose-invert max-w-none"></div>
                </div>
                <span class="text-xs text-gray-500 leading-none">${new Date().toLocaleTimeString()}</span>
            </div>
        `;
        assistantMessageDiv.querySelector(".markdown-content").innerHTML = renderMarkdown(message);
        chatBox.appendChild(assistantMessageDiv);
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

        updateEditButtonState();

        modelSelect.addEventListener("change", function () {
            updateEditButtonState();
            if (chatBox.children.length > 0) {
                const formData = new FormData();
                formData.append("model_id", this.value);
                fetch("/chat", {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": getCSRFToken(),
                    },
                    body: formData,
                });
            }
        });

        editModelButton.addEventListener("click", function () {
            const modelId = this.dataset.modelId;
            if (modelId) {
                window.location.href = `/models/edit-model/${modelId}`;
            }
        });
    }

    // New Chat Button
    if (newChatBtn) {
        newChatBtn.addEventListener("click", async () => {
            try {
                const modelId = modelSelect.value;
                const response = await fetch("/new_chat", {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": getCSRFToken(),
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ model_id: modelId })
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

    // Chat Deletion
    window.deleteChat = function(chatId) {
        if (confirm('Are you sure you want to delete this chat?')) {
            fetch(`/delete_chat/${chatId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (window.location.href.includes(chatId)) {
                        window.location.href = '/chat_interface';
                    } else {
                        const chatElement = document.querySelector(`a[href*="${chatId}"]`).parentElement;
                        chatElement.classList.add('chat-item-exit');
                        setTimeout(() => {
                            chatElement.remove();
                            const dateGroup = chatElement.previousElementSibling;
                            if (dateGroup && dateGroup.classList.contains('text-xs') && !dateGroup.nextElementSibling) {
                                dateGroup.remove();
                            }
                        }, 300);
                    }
                } else {
                    showFeedback('Failed to delete chat', 'error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showFeedback('An error occurred while deleting the chat', 'error');
            });
        }
    };

    // File Drop Zone
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

    // Mobile Menu
    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", function () {
            offCanvasMenu.classList.toggle("hidden");
            overlay.classList.toggle("hidden");
        });
    }

    if (offCanvasClose) {
        offCanvasClose.addEventListener("click", function () {
            offCanvasMenu.classList.add("hidden");
            overlay.classList.add("hidden");
        });
    }

    if (overlay) {
        overlay.addEventListener("click", function () {
            offCanvasMenu.classList.add("hidden");
            overlay.classList.add("hidden");
        });
    }

    // Mobile Gestures
    let touchstartX = 0;
    let touchendX = 0;

    function handleGesture() {
        if (touchendX < touchstartX) {
            offCanvasMenu.classList.add("hidden");
            overlay.classList.add("hidden");
        }
    }

    document.addEventListener("touchstart", function (event) {
        touchstartX = event.changedTouches[0].screenX;
    }, false);

    document.addEventListener("touchend", function (event) {
        touchendX = event.changedTouches[0].screenX;
        handleGesture();
    }, false);

    // Mobile Interactions
    function handleMobileInteractions() {
        chatBox.addEventListener("touchstart", handleTouchStart, false);
        chatBox.addEventListener("touchmove", handleTouchMove, false);

        let xDown = null;
        let yDown = null;

        function handleTouchStart(evt) {
            const firstTouch = evt.touches[0];
            xDown = firstTouch.clientX;
            yDown = firstTouch.clientY;
        }

        function handleTouchMove(evt) {
            if (!xDown || !yDown) return;

            const xUp = evt.touches[0].clientX;
            const yUp = evt.touches[0].clientY;

            const xDiff = xDown - xUp;
            const yDiff = yDown - yUp;

            if (Math.abs(xDiff) > Math.abs(yDiff)) {
                if (xDiff > 0) {
                    console.log("Left swipe detected");
                } else {
                    console.log("Right swipe detected");
                }
            } else if (yDiff > 0) {
                console.log("Up swipe detected");
            } else {
                console.log("Down swipe detected");
            }

            xDown = null;
            yDown = null;
        }
    }

    handleMobileInteractions();
})();
