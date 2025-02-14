// Enhanced chat interface with mobile optimizations

'use strict';

let scrollFrame = null;

const CONFIG = {
    DEPENDENCY_TIMEOUT: 5000,
    STREAM_UPDATE_INTERVAL: 100,
    MAX_DEPENDENCY_ATTEMPTS: 50,
    O_SERIES_MODELS: ['o3-mini', 'o1', 'o1-mini', 'o1-preview'],
    DEBUG: true,
};

// -----------------------------------------------------------------------------
// Enhanced usage panel management
// -----------------------------------------------------------------------------
class UsagePanelManager {
    constructor() {
        this.panel = document.getElementById('usage-panel');
        this.chatInput = document.getElementById('chat-input');
        this.tabs = document.querySelectorAll('.usage-tabs .tab');
        this.panels = document.querySelectorAll('.panel-content');
        this.dragStartY = 0;
        this.startHeight = 0;
        this.currentHeight = 0;
        this.isExpanded = false;

        this.setupEventListeners();
        this.setupTouchHandling();
        
        // Set initial active tab
        const firstTab = document.querySelector('.usage-tabs .tab');
        const firstPanelId = firstTab?.getAttribute('data-panel'); 
        if (firstTab && firstPanelId) {
            this.switchTab(firstTab, firstPanelId);
        }
    }

    setupEventListeners() {
        // Tab switching with loading states
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const targetId = tab.getAttribute('data-panel');
                this.switchTab(tab, targetId);
            });
        });

        // Add handle for touch/drag interactions
        const handle = document.createElement('div');
        handle.className = 'panel-handle';
        this.panel.insertBefore(handle, this.panel.firstChild);
    }

    setupTouchHandling() {
        const handle = this.panel.querySelector('.panel-handle');
        if (!handle) return;

        handle.addEventListener('touchstart', (e) => {
            this.dragStartY = e.touches[0].clientY;
            this.startHeight = this.panel.offsetHeight;
            this.panel.classList.add('dragging');
        });

        handle.addEventListener('touchmove', (e) => {
            if (!this.dragStartY) return;
            
            const deltaY = this.dragStartY - e.touches[0].clientY;
            const newHeight = Math.min(
                Math.max(this.startHeight + deltaY, 60),
                window.innerHeight * 0.5
            );
            
            this.panel.style.height = `${newHeight}px`;
            this.currentHeight = newHeight;
        });

        handle.addEventListener('touchend', () => {
            this.dragStartY = 0;
            this.panel.classList.remove('dragging');
            
            if (this.currentHeight > 100) {
                this.expand();
            } else {
                this.collapse();
            }
        });
    }

    switchTab(selectedTab, targetId) {
        // Remove active class from all tabs
        this.tabs.forEach(t => t.classList.remove('tab-active'));
        
        // Add active class to selected tab
        selectedTab.classList.add('tab-active');
        
        // Hide all panels
        document.querySelectorAll('.panel-content').forEach(panel => {
            if (panel.id === targetId) {
                panel.style.display = 'block';
                panel.classList.remove('hidden');
            } else {
                panel.style.display = 'none';
                panel.classList.add('hidden');
            }
        });
    }

    expand() {
        this.panel.classList.add('expanded');
        this.panel.classList.remove('collapsed');
        this.isExpanded = true;
    }

    collapse() {
        this.panel.classList.remove('expanded');
        this.panel.classList.add('collapsed');
        this.isExpanded = false;
    }

    toggle() {
        if (this.isExpanded) {
            this.collapse();
        } else {
            this.expand();
        }
    }

    updatePosition() {
        if (!this.panel || !this.chatInput) return;

        const inputRect = this.chatInput.getBoundingClientRect();
        const chatInputHeight = inputRect.height || 0;

        this.panel.style.position = 'fixed';
        this.panel.style.left = '0';
        this.panel.style.right = '0';
        this.panel.style.bottom = `${chatInputHeight}px`;
        this.panel.style.zIndex = '1100';
    }
}

// -----------------------------------------------------------------------------
// Global usage panel manager and helper functions
// -----------------------------------------------------------------------------
let usagePanelManager;

