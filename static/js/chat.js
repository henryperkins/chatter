// Enhanced logic to keep the usage panel connected above the chat input

"use strict";

let scrollFrame = null;

const CONFIG = {
    DEPENDENCY_TIMEOUT: 5000,
    STREAM_UPDATE_INTERVAL: 100,
    MAX_DEPENDENCY_ATTEMPTS: 50,
    O_SERIES_MODELS: ['o3-mini', 'o1', 'o1-mini', 'o1-preview'],
    DEBUG: true
};

// Dynamically position the usage panel above the chat input
function updateUsagePanelPosition() {
    const usagePanel = document.getElementById('usage-panel');
    const chatInput = document.getElementById('chat-input');
    if (!usagePanel || !chatInput) return;

    // Calculate how tall the chat input is and reposition usage panel just above it
    const inputRect = chatInput.getBoundingClientRect();
    // For a fixed position usage panel, set bottom equal to chat input's total height
    const chatInputHeight = inputRect.height || 0;

    // Update usage panel's bottom to place it just above the chat input
    usagePanel.style.position = 'fixed';
    usagePanel.style.left = '0';
    usagePanel.style.right = '0';
    usagePanel.style.bottom = `${chatInputHeight}px`;
    // Optional: bump up z-index if needed
    usagePanel.style.zIndex = '9999';

    // If there's any transform from visualViewport adjustments, reset usagePanel transform so it remains pinned
    usagePanel.style.transform = 'none';
}

// Visual viewport handling for input positioning
function handleViewportChanges() {
    const visualViewport = window.visualViewport;
    const chatInput = document.getElementById('chat-input');

    if (visualViewport && chatInput) {
        const viewportHeight = visualViewport.height;
        const offsetTop = visualViewport.offsetTop;
        const delta = window.innerHeight - viewportHeight - offsetTop;

        // Move chat input so it's visible above the keyboard
        chatInput.style.transform = `translateY(${Math.max(delta, 0)}px)`;
    }

    updateUsagePanelPosition();
}

// Attach these listeners to keep everything aligned on viewport change
if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', handleViewportChanges);
    window.visualViewport.addEventListener('scroll', handleViewportChanges);
}

// Also reposition usage panel when window resizes in normal situations
window.addEventListener('resize', updateUsagePanelPosition);

// ==========================================================================
// Existing chat.js code below
// ==========================================================================

