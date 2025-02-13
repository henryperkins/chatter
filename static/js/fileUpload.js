    'use strict';

    // Accurate token counting with type-specific handlers
    class TokenCounter {
        constructor() {
            this.typeHandlers = new Map([
                ['text/plain', this.countTextTokens.bind(this)],
                ['application/pdf', this.countPDFTokens.bind(this)],
                ['application/msword', this.countWordTokens.bind(this)],
                ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', this.countWordTokens.bind(this)]
            ]);
        }

        async countTokens(file) {
            const handler = this.typeHandlers.get(file.type) || this.estimateTokens.bind(this);
            const count = await handler(file);
            await this.validateAgainstLimits(count);
            return count;
        }

        async countTextTokens(file) {
            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const text = e.target.result;
                    // More accurate token estimation: ~4 chars per token
                    const tokenCount = Math.ceil(text.length / 4);
                    resolve(tokenCount);
                };
                reader.readAsText(file);
            });
        }

        async countPDFTokens(file) {
            // Estimate PDF tokens based on size with a more accurate multiplier
            return Math.ceil(file.size / 500); // ~500 bytes per token for PDFs
        }

        async countWordTokens(file) {
            // Word docs typically have more formatting overhead
            return Math.ceil(file.size / 750); // ~750 bytes per token for Word docs
        }

        estimateTokens(file) {
            // Fallback estimation for unknown types
            return Math.ceil(file.size / 1000); // Conservative estimate
        }

        async validateAgainstLimits(count) {
            const systemLimits = { maxTokens: 32000 }; // Could be fetched from server
            if (count > systemLimits.maxTokens) {
                throw new Error(`Token limit exceeded: ${count} tokens (max: ${systemLimits.maxTokens})`);
            }
            return true;
        }
    }

    // Proper file tracking and system integration
    class FileTracker {
        constructor() {
            this.stagedFiles = new Map();
            this.uploadedFiles = new Map();
            this.tokenCounter = new TokenCounter();
        }

        async addFile(file) {
            const fileId = await this.generateUniqueId(file);
            
            if (this.stagedFiles.has(fileId) || this.uploadedFiles.has(fileId)) {
                throw new Error('File already exists in the system');
            }

            // Validate token count before staging
            const tokenCount = await this.tokenCounter.countTokens(file);
            file.tokenCount = tokenCount;

            this.stagedFiles.set(fileId, {
                file,
                tokenCount,
                status: 'staged',
                timestamp: new Date().toISOString()
            });

            return fileId;
        }

        async generateUniqueId(file) {
            // Generate a unique ID based on file properties
            const fileInfo = `${file.name}-${file.size}-${file.lastModified}`;
            // Use SubtleCrypto for secure hash generation
            const msgBuffer = new TextEncoder().encode(fileInfo);
            const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        }

        removeFile(fileId) {
            const wasStaged = this.stagedFiles.delete(fileId);
            const wasUploaded = this.uploadedFiles.delete(fileId);
            return wasStaged || wasUploaded;
        }

        getFile(fileId) {
            return this.stagedFiles.get(fileId) || this.uploadedFiles.get(fileId);
        }

        moveToUploaded(fileId, uploadResult) {
            const fileData = this.stagedFiles.get(fileId);
            if (!fileData) return false;

            this.stagedFiles.delete(fileId);
            this.uploadedFiles.set(fileId, {
                ...fileData,
                status: 'uploaded',
                uploadResult
            });
            return true;
        }

        getTotalTokens() {
            let total = 0;
            for (const [_, data] of this.stagedFiles) {
                total += data.tokenCount;
            }
            for (const [_, data] of this.uploadedFiles) {
                total += data.tokenCount;
            }
            return total;
        }
    }

    // Enhanced mobile upload handling
    class MobileUploadManager {
        constructor() {
            this.networkMonitor = {
                type: navigator.connection?.type || 'unknown',
                isReliable: () => {
                    const connection = navigator.connection;
                    if (!connection) return true;
                    return !['slow-2g', '2g'].includes(connection.effectiveType);
                }
            };
            this.uploadQueue = new Map();
            this.CHUNK_SIZE = 5 * 1024 * 1024; // 5MB default
            this.setupNetworkListeners();
        }

        setupNetworkListeners() {
            if ('connection' in navigator) {
                navigator.connection.addEventListener('change', () => {
                    this.networkMonitor.type = navigator.connection.type;
                    this.adjustChunkSize();
                });
            }
        }

        adjustChunkSize() {
            const connection = navigator.connection;
            if (!connection) return;

            switch (connection.effectiveType) {
                case '4g':
                    this.CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
                    break;
                case '3g':
                    this.CHUNK_SIZE = 1 * 1024 * 1024; // 1MB
                    break;
                default:
                    this.CHUNK_SIZE = 512 * 1024; // 512KB
            }
        }

        async upload(file, uploadUrl, headers = {}) {
            if (!this.networkMonitor.isReliable()) {
                return this.queueForLater(file);
            }

            if (file.size > this.CHUNK_SIZE) {
                return this.chunkedUpload(file, uploadUrl, headers);
            }

            return this.reliableUpload(file, uploadUrl, headers);
        }

        async reliableUpload(file, uploadUrl, headers, retries = 3) {
            try {
                const formData = new FormData();
                formData.append('file', file);

                const response = await fetch(uploadUrl, {
                    method: 'POST',
                    body: formData,
                    headers,
                });

                if (!response.ok) {
                    throw new Error(`Upload failed: ${response.statusText}`);
                }

                return await response.json();
            } catch (error) {
                if (retries > 0 && this.isRetryableError(error)) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    return this.reliableUpload(file, uploadUrl, headers, retries - 1);
                }
                throw error;
            }
        }

        isRetryableError(error) {
            return error.message.includes('network') || 
                   error.message.includes('timeout') ||
                   error.message.includes('connection');
        }

        async chunkedUpload(file, uploadUrl, headers) {
            const chunks = Math.ceil(file.size / this.CHUNK_SIZE);
            const uploadId = await this.initializeChunkedUpload(file, uploadUrl, headers);

            for (let i = 0; i < chunks; i++) {
                const start = i * this.CHUNK_SIZE;
                const end = Math.min(start + this.CHUNK_SIZE, file.size);
                const chunk = file.slice(start, end);

                await this.uploadChunk(chunk, i, chunks, uploadId, uploadUrl, headers);
            }

            return this.finalizeChunkedUpload(uploadId, uploadUrl, headers);
        }

        async initializeChunkedUpload(file, uploadUrl, headers) {
            const response = await fetch(`${uploadUrl}/init`, {
                method: 'POST',
                headers: {
                    ...headers,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filename: file.name,
                    size: file.size,
                    type: file.type
                })
            });

            if (!response.ok) {
                throw new Error('Failed to initialize chunked upload');
            }

            const result = await response.json();
            return result.uploadId;
        }

        async uploadChunk(chunk, index, total, uploadId, uploadUrl, headers) {
            const formData = new FormData();
            formData.append('chunk', chunk);
            formData.append('index', index);
            formData.append('total', total);
            formData.append('uploadId', uploadId);

            const response = await fetch(`${uploadUrl}/chunk`, {
                method: 'POST',
                body: formData,
                headers
            });

            if (!response.ok) {
                throw new Error(`Failed to upload chunk ${index + 1}/${total}`);
            }

            return response.json();
        }

        async finalizeChunkedUpload(uploadId, uploadUrl, headers) {
            const response = await fetch(`${uploadUrl}/finalize`, {
                method: 'POST',
                headers: {
                    ...headers,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ uploadId })
            });

            if (!response.ok) {
                throw new Error('Failed to finalize upload');
            }

            return response.json();
        }

        queueForLater(file) {
            const queueId = Date.now().toString();
            this.uploadQueue.set(queueId, {
                file,
                timestamp: new Date(),
                retryCount: 0
            });
            return { queued: true, queueId };
        }
    }

    class FileUploadManager {
        constructor(chatId, userId, uploadButton) {
            this.chatId = chatId;
            this.userId = userId;

            // Enhanced file tracking
            this.fileTracker = new FileTracker();
            this.mobileUploadManager = new MobileUploadManager();
            
                    // Mobile-specific properties
                    this.isMobile = /Mobile|Android|iPhone/i.test(navigator.userAgent);
                    this.networkType = navigator.connection?.type || 'unknown';

                    // Basic constraints
                    this.MAX_FILES = 5;
                    this.MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
                    this.MAX_TOTAL_SIZE = 50 * 1024 * 1024; // 50 MB
                    this.MAX_TOKENS = 32000; // approximate usage limit
                    this.MAX_CONCURRENT_UPLOADS = 3;

                    // Allowed file extensions - must match server config
                    this.ALLOWED_EXTENSIONS = ['.txt', '.pdf', '.doc', '.docx'];
                    
                    // File input accept attribute extensions
                    this.ACCEPT_TYPES = '.txt,.pdf,.doc,.docx';

                    // DOM references
                    this.uploadButton = uploadButton || document.getElementById('upload-trigger');
                    this.fileInput = this.createFileInput();
                    this.mobileUploadMenu = document.getElementById('mobile-upload-controls');
                    this.uploadedFilesDiv = document.getElementById('uploaded-files');
                    this.progressBar = document.getElementById('upload-progress-bar');

                    // For partial or chunked uploads
                    this.CHUNK_SIZE = 5 * 1024 * 1024; // 5MB per chunk

                    // Internal state
                    this.initialized = false;
                }

                /**
                 * Creates the hidden <input type="file"> used for manual selection.
                 */
                createFileInput() {
                    const input = document.createElement('input');
                    input.type = 'file';
                    input.id = 'file-upload';
                    input.multiple = true;
                    input.accept = this.ACCEPT_TYPES;

                    input.style.display = 'none';
                    document.body.appendChild(input);
                    return input;
                }

                /**
                 * Main entry point to set up event listeners.
                 */
                async initializeFileUpload() {
                    if (this.initialized) return true;
                    try {
                        if (this.isMobile) {
                            await this.setupMobileSpecificHandling();
                        }
                        // Removed drop-zone handling to match the template which has no drop zone
                        this.setupEventListeners();
                        this.setupMobileUpload();
                        this.initialized = true;
                        return true;
                    } catch (error) {
                        console.error('Initialization failed:', error);
                        this.showError('File upload initialization failed');
                        return false;
                    }
                }

                /**
                 * Sets up click/selection listeners on file input and button.
                 */
                setupEventListeners() {
                    // File input change
                    this.fileInput.addEventListener('change', async (e) => {
                        // Ensure iOS triggers the "change" event
                        e.preventDefault();
                        e.stopPropagation();
                        const inputFiles = e.target.files;
                        if (!inputFiles || !inputFiles.length) {
                            return; // Bail out if no files selected
                        }
                        const files = Array.from(inputFiles);
                        await this.handleNewFiles(files);
                        // Reset file input to allow selecting the same file again
                        e.target.value = '';
                    });

                    // Upload button click (desktop) and touch (mobile)
                    this.uploadButton?.addEventListener('click', () => this.fileInput.click());
                    this.uploadButton?.addEventListener('touchstart', (e) => {
                        // Prevent default so iOS doesn't ignore the tap
                        e.preventDefault();
                        e.stopPropagation();
                        // Some versions of iOS Safari need a small delay
                        // before calling .click() on the file input
                        setTimeout(() => {
                            this.fileInput.click();
                        }, 50);
                    });

                    // Adjust mobile menu on window resize
                    window.addEventListener('resize', () => this.updateMobileMenuVisibility());
                }

                /**
                 * Processes newly added files: validates them, adds to queue, shows errors if any.
                 */
                async handleNewFiles(files) {
                    console.log('Processing files:', files);
                    const { validFiles, errors } = await this.processFiles(files);
                    console.log('Valid files:', validFiles);
                    console.log('Errors:', errors);

                    // Show any errors
                    errors.forEach(({ file, errors }) => {
                        this.showError(errors.join(', '), file);
                    });

                    // Append valid files to local queue and update UI
                    if (validFiles.length) {
                        this.uploadedFiles.push(...validFiles);
                        console.log('Updated uploadedFiles:', this.uploadedFiles);
                        
                        // Update the file list UI
                        this.updateFileList();
                        console.log('File list updated');
                        
                        // Trigger the onFilesChanged callback if it exists
                        if (typeof this.onFilesChanged === 'function') {
                            this.onFilesChanged(this.uploadedFiles);
                            console.log('onFilesChanged callback triggered');
                        }
                        
                        // Update token display
                        this.updateTokenDisplay();
                    } else {
                        console.log('No valid files to process');
                    }
                }

                /**
                 * Validates each file and (optionally) generates previews for images.
                 */
                async processFiles(files) {
                    const validFiles = [];
                    const errors = [];
                    let totalSize = this.uploadedFiles.reduce((sum, f) => sum + f.size, 0);

                    for (const file of files) {
                        const fileErrors = this.validateFile(file);
                        if (fileErrors.length) {
                            errors.push({ file, errors: fileErrors });
                            continue;
                        }

                        // Check total size constraint
                        if (totalSize + file.size > this.MAX_TOTAL_SIZE) {
                            errors.push({
                                file,
                                errors: ['Total size limit exceeded']
                            });
                            continue;
                        }

                        // Generate preview for images
                        if (file.type.startsWith('image/')) {
                            file.preview = await this.generatePreview(file);
                        }

                        validFiles.push(file);
                        totalSize += file.size;
                    }

                    return { validFiles, errors };
                }

                /**
                 * Returns a base64 data URL for images so you can show a thumbnail in your UI.
                 */
                generatePreview(file) {
                    return new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onload = (e) => resolve(e.target.result);
                        reader.readAsDataURL(file);
                    });
                }

                /**
                 * Checks file type, size, duplicates, and token usage.
                 */
                validateFile(file) {
                    const errors = [];
                    const fileType = this.getMimeType(file);

                    // Check if the type is allowed
                    const allowedExtensions = ['.txt', '.pdf', '.doc', '.docx'];
                    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
                    
                    if (!allowedExtensions.includes(fileExtension)) {
                        errors.push(`Unsupported file type: ${fileExtension}`);
                    }

                    // Max size per file
                    if (file.size > this.MAX_FILE_SIZE) {
                        errors.push(`File exceeds ${this.formatFileSize(this.MAX_FILE_SIZE)} limit`);
                    }

                    // Duplicate check by name + size
                    if (this.uploadedFiles.some(f => f.name === file.name && f.size === file.size)) {
                        errors.push('Duplicate file detected');
                    }

                    // Token estimation (for text or partial binary)
                    const fileTokens = this.estimateTokens(file);
                    const currentTokens = this.uploadedFiles.reduce(
                        (sum, f) => sum + (f.tokenCount || this.estimateTokens(f)), 0
                    );
                    if (currentTokens + fileTokens > this.MAX_TOKENS) {
                        errors.push('Exceeds available token capacity');
                    } else {
                        // Store the token count on the file object
                        file.tokenCount = fileTokens;
                    }

                    return errors;
                }

                /**
                 * Basic detection of file MIME type or fallback from extension.
                 */
                getMimeType(file) {
                    return file.type || this.guessMimeType(file.name);
                }

                guessMimeType(filename) {
                    const ext = filename.split('.').pop().toLowerCase();
                    const typeMap = {
                        txt: 'text/plain',
                        pdf: 'application/pdf',
                        doc: 'application/msword',
                        docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    };
                    return typeMap[ext] || 'application/octet-stream';
                }

                /**
                 * Roughly estimates token usage. More refined logic can be used if needed.
                 */
                estimateTokens(file) {
                    // For text-based:
                    if (file.type.startsWith('text/')) {
                        // Rough estimate: 1 token per ~4 chars
                        return Math.ceil(file.size / 4);
                    }
                    // For binary data, e.g. PDFs, images, etc.:
                    // 1 token per ~1 KB by default
                    return Math.ceil(file.size / 1000);
                }

                /**
                 * Uploads the current queue of files. Demonstrates chunked uploading for large files.
                 * Returns an array of metadata objects for each file.
                 */
                async uploadFiles() {
                    if (!this.uploadedFiles.length) return [];

                    const uploadedFiles = [];
                    let fileIndex = 0;

                    for (const file of this.uploadedFiles) {
                        try {
                            // If file is large, do chunked upload
                            if (file.size > this.CHUNK_SIZE) {
                                const chunks = Math.ceil(file.size / this.CHUNK_SIZE);
                                let uploadId = null;

                                for (let i = 0; i < chunks; i++) {
                                    const chunk = file.slice(i * this.CHUNK_SIZE, (i + 1) * this.CHUNK_SIZE);
                                    const formData = new FormData();
                                    formData.append('file', chunk);
                                    formData.append('chunkIndex', i);
                                    formData.append('totalChunks', chunks);
                                    formData.append('originalFilename', file.name);
                                    formData.append('uploadId', uploadId || '');
                                    formData.append('fileSize', file.size);

                                    const resp = await fetch(`${window.location.origin}/api/files/chunked-upload/${this.chatId}`, {
                                        method: 'POST',
                                        body: formData,
                                        headers: {
                                            'X-CSRFToken': window.CHAT_CONFIG.csrfToken,
                                            'X-Chat-ID': this.chatId
                                        }
                                    });

                                    if (!resp.ok) {
                                        let errorData;
                                        try {
                                            errorData = await resp.json();
                                        } catch {
                                            // fallback if JSON parse fails
                                            errorData = { error: 'Chunked upload failed' };
                                        }
                                        throw new Error(errorData.error || 'Chunked upload error');
                                    }

                                    const result = await resp.json();
                                    uploadId = result.uploadId;
                                    // progress: from 0% to 100% across all chunks
                                    const overallPct = Math.round(((fileIndex + i / chunks) / this.uploadedFiles.length) * 100);
                                    this.updateProgress(overallPct);
                                }

                                uploadedFiles.push({
                                    id: uploadId,
                                    name: file.name,
                                    size: file.size,
                                    mime_type: file.type,
                                    uploaded_at: new Date().toISOString()
                                });
                            } else {
                                // Normal single-file upload
                                const formData = new FormData();
                                formData.append('file', file);

                                // Optional: pass chatId, userId, etc. if needed
                                const resp = await fetch(`${window.location.origin}/api/files/upload/${this.chatId}`, {
                                    method: 'POST',
                                    body: formData,
                                    headers: {
                                        'X-CSRFToken': window.CHAT_CONFIG.csrfToken,
                                        'X-Chat-ID': this.chatId
                                    }
                                });

                                if (!resp.ok) {
                                    let errorData;
                                    try {
                                        errorData = await resp.json();
                                    } catch {
                                        errorData = { error: 'Upload failed' };
                                    }
                                    throw new Error(errorData.error || 'Upload failed');
                                }

                                const result = await resp.json();
                                console.log('Upload response:', result);

                                if (!result.success) {
                                    throw new Error(result.error || 'File upload unsuccessful');
                                }

                                // Handle various response formats
                                const fileMetadata = {
                                    id: result.file_id || result.id || file.name,
                                    name: result.filename || file.name,
                                    size: result.size || file.size,
                                    mime_type: result.mime_type || file.type,
                                    uploaded_at: new Date().toISOString()
                                };

                                console.log('File metadata:', fileMetadata);
                                uploadedFiles.push(fileMetadata);
                                
                                // Update UI immediately after successful upload
                                this.uploadedFiles = [...this.uploadedFiles, file];
                                this.updateFileList();
                                
                                // Switch to Files tab if not already active
                                const filesTab = document.querySelector('[data-panel="file-usage-panel"]');
                                if (filesTab && !filesTab.classList.contains('tab-active')) {
                                    filesTab.click();
                                }
                            }
                            
                            // As soon as we finish this file, update progress
                            const percent = Math.round(((fileIndex + 1) / this.uploadedFiles.length) * 100);
                            this.updateProgress(percent);
                        } catch (error) {
                            this.showError(`Failed to upload ${file.name}: ${error.message}`, file);
                            throw error; // Let the caller (chat.js) handle overall error
                        }

                        fileIndex++;
                    }

                    // After all files are processed, set final progress to 100%
                    this.updateProgress(100);

                    return uploadedFiles;
                }

                /**
                 * Visually updates the progress bar (if present).
                 */
                updateProgress(percentage) {
                    if (this.progressBar) {
                        this.progressBar.style.width = `${percentage}%`;
                        this.progressBar.setAttribute('aria-valuenow', percentage);
                    }
                }

                /**
                 * Highlights errors in the UI and optionally the specific file item.
                 */
                showError(message, file = null) {
                    if (file) {
                        // Include file name + size in the message
                        message = `${file.name} (${this.formatFileSize(file.size)}): ${message}`;
                        this.highlightInvalidFile(file.name);
                    }

                    // Example: using your global feedback utility
                    if (window.utils?.showFeedback) {
                        window.utils.showFeedback(
                            message,
                            'error',
                            { duration: 7000, position: 'top' }
                        );
                    } else {
                        alert(`Error: ${message}`);
                    }
                }

                /**
                 * Temporary highlight for a file that failed validation/upload.
                 */
                highlightInvalidFile(filename) {
                    const fileList = document.getElementById('file-list');
                    if (!fileList) return;

                    const item = fileList.querySelector(`[data-filename="${filename}"]`);
                    if (item) {
                        item.classList.add('invalid-file');
                        setTimeout(() => {
                            item.classList.remove('invalid-file');
                        }, 3000);
                    }
                }

                /**
                 * Displays updated file list in the UI and updates token usage.
                 */
                updateFileList() {
                    console.log('Updating file list. Current files:', this.uploadedFiles);
                    const fileList = document.getElementById('file-list');
                    if (!fileList) {
                        console.error('File list element not found');
                        return;
                    }

                    if (!this.uploadedFiles.length) {
                        console.log('No files to display, showing empty state');
                        fileList.innerHTML = `
                            <div class="file-list-empty text-gray-500 dark:text-gray-400 text-sm text-center py-4">
                                <i class="fas fa-file-upload text-2xl mb-2 opacity-50"></i>
                                <p>No files attached yet</p>
                            </div>`;
                        return;
                    }

                    console.log('Rendering file list items');
                    fileList.innerHTML = this.uploadedFiles.map(file => `
                        <div class="file-item" data-filename="${file.name}">
                            <div class="file-info">
                                <i class="fas fa-file-alt text-gray-400"></i>
                                <span class="file-name">${file.name}</span>
                                <span class="file-size">${this.formatFileSize(file.size)}</span>
                            </div>
                            <button class="remove-file-btn" data-filename="${file.name}">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    `).join('');

                    fileList.querySelectorAll('.remove-file-btn').forEach(btn => {
                        btn.addEventListener('click', () => {
                            this.removeFile(btn.dataset.filename);
                        });
                    });

                    // Update token display after changes
                    this.updateTokenDisplay();
                }

                /**
                 * Removes a single file by filename from the queue.
                 */
                removeFile(filename) {
                    this.uploadedFiles = this.uploadedFiles.filter(f => f.name !== filename);
                    // Trigger the onFilesChanged callback if it exists
                    if (typeof this.onFilesChanged === 'function') {
                        this.onFilesChanged(this.uploadedFiles);
                    }
                    // Update token display
                    this.updateTokenDisplay();
                }

                /**
                 * Clears all queued files and resets progress/UI.
                 */
                clearFiles() {
                    this.uploadedFiles = [];
                    this.fileInput.value = '';
                    // Trigger the onFilesChanged callback if it exists
                    if (typeof this.onFilesChanged === 'function') {
                        this.onFilesChanged(this.uploadedFiles);
                    }
                    // Update token display and progress
                    this.updateTokenDisplay();
                    this.updateProgress(0);
                }

                /**
                 * If you track token usage in real time, integrate with a usage manager or simply display it.
                 */
                updateTokenDisplay() {
                    const totalTokens = this.uploadedFiles.reduce(
                        (sum, file) => sum + (file.tokenCount || this.estimateTokens(file)),
                        0
                    );

                    // If you have a global usage manager:
                    if (window.tokenUsageManager) {
                        window.tokenUsageManager.updateTokenCount(totalTokens);
                        // Warn if the corresponding DOM element isn't present
                        if (!document.getElementById('tokens-used')) {
                            console.warn('tokens-used element not present in DOM, skipping usage display.');
                        }
                    }

                    // Or simply put it in a DOM element:
                    const tokenDisplay = document.getElementById('token-count');
                    if (tokenDisplay) {
                        tokenDisplay.textContent = `Tokens: ${totalTokens}`;
                    }
                }

                /**
                 * Helper to format file sizes in a human-readable form.
                 */
                formatFileSize(bytes) {
                    if (bytes === 0) return '0 Bytes';
                    const k = 1024;
                    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                    const i = Math.floor(Math.log(bytes) / Math.log(k));
                    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
                }

                /**
                 * Initializes mobile upload menu if present.
                 */
                setupMobileUpload() {
                    if (!this.mobileUploadMenu) return;
                    this.updateMobileMenuVisibility();
                    this.setupMobileUploadMenu();
            
                    if (this.isMobile) {
                        this.createMobileProgressUI();
                    }
                }

                async setupMobileSpecificHandling() {
                    // Handle iOS HEIC/HEIF conversion and other mobile-specific formats
                    this.uploadButton.addEventListener('change', async (e) => {
                        const files = Array.from(e.target.files);
                        const convertedFiles = await Promise.all(
                            files.map(async file => {
                                // Handle HEIC/HEIF images
                                if (['image/heic', 'image/heif', 'image/heic-sequence'].includes(file.type)) {
                                    return this.convertHEICtoJPG(file);
                                }
                                else if (/\.(heic|HEIC)$/.test(file.name)) {
                                    // Fallback if MIME detection missed .HEIC
                                    return this.convertHEICtoJPG(file);
                                }
                                // Handle other image types that might need orientation fixing
                                if (file.type.startsWith('image/')) {
                                    const orientedBlob = await this.fixImageOrientation(file);
                                    return new File([orientedBlob], file.name, {
                                        type: file.type,
                                        lastModified: file.lastModified
                                    });
                                }
                                return file;
                            })
                        );
                            // Group HEIC + MOV pairs if present (iOS Live Photos)
                            const groupedFiles = this.groupLivePhotos(convertedFiles);
                            this.handleNewFiles(groupedFiles);
                    });

                    // Monitor network changes
                    if ('connection' in navigator) {
                        navigator.connection.addEventListener('change', () => {
                            this.networkType = navigator.connection.type || 'unknown';
                            this.adjustUploadParamsForNetwork();
                        });
                    }
                }

                adjustUploadParamsForNetwork() {
                    // Adjust chunk size based on network quality
                    if (navigator.userAgent.includes('Safari') && navigator.userAgent.includes('iPhone')) {
                        this.CHUNK_SIZE = 512 * 1024; // 512KB
                        return;
                    }
                    switch (this.networkType) {
                        case '4g':
                            this.CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
                            break;
                        case '3g':
                            this.CHUNK_SIZE = 1 * 1024 * 1024; // 1MB
                            break;
                        default:
                            this.CHUNK_SIZE = 512 * 1024; // 512KB
                    }
                }

                async fixImageOrientation(blob) {
                    let canvas;
                    try {
                        const imageBitmap = await createImageBitmap(blob);
                        canvas = document.createElement('canvas');
                        canvas.width = imageBitmap.width;
                        canvas.height = imageBitmap.height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(imageBitmap, 0, 0);
                    } catch (e) {
                        // Fallback para iOS que não suporta createImageBitmap
                        const fallbackImg = document.createElement('img');
                        fallbackImg.src = URL.createObjectURL(blob);
                        await new Promise((res) => (fallbackImg.onload = res));
                        canvas = document.createElement('canvas');
                        canvas.width = fallbackImg.width;
                        canvas.height = fallbackImg.height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(fallbackImg, 0, 0);
                    }
                    return new Promise((resolve) => {
                        canvas.toBlob(resolve, 'image/jpeg', 0.8);
                    });
                }

                async convertHEICtoJPG(file) {
                    try {
                        const heic2any = (await import('heic2any')).default;
                        const convertedBlob = await heic2any({
                            blob: file,
                            toType: 'image/jpeg',
                            quality: 0.8
                        });

                        // Fix orientation issues
                        const orientedBlob = await this.fixImageOrientation(convertedBlob);
                        
                        // Preserve original filename but change extension
                        const newName = file.name.replace(/\.[^/.]+$/, '.jpg');
                        
                        return new File([orientedBlob], newName, {
                            type: 'image/jpeg',
                            lastModified: file.lastModified
                        });
                    } catch (error) {
                        console.error('HEIC conversion failed:', error);
                        return file;
                    }
                }

                createMobileProgressUI() {
                    this.progressBar = document.createElement('div');
                    this.progressBar.className = 'mobile-progress-bar';
            
                    const progressHTML = `
                        <div class="upload-status">
                            <div class="progress-bar">
                                <div class="progress-fill"></div>
                            </div>
                            <div class="network-status">
                                <i class="fas fa-signal"></i>
                                <span>Using ${this.networkType} connection</span>
                            </div>
                            <button class="pause-resume-btn">
                                <i class="fas fa-pause"></i>
                            </button>
                        </div>
                    </div>
                    <div class="mobile-tips">
                    <span class="ios-warning" style="display: none;">
                        Tip for iOS: Keep Safari in the foreground for uninterrupted upload.
                    </span>
                    </div>
                    `;
            
                    this.progressBar.innerHTML = progressHTML;
                    document.body.appendChild(this.progressBar);

                    if (/iPhone|iPad/i.test(navigator.userAgent)) {
                        this.progressBar.querySelector('.ios-warning').style.display = 'inline';
                    }
                }

                updateMobileMenuVisibility() {
                    if (this.mobileUploadMenu) {
                        this.mobileUploadMenu.style.display =
                            window.innerWidth <= 640 ? 'block' : 'none';
                    }
                }

                /**
                 * Assigns different accept filters based on user selection (camera, gallery, files).
                 */
                setupMobileUploadMenu() {
                    const types = {
                        camera: 'image/*;capture=camera',
                        gallery: 'image/*',
                        files: this.ACCEPT_TYPES  // ensure no "capture" appended
                    };

                    Object.entries(types).forEach(([type, accept]) => {
                        const btn = this.mobileUploadMenu.querySelector(`[data-upload-type="${type}"]`);
                        if (btn) {
                            btn.onclick = () => {
                                this.triggerFileInput(accept);
                                this.logUploadAction(type);
                            };
                        }
                    });
                }

                /**
                 * Actually triggers the hidden file input with an updated accept pattern.
                 */
                triggerFileInput(accept) {
                    this.fileInput.accept = accept;
                    this.fileInput.click();
                }

                /**
                 * Example logging for analytics/monitoring.
                 */
                logUploadAction(type) {
                    if (window.monitoring) {
                        window.monitoring.log('file_upload', {
                            type: type,
                            chat_id: this.chatId
                        });
                    }
                }
            }

    // Layout management for proper panel visibility
    class LayoutManager {
        constructor() {
            this.panels = new Set();
            this.visibilityObserver = new IntersectionObserver(
                this.handleVisibilityChange.bind(this),
                {
                    threshold: 0.5
                }
            );
            this.setupPanelObservers();
        }

        setupPanelObservers() {
            // Observe chat messages for visibility
            document.querySelectorAll('.chat-message').forEach(message => {
                this.visibilityObserver.observe(message);
            });

            // Track panel states
            document.querySelectorAll('.panel').forEach(panel => {
                this.panels.add(panel);
            });
        }

        handleVisibilityChange(entries) {
            for (const entry of entries) {
                if (entry.target.classList.contains('chat-message') && 
                    entry.intersectionRatio < 0.5) {
                    this.adjustPanels();
                }
            }
        }

        adjustPanels() {
            const chatVisible = this.ensureChatVisible();
            if (!chatVisible) {
                this.collapsePanels();
            }
        }

        ensureChatVisible() {
            const chatContainer = document.querySelector('.chat-container');
            if (!chatContainer) return true;

            const rect = chatContainer.getBoundingClientRect();
            const isVisible = rect.top >= 0 && rect.bottom <= window.innerHeight;

            if (!isVisible) {
                chatContainer.scrollIntoView({ behavior: 'smooth' });
            }

            return isVisible;
        }

        collapsePanels() {
            this.panels.forEach(panel => {
                if (panel.classList.contains('expanded')) {
                    panel.classList.remove('expanded');
                    panel.style.height = 'var(--panel-content-height)';
                }
            });
        }

        observeNewMessage(message) {
            this.visibilityObserver.observe(message);
        }

        destroy() {
            this.visibilityObserver.disconnect();
            this.panels.clear();
        }
    }

    // Expose classes globally
    if (typeof window !== 'undefined') {
        window.FileUploadManager = FileUploadManager;
        window.LayoutManager = LayoutManager;
    }