function updateUsagePanelPosition() {
    if (usagePanelManager) {
        usagePanelManager.updatePosition();
    }
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

// Attach viewport listeners
if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', handleViewportChanges);
    window.visualViewport.addEventListener('scroll', handleViewportChanges);
}
window.addEventListener('resize', updateUsagePanelPosition);

// -----------------------------------------------------------------------------
// Chat Interface Initialization
// -----------------------------------------------------------------------------
async function startChat() {
    try {
        // Initialize usage panel manager
        usagePanelManager = new UsagePanelManager();
        
        // Handle token usage updates
        if (window.tokenUsageManager) {
            const tokenPanel = document.getElementById('token-usage-panel');
            const tokenTab = document.querySelector('[data-panel="token-usage-panel"]');
            
            window.tokenUsageManager.onUpdateStart = () => {
                tokenTab?.classList.add('loading');
                tokenPanel?.classList.add('loading');
            };
            
            window.tokenUsageManager.onUpdateComplete = () => {
                tokenTab?.classList.remove('loading');
                tokenPanel?.classList.remove('loading');
            };
        }

        // Handle file upload progress and file list updates
        if (window.fileUploadManager) {
            window.fileUploadManager.onProgress = (file, progress) => {
                const progressBar = document.querySelector(`[data-file-id="${file.id}"] .file-progress-bar`);
                if (progressBar) {
                    progressBar.style.width = `${progress}%`;
                }
            };

            window.fileUploadManager.onFilesChanged = (files) => {
                if (typeof fileListUpdateDebounce === 'function') {
                    fileListUpdateDebounce(files);
                }
            };
        }

        // Initialize components
        const configDiv = document.getElementById('chat-config');
        if (!configDiv) {
            throw new Error('Chat configuration not found');
        }

        // Wait for dependencies (e.g. MessageRenderer)
        let attempts = 0;
        while (!window.MessageRenderer && attempts < CONFIG.MAX_DEPENDENCY_ATTEMPTS) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        if (!window.MessageRenderer) {
            throw new Error('MessageRenderer not available');
        }

        // Initialize managers (file upload and token usage)
        try {
            if (!window.fileUploadManager) {
                const uploadButton = document.getElementById('upload-trigger');
                if (!uploadButton) {
                    console.error('Upload button not found');
                    throw new Error('Upload button not found');
                }
                
                console.log('Initializing FileUploadManager');
                window.fileUploadManager = new window.FileUploadManager(
                    configDiv.dataset.chatId,
                    configDiv.dataset.userId,
                    uploadButton
                );
                
                // Initialize file upload manager
                try {
                    await window.fileUploadManager.initializeFileUpload();
                    console.log('FileUploadManager initialized');
                } catch (error) {
                    console.error('Failed to initialize FileUploadManager:', error);
                    throw error;
                }
            }

            if (!window.tokenUsageManager && window.CHAT_CONFIG?.chatId) {
                window.tokenUsageManager = new window.TokenUsageManager(window.CHAT_CONFIG);
                await window.tokenUsageManager.initialize();
            }
        } catch (error) {
            window.monitoring?.logError('Component init failed', error);
            window.MessageRenderer.showError('Failed to initialize chat components: ' + error.message);
            return;
        }

        // Setup UI event listeners
        setupUIEventListeners();

        // Make sure the usage panel is positioned correctly
        handleViewportChanges();
        updateUsagePanelPosition();

    } catch (error) {
        window.monitoring?.logError('Failed to initialize chat:', error);
        window.MessageRenderer.showError(error.message);
    }
}