async function createNewChat() {
    try {
        const sendBtn = document.getElementById('new-chat-btn');
        if (sendBtn) sendBtn.disabled = true;

        const response = await fetch('/chat/new', {
            method: 'POST',
            headers: {
                'X-CSRFToken': window.CHAT_CONFIG?.csrfToken,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to create new chat');
        }

        const data = await response.json();
        if (data.success && data.chat_id) {
            window.location.href = `/chat/chat_interface?chat_id=${data.chat_id}&new=true`;
        } else {
            throw new Error('Invalid response from server');
        }
    } catch (error) {
        console.error('New chat error:', error);
        window.MessageRenderer.showError(`Failed to create chat: ${error.message}`);
    } finally {
        const sendBtn = document.getElementById('new-chat-btn');
        if (sendBtn) sendBtn.disabled = false;
    }
}

/**
 * handlePotentialFetchResponse()
 */
async function handlePotentialFetchResponse(response) {
    if (response && typeof response === 'object' && 'ok' in response && 'status' in response) {
        if (!response.ok) {
            console.error('Full fetch response:', response);
            throw new Error(`Request failed: ${response.status}`);
        }
        return await response.json();
    } else {
        return response;
    }
}

// Normal response handler
async function handleNormalResponse(formData) {
    const message = formData.get('message') || '';
    const jsonData = {
        message,
        chat_id: window.CHAT_CONFIG.chatId
    };

    if (window.fileUploadManager?.uploadedFiles?.length > 0) {
        const uploadResponse = await fetch(`/api/files/upload/${window.CHAT_CONFIG.chatId}`, {
            method: 'POST',
            body: new FormData(document.getElementById('chat-form')),
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'X-CSRFToken': window.CHAT_CONFIG.csrfToken
            }
        });
        if (!uploadResponse.ok) {
            throw new Error(`File upload failed: ${uploadResponse.status}`);
        }
        const { file_ids: fileIds } = await uploadResponse.json();
        jsonData.file_ids = fileIds;
    }

    let fetchResponse;
    try {
        fetchResponse = await window.utils.fetchWithCSRF('/chat/send', {
            method: 'POST',
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'api-key': window.CHAT_CONFIG.azureToken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: jsonData
        });
    } catch (err) {
        console.error('Error calling fetchWithCSRF:', err);
        throw err;
    }

    let data;
    try {
        data = await handlePotentialFetchResponse(fetchResponse);
    } catch (err) {
        console.error('Error in handleNormalResponse:', err);
        throw err;
    }

    if (!data || typeof data !== 'object') {
        throw new Error('No valid JSON data returned from server');
    }
    if (!data.success && !data.message) {
        throw new Error('Request was not successful');
    }
    if (!data.message || typeof data.message !== 'object') {
        throw new Error('Invalid or empty "message" field in server response');
    }

    const { content, content_html: contentHtml } = data.message;
    if (!content || !contentHtml) {
        throw new Error('Empty content in response');
    }

    await window.MessageRenderer.appendAssistantMessage({
        content: content,
        content_html: contentHtml
    }, false);
    window.MessageRenderer.showSuccess('Assistant responded successfully');
}

// Streaming response handler
async function handleStreamingResponse(formData) {
    let accumulatedContent = '';
    let messageDiv = null;
    let buffer = '';

    try {
        const message = formData.get('message');
        const files = formData.getAll('files[]') || [];
        const hasMessage = message && message.trim().length > 0;
        const hasFiles = files && files.length > 0;

        if (!hasMessage && !hasFiles) {
            throw new Error('Please provide a message or upload files.');
        }

        const uploadedFiles = formData.getAll('files[]') || [];
        const jsonData = {
            message: message || '',
            files: uploadedFiles.map(file => file.id),
            chat_id: window.CHAT_CONFIG.chatId,
            stream: true
        };

        let response;
        try {
            response = await window.utils.fetchWithCSRF('/chat/send?stream=true', {
                method: 'POST',
                headers: {
                    'X-Chat-ID': window.CHAT_CONFIG.chatId,
                    'api-key': window.CHAT_CONFIG.azureToken,
                    'X-CSRFToken': window.CHAT_CONFIG.csrfToken,
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: jsonData
            });
        } catch (err) {
            console.error('Streaming error:', err);
            throw err;
        }

        if (!(response instanceof Response)) {
            if (!response.success) {
                throw new Error('Request was not successful (non-streaming server response).');
            }
            if (!response.message) {
                throw new Error('No "message" in non-streaming server response.');
            }
            const { content, content_html } = response.message;
            const nextMessage = content_html || content || 'No content';
            messageDiv = window.MessageRenderer.renderAssistantMessage(nextMessage, false);
            document.getElementById('chat-box').appendChild(messageDiv);
            window.MessageRenderer.showSuccess('Assistant responded successfully (non-stream fallback).');
            return;
        }

        if (!response.ok) {
            const text = await response.text();
            let errorMsg = `Server error: ${response.status}`;
            try {
                const errorData = JSON.parse(text);
                if (errorData.error) {
                    errorMsg = errorData.error;
                }
            } catch {
                // fallback
            }
            throw new Error(errorMsg);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let streamComplete = false;
        let updateQueue = [];
        let updateScheduled = false;

        const processUpdate = () => {
            if (updateQueue.length > 0) {
                const latestContent = updateQueue[updateQueue.length - 1];
                accumulatedContent = latestContent;

                if (!messageDiv) {
                    messageDiv = window.MessageRenderer.renderAssistantMessage(latestContent, true);
                    document.getElementById('chat-box').appendChild(messageDiv);
                } else {
                    const contentContainer = messageDiv.querySelector('[data-role="assistant-message"]');
                    if (contentContainer) {
                        contentContainer.textContent = latestContent;
                    }
                }

                updateQueue = [];
                updateScheduled = false;
            }
        };

        while (!streamComplete) {
            const { done, value } = await reader.read();
            if (done) {
                streamComplete = true;
                continue;
            }

            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop() || '';

            for (const event of events) {
                const match = event.match(/^data: (.*)/);
                if (!match) continue;

                try {
                    const parsed = JSON.parse(match[1]);
                    if (parsed.error) {
                        throw new Error(parsed.error);
                    }
                    if (parsed.content) {
                        accumulatedContent += parsed.content;
                        updateQueue.push(accumulatedContent);
                        if (!updateScheduled) {
                            updateScheduled = true;
                            requestAnimationFrame(processUpdate);
                        }
                    }
                } catch (err) {
                    throw new Error(`Stream parsing error: ${err.message}`);
                }
            }

            const chatBox = document.getElementById('chat-box');
            if (!chatBox) continue;
            const scrollPos = chatBox.scrollTop;
            const nearBottom = chatBox.scrollHeight - chatBox.clientHeight - scrollPos < 100;
            if (nearBottom) {
                cancelAnimationFrame(scrollFrame);
                scrollFrame = requestAnimationFrame(() => {
                    chatBox.scrollTop = chatBox.scrollHeight;
                });
            }
        }

        if (messageDiv) {
            window.MessageRenderer.finalizeAssistantMessage(messageDiv, accumulatedContent);
        }
        window.MessageRenderer.showSuccess('Assistant responded successfully (stream).');
    } catch (error) {
        window.MessageRenderer.showError(`API Error: ${error.message}`);
        if (messageDiv) {
            messageDiv.remove();
        }
    }
}

// Send a message
async function sendMessage(event) {
    if (event) {
        event.preventDefault();
    }
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');

    if (!messageInput || !sendButton) {
        window.MessageRenderer.showError('Chat interface not properly initialized');
        return;
    }
    if (sendButton.disabled) return;

    sendButton.disabled = true;
    try {
        const message = messageInput.value.trim();
        let uploadedFiles = [];

        if (window.fileUploadManager?.uploadedFiles?.length > 0) {
            try {
                uploadedFiles = await window.fileUploadManager.uploadFiles();
                if (!Array.isArray(uploadedFiles)) {
                    throw new Error('Invalid response from file upload');
                }
            } catch (uploadError) {
                window.MessageRenderer.showError('File upload failed: ' + (uploadError.message || 'Unknown error'), uploadError.file);
                throw uploadError;
            }
        }

        const formData = new FormData();
        formData.append('message', message);
        if (uploadedFiles.length > 0) {
            uploadedFiles.forEach(file => {
                formData.append('files[]', file);
            });
        }

        const modelSelect = document.getElementById('model-select');
        let modelSupportsStreaming = false;
        let isOSeriesModel = false;

        if (modelSelect && modelSelect.selectedOptions.length) {
            const selectedOption = modelSelect.selectedOptions[0];
            const modelType = selectedOption.dataset.modelType;
            isOSeriesModel = CONFIG.O_SERIES_MODELS.includes(modelType);
            modelSupportsStreaming = (modelType === 'o3-mini');
            window.CHAT_CONFIG.isOSeriesModel = isOSeriesModel;
        }

        window.MessageRenderer.appendUserMessage(message, uploadedFiles);
        messageInput.value = '';
        window.fileUploadManager?.clearFiles();
        window.MessageRenderer.showTypingIndicator();

        if (modelSupportsStreaming) {
            await handleStreamingResponse(formData);
        } else {
            await handleNormalResponse(formData);
        }

        if (window.tokenUsageManager) {
            await window.tokenUsageManager.handleNewMessage();
        }
    } catch (error) {
        window.monitoring?.logError('Error in sendMessage:', error);
        window.MessageRenderer.showError(error.message || 'Failed to send message');
    } finally {
        sendButton.disabled = false;
        window.MessageRenderer.removeTypingIndicator();
    }
}

async function startChat() {
    const tabButtons = document.querySelectorAll('.usage-tabs .tab');
    if (tabButtons.length > 0) {
        const panels = document.querySelectorAll('.panel-content');
        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                tabButtons.forEach(tb => tb.classList.remove('tab-active'));
                panels.forEach(p => p.classList.add('hidden'));
                btn.classList.add('tab-active');
                const targetId = btn.getAttribute('data-panel');
                document.getElementById(targetId).classList.remove('hidden');
            });
        });
    }

    const uploadTrigger = document.getElementById('upload-trigger');
    const fileInput = document.getElementById('file-upload');
    if (uploadTrigger && fileInput) {
        uploadTrigger.addEventListener('click', () => {
            fileInput.click();
        });
    }

    if (window.fileUploadManager) {
        window.fileUploadManager.onFilesChanged = updateFileList;
    }

    function updateFileList() {
        const fileList = document.getElementById('file-list');
        if (!fileList || !window.fileUploadManager?.uploadedFiles) return;

        fileList.innerHTML = window.fileUploadManager.uploadedFiles.map(file => `
            <div class="file-item">
                <div class="flex items-center gap-2 flex-1">
                    <i class="fas fa-file-alt text-gray-400"></i>
                    <span class="file-name">${file.name}</span>
                    <span class="file-size">${formatFileSize(file.size)}</span>
                </div>
                <button class="remove-btn" data-filename="${file.name}">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');

        fileList.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                window.fileUploadManager.removeFile(btn.dataset.filename);
            });
        });
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    try {
        const configDiv = document.getElementById('chat-config');
        if (!configDiv) {
            throw new Error('Chat configuration not found');
        }
        window.CHAT_CONFIG.isOSeriesModel = false;

        let attempts = 0;
        while (!window.MessageRenderer && attempts < CONFIG.MAX_DEPENDENCY_ATTEMPTS) {
            // wait for global scripts to load
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        if (!window.MessageRenderer) {
            throw new Error('MessageRenderer not available');
        }

        try {
            const FileUploadManagerClass = window.FileUploadManager;
            if (!FileUploadManagerClass) {
                throw new Error('FileUploadManager class not loaded');
            }
            if (!window.fileUploadManager) {
                const uploadButton = document.getElementById('file-upload');
                window.fileUploadManager = new FileUploadManagerClass(
                    configDiv.dataset.chatId,
                    configDiv.dataset.userId,
                    uploadButton
                );
            }

            const TokenUsageManagerClass = window.TokenUsageManager;
            if (!TokenUsageManagerClass) {
                throw new Error('TokenUsageManager class not loaded');
            }
            if (!window.tokenUsageManager && window.CHAT_CONFIG?.chatId) {
                window.tokenUsageManager = new TokenUsageManagerClass(window.CHAT_CONFIG);
                await window.tokenUsageManager.initialize();
            }
        } catch (error) {
            window.monitoring?.logError('Component init failed', error);
            window.MessageRenderer.showError('Failed to initialize chat components: ' + error.message);
            return;
        }

        if (window.fileUploadManager) {
            await window.fileUploadManager.initializeFileUpload();
        }

        const modelSelect = document.getElementById('model-select');
        if (modelSelect) {
            const modelIcon = document.querySelector('.model-selector svg');
            modelSelect.addEventListener('change', () => {
                const selected = modelSelect.options[modelSelect.selectedIndex];
                if (modelIcon && selected.dataset.color) {
                    modelIcon.style.color = selected.dataset.color;
                }
            });

            modelSelect.addEventListener('change', async () => {
                const selectedOption = modelSelect.selectedOptions[0];
                const modelType = selectedOption.dataset.modelType;
                window.CHAT_CONFIG.isOSeriesModel = CONFIG.O_SERIES_MODELS.includes(modelType);

                if (modelIcon && selectedOption.dataset.color) {
                    modelIcon.style.color = selectedOption.dataset.color;
                }

                const newModelId = modelSelect.value;
                const chatId = window.CHAT_CONFIG.chatId;
                try {
                    const resp = await fetch('/chat/update_model', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                        },
                        body: JSON.stringify({ chat_id: chatId, model_id: newModelId })
                    });
                    const data = await resp.json();
                    if (data.success) {
                        window.MessageRenderer.showSuccess('Chat model updated');
                    } else {
                        window.MessageRenderer.showError(data.error || 'Failed to update chat model');
                    }
                } catch (err) {
                    window.MessageRenderer.showError('Failed to update chat model');
                }
            });
        }

        const messageInput = document.getElementById('message-input');
        const sendButton = document.getElementById('send-button');
        const chatForm = document.getElementById('chat-form');
        const newChatBtn = document.getElementById('new-chat-btn');
        const mobileChatSelector = document.getElementById('mobile-chat-selector');

        if (newChatBtn) {
            newChatBtn.addEventListener('click', (e) => {
                e.preventDefault();
                createNewChat();
            });
        }

        if (mobileChatSelector) {
            mobileChatSelector.addEventListener('change', (e) => {
                const selectedValue = e.target.value;
                if (selectedValue === 'new') {
                    createNewChat();
                } else {
                    window.location.href = `/chat/chat_interface?chat_id=${selectedValue}`;
                }
            });
        }

        if (chatForm) {
            chatForm.addEventListener('submit', (e) => {
                e.preventDefault();
                sendMessage(e);
            });
        }

        if (messageInput) {
            const debounce = (func, wait) => {
                let timeout;
                return function executedFunction(...args) {
                    const later = () => {
                        clearTimeout(timeout);
                        func(...args);
                    };
                    clearTimeout(timeout);
                    timeout = setTimeout(later, wait);
                };
            };

            const debouncedKeydown = debounce(e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage(e);
                }
            }, 100);

            messageInput.addEventListener('keydown', debouncedKeydown);
        }

        document.querySelectorAll('button[aria-label="Delete chat"]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const chatId = btn.getAttribute('data-chat-id');
                if (!chatId) return;
                if (!confirm('Are you sure you want to delete this chat?')) return;
                try {
                    const resp = await fetch(`/chat/delete_chat/${chatId}`, {
                        method: 'DELETE',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                        }
                    });
                    const data = await resp.json();
                    if (data.success) {
                        window.MessageRenderer.showSuccess('Chat deleted');
                        window.location.href = '/chat/interface';
                    } else {
                        window.MessageRenderer.showError(data.error);
                    }
                } catch (err) {
                    window.MessageRenderer.showError('Delete failed');
                }
            });
        });

        const editTitleBtn = document.getElementById('edit-title-btn');
        if (editTitleBtn) {
            editTitleBtn.addEventListener('click', async () => {
                const newTitle = prompt('Enter new chat title:');
                if (!newTitle || newTitle.trim() === '') return;
                try {
                    const resp = await fetch(`/chat/update_chat_title/${window.CHAT_CONFIG.chatId}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                        },
                        body: JSON.stringify({ title: newTitle.trim() })
                    });
                    const data = await resp.json();
                    if (data.success) {
                        window.MessageRenderer.showSuccess('Chat title updated');
                        const trimmedTitle = newTitle.trim();

                        const mobileSel = document.getElementById('mobile-chat-selector');
                        if (mobileSel) {
                            const opt = mobileSel.querySelector(`option[value="${window.CHAT_CONFIG.chatId}"]`);
                            if (opt) {
                                opt.textContent = trimmedTitle;
                            }
                        }

                        const desktopTab = document.querySelector(`.chat-tab[data-chat-id="${window.CHAT_CONFIG.chatId}"] span`);
                        if (desktopTab) {
                            desktopTab.textContent = trimmedTitle;
                        }
                        document.title = `Chat - ${trimmedTitle}`;
                    } else {
                        window.MessageRenderer.showError(data.error);
                    }
                } catch (err) {
                    window.MessageRenderer.showError('Failed to update chat title');
                }
            });
        }

        document.querySelectorAll('.copy-button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const rawContent = btn.getAttribute('data-raw-content');
                if (rawContent && window.utils?.copyToClipboard) {
                    window.utils.copyToClipboard(rawContent);
                }
            });
        });

        document.querySelectorAll('.regenerate-button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm('Do you want to regenerate the assistant response?')) {
                    window.MessageRenderer.showSuccess('Regeneration triggered (feature not fully implemented)');
                }
            });
        });

        // Make sure the usage panel is placed above the chat input on load
        handleViewportChanges();
        updateUsagePanelPosition();
    } catch (error) {
        window.monitoring?.logError('Failed to initialize chat:', error);
        window.MessageRenderer.showError(error.message);
    }
}

document.addEventListener('DOMContentLoaded', startChat);
