// static/js/chat.js

(function () {
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
    const fileInput = document.getElementById("file-input");
    const uploadButton = document.getElementById("upload-button");
    const modelSelect = document.getElementById("model-select");
    const editModelButton = document.getElementById("edit-model-btn");
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const offCanvasMenu = document.getElementById("off-canvas-menu");
    const offCanvasClose = document.getElementById("off-canvas-close");
    const overlay = document.getElementById("overlay");

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
            .then(response => {
                clearTimeout(timeoutId);
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Update the title in the UI
                    const chatTitleElement = document.getElementById("chat-title");
                    if (chatTitleElement) {
                        chatTitleElement.textContent = `${newTitle} - ${chatTitleElement.textContent.split(" - ")[1]}`;
                    }
                    alert("Chat title updated successfully!");
                } else {
                    alert("Failed to update chat title");
                }
            })
            .catch(error => {
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

    // Function to delete a chat
    function deleteChat(chatId) {
        console.log("deleteChat triggered for chatId:", chatId);
        if (confirm('Are you sure you want to delete this chat?')) {
            console.log("Sending request to delete chat:", chatId);
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000); // 15-second timeout
            fetch(`/delete_chat/${chatId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                signal: controller.signal,
            })
            .then(response => {
                clearTimeout(timeoutId);
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // If we're currently viewing the deleted chat, redirect to a new chat
                    if (window.location.href.includes(chatId)) {
                        window.location.href = '/chat_interface';
                    } else {
                        // Otherwise just remove the chat from the list with animation
                        const chatElement = document.querySelector(`a[href*="${chatId}"]`).parentElement;
                        chatElement.classList.add('chat-item-exit');
                        setTimeout(() => {
                            chatElement.remove();
                            // Check if the date group is now empty
                            const dateGroup = chatElement.previousElementSibling;
                            if (dateGroup && dateGroup.classList.contains('text-xs') && !dateGroup.nextElementSibling) {
                                dateGroup.remove();
                            }
                        }, 300);
                    }
                } else {
                    alert('Failed to delete chat');
                }
            })
            .catch(error => {
                clearTimeout(timeoutId);
                if (error.name === 'AbortError') {
                    alert('Request timed out. Please try again.');
                } else {
                    console.error('Error:', error);
                    alert('An error occurred while deleting the chat');
                }
            });
        }
    }

    // Expose deleteChat and editChatTitle functions globally if needed
    window.deleteChat = deleteChat;
    window.editChatTitle = editChatTitle;

})();