// -----------------------------------------------------------------------------
// UI Event Listeners
// -----------------------------------------------------------------------------
function setupUIEventListeners() {
    const messageInput = document.getElementById('message-input');
    const chatForm = document.getElementById('chat-form');
    const newChatBtn = document.getElementById('new-chat-btn');
    const modelSelectorBtn = document.getElementById('model-selector-btn');
    const modelDropdown = document.getElementById('model-dropdown');
    const chatSelectorBtn = document.getElementById('chat-selector-btn');
    const chatListDropdown = document.getElementById('chat-list-dropdown');
    const editTitleBtn = document.getElementById('edit-title-btn');

    // Chat list item navigation
    if (chatListDropdown) {
        chatListDropdown.querySelectorAll('button[data-chat-url]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const url = btn.dataset.chatUrl;
                if (url) {
                    window.location.href = url;
                }
            });
        });
    }

    // Chat list dropdown
    if (chatSelectorBtn && chatListDropdown) {
        chatSelectorBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            chatListDropdown.classList.toggle('hidden');
        });
        
        document.addEventListener('click', (evt) => {
            if (!chatListDropdown.contains(evt.target) && evt.target !== chatSelectorBtn) {
                chatListDropdown.classList.add('hidden');
            }
        });
    }

    // Model selection dropdown
    if (modelSelectorBtn && modelDropdown) {
        modelSelectorBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            modelDropdown.classList.toggle('hidden');
        });
        
        document.addEventListener('click', (evt) => {
            if (!modelDropdown.contains(evt.target) && evt.target !== modelSelectorBtn) {
                modelDropdown.classList.add('hidden');
            }
        });

        // Model selection buttons
        modelDropdown.querySelectorAll('button[data-model-id]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const modelId = btn.dataset.modelId;
                try {
                    const resp = await fetch('/chat/update_model', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                        },
                        body: JSON.stringify({
                            chat_id: window.CHAT_CONFIG.chatId,
                            model_id: modelId
                        })
                    });
                    const data = await resp.json();
                    if (data.success) {
                        window.MessageRenderer.showSuccess('Chat model updated');
                        modelSelectorBtn.querySelector('span').textContent = btn.textContent.trim();
                        modelDropdown.classList.add('hidden');
                    } else {
                        window.MessageRenderer.showError(data.error || 'Failed to update chat model');
                    }
                } catch (err) {
                    window.MessageRenderer.showError('Failed to update chat model');
                }
            });
        });
    }

    // File upload handling is now managed by FileUploadManager

    // Chat form submission
    if (chatForm) {
        chatForm.addEventListener('submit', handleSubmit);
    }

    // Message input handling with debounce
    if (messageInput) {
        const debouncedKeydown = debounce(handleKeydown, 100);
        messageInput.addEventListener('keydown', debouncedKeydown);
    }

    // New chat button
    if (newChatBtn) {
        newChatBtn.addEventListener('click', (e) => {
            e.preventDefault();
            createNewChat();
        });
    }

    if (modelDropdown) {
        modelDropdown.querySelectorAll('button[data-model-id]').forEach((btn) => {
            btn.addEventListener('click', handleModelChange);
        });
    }

    // Edit title button
    if (editTitleBtn) {
        editTitleBtn.addEventListener('click', handleEditTitle);
    }

    // Copy buttons
    document.querySelectorAll('.copy-button').forEach(btn => {
        btn.addEventListener('click', handleCopyClick);
    });

    // Delete chat buttons
    document.querySelectorAll('button[aria-label="Delete chat"]').forEach(btn => {
        btn.addEventListener('click', handleDeleteChat);
    });

    // Regenerate buttons
    document.querySelectorAll('.regenerate-button').forEach(btn => {
        btn.addEventListener('click', handleRegenerate);
    });

    // Developer message modal setup
    const devMsgModalBtn = document.getElementById('dev-msg-modal-btn');
    const devMsgModal = document.getElementById('dev-msg-modal');
    const devMsgInput = document.getElementById('dev-msg-input');
    const devMsgCancel = document.getElementById('dev-msg-cancel');
    const devMsgSave = document.getElementById('dev-msg-save');
    const devMsgModalClose = document.getElementById('dev-msg-modal-close');

    if (devMsgModalBtn && devMsgModal && devMsgModalClose && devMsgCancel && devMsgSave && devMsgInput) {
        // Open modal
        devMsgModalBtn.addEventListener('click', () => {
            // Load existing developer message from localStorage or fallback
            const storedDevMsg = localStorage.getItem('developerMessage') || '';
            devMsgInput.value = storedDevMsg;
            devMsgModal.classList.remove('hidden');
        });

        // Close modal (X button)
        devMsgModalClose.addEventListener('click', () => {
            devMsgModal.classList.add('hidden');
        });

        // Cancel
        devMsgCancel.addEventListener('click', () => {
            devMsgModal.classList.add('hidden');
        });

        // Save developer message
        devMsgSave.addEventListener('click', () => {
            const newDevMsg = devMsgInput.value.trim();
            if (!newDevMsg) {
                window.MessageRenderer.showError('Developer message cannot be empty');
                return;
            }
            localStorage.setItem('developerMessage', newDevMsg);
            devMsgModal.classList.add('hidden');
            window.MessageRenderer.showSuccess('Developer message saved locally');
        });
    }
}

// -----------------------------------------------------------------------------
// Event Handlers and Helpers
// -----------------------------------------------------------------------------
function handleSubmit(e) {
    e.preventDefault();
    sendMessage(e);
}

function handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(e);
    }
}

async function handleModelChange() {
    const modelSelect = document.getElementById('model-select');
    const selectedOption = modelSelect.selectedOptions[0];
    const modelType = selectedOption.dataset.modelType;
    const modelIcon = document.querySelector('.model-selector svg');

    window.CHAT_CONFIG.isOSeriesModel = CONFIG.O_SERIES_MODELS.includes(modelType);

    if (modelIcon && selectedOption.dataset.color) {
        modelIcon.style.color = selectedOption.dataset.color;
    }

    try {
        const resp = await fetch('/chat/update_model', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.CHAT_CONFIG.csrfToken
            },
            body: JSON.stringify({
                chat_id: window.CHAT_CONFIG.chatId,
                model_id: modelSelect.value
            })
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
}

async function handleEditTitle() {
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
            updateTitleElements(newTitle.trim());
        } else {
            window.MessageRenderer.showError(data.error);
        }
    } catch (err) {
        window.MessageRenderer.showError('Failed to update chat title');
    }
}

function updateTitleElements(title) {
    const mobileSel = document.getElementById('mobile-chat-selector');
    if (mobileSel) {
        const opt = mobileSel.querySelector(`option[value="${window.CHAT_CONFIG.chatId}"]`);
        if (opt) opt.textContent = title;
    }

    const desktopTab = document.querySelector(`.chat-tab[data-chat-id="${window.CHAT_CONFIG.chatId}"] span`);
    if (desktopTab) desktopTab.textContent = title;

    document.title = `Chat - ${title}`;
}

function handleCopyClick(e) {
    e.stopPropagation();
    const rawContent = e.currentTarget.getAttribute('data-raw-content');
    if (rawContent && window.utils?.copyToClipboard) {
        window.utils.copyToClipboard(rawContent);
    }
}

async function handleDeleteChat(e) {
    e.stopPropagation();
    const chatId = e.currentTarget.getAttribute('data-chat-id');
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
}

function handleRegenerate(e) {
    e.stopPropagation();
    if (confirm('Do you want to regenerate the assistant response?')) {
        window.MessageRenderer.showSuccess('Regeneration triggered (feature not fully implemented)');
    }
}

const fileListUpdateDebounce = debounce((files) => {
    const fileList = document.getElementById('file-list');
    if (!fileList) {
        console.error('File list element not found');
        return;
    }

    // Clear existing content
    fileList.innerHTML = '';

    if (!files || !files.length) {
        // Show empty state
        fileList.innerHTML = `
            <div class="file-list-empty text-gray-500 dark:text-gray-400 text-sm text-center py-4">
                <i class="fas fa-file-upload text-2xl mb-2 opacity-50"></i>
                <p>No files attached yet</p>
            </div>`;
        return;
    }

    // Create document fragment for better performance
    const fragment = document.createDocumentFragment();

    // Create file items
    files.forEach(file => {
        const safeName = window.utils.sanitizeHTML(file.name);
        const div = document.createElement('div');
        div.className = 'file-item';
        div.dataset.fileId = file.id;
        
        // Create file info container
        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';
        fileInfo.innerHTML = `
            <i class="fas fa-file-alt text-gray-400"></i>
            <span class="file-name">${safeName}</span>
            <span class="file-size">${formatFileSize(file.size)}</span>
        `;
        
        // Create remove button
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-file-btn';
        removeBtn.dataset.filename = file.name;
        removeBtn.innerHTML = '<i class="fas fa-times"></i>';
        removeBtn.addEventListener('click', () => {
            window.fileUploadManager?.removeFile(file.name);
        });
        
        // Create progress bar
        const progressContainer = document.createElement('div');
        progressContainer.className = 'file-progress';
        progressContainer.innerHTML = '<div class="file-progress-bar" style="width: 0%"></div>';
        
        // Assemble the file item
        div.appendChild(fileInfo);
        div.appendChild(removeBtn);
        div.appendChild(progressContainer);
        
        fragment.appendChild(div);
    });

    // Add all items to DOM at once
    fileList.appendChild(fragment);
});

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// -----------------------------------------------------------------------------
// Initialize on DOMContentLoaded
// -----------------------------------------------------------------------------
document.addEventListener('app:ready', () => {
    startChat().catch(error => {
        console.error('Chat initialization failed:', error);
        window.MessageRenderer?.showError('Failed to initialize chat');
    });

    function updateMobileLayout() {
        handleViewportChanges();
        // Add any additional layout changes for mobile here
    }

    // Update layout on resize
    window.addEventListener('resize', () => {
        updateMobileLayout();
        updateUsagePanelPosition();
    });

    // Handle token usage updates (if applicable)
    if (window.tokenUsageManager) {
        const tokenPanel = document.getElementById('token-usage-panel');
        const tokenTab = document.querySelector('[data-panel="token-usage-panel"]');
        
        window.tokenUsageManager.onUpdateStart = () => {
            tokenTab?.classList.add('loading');
            tokenPanel?.classList.add('loading');
        };
        
        window.tokenUsageManager.onUpdateComplete = () => {
            tokenTab?.classList.remove('loading');
            tokenPanel?.classList.remove('loading');
        };
    }
});

// -----------------------------------------------------------------------------
// Existing Chat Functions
// -----------------------------------------------------------------------------

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
    // Prepare request data
    const message = formData.get('message')?.trim() || '';
    const jsonData = {
        message,
        chat_id: window.CHAT_CONFIG.chatId,
        file_ids: []
    };

    // Handle file uploads if present
    // Skipping file upload in handleNormalResponse because we already handle that in sendMessage

    let fetchResponse;
    try {
        fetchResponse = await window.utils.fetchWithCSRF('/chat/send', {
            method: 'POST',
            headers: {
                'X-Chat-ID': window.CHAT_CONFIG.chatId,
                'api-key': window.CHAT_CONFIG?.azureToken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': window.CHAT_CONFIG?.csrfToken
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
            stream: true,
            model_type: window.CHAT_CONFIG.modelType
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

        // Validate message content
        if (!message && (!window.fileUploadManager?.uploadedFiles?.length || window.fileUploadManager.uploadedFiles.length === 0)) {
            window.MessageRenderer.showError('Please provide a message or upload files');
            return;
        }

        // Validate files if present
        if (window.fileUploadManager?.uploadedFiles?.length > 0) {
            // Validate file types and sizes
            const validFileTypes = ['text/plain', 'application/pdf', 'image/jpeg', 'image/png'];
            const maxFileSize = 10 * 1024 * 1024; // 10MB
            
            const invalidFiles = window.fileUploadManager.uploadedFiles.filter(file => {
                if (!validFileTypes.includes(file.type)) {
                    window.MessageRenderer.showError(`Invalid file type: ${file.name}. Supported types: txt, pdf, jpg, png`);
                    return true;
                }
                if (file.size > maxFileSize) {
                    window.MessageRenderer.showError(`File too large: ${file.name}. Maximum size: 10MB`);
                    return true;
                }
                return false;
            });

            if (invalidFiles.length > 0) {
                return;
            }

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
