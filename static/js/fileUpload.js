    (() => {
        'use strict';

        if (!window.FileUploadManager) {
            class FileUploadManager {
                constructor(chatId, userId, uploadButton) {
                    this.chatId = chatId;
                    this.userId = userId;

                    // In-memory file list (pending uploads)
                    this.uploadedFiles = [];
            
                    // Mobile-specific properties
                    this.isMobile = /Mobile|Android|iPhone/i.test(navigator.userAgent);
                    this.networkType = navigator.connection?.type || 'unknown';

                    // Basic constraints
                    this.MAX_FILES = 5;
                    this.MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
                    this.MAX_TOTAL_SIZE = 50 * 1024 * 1024; // 50 MB
                    this.MAX_TOKENS = 32000; // approximate usage limit
                    this.MAX_CONCURRENT_UPLOADS = 3;

                    // Allowed MIME types - must match server config
                    this.ALLOWED_FILE_TYPES = [
                        'text/plain',           // .txt
                        'text/markdown',        // .md
                        'text/html',           // .html
                        'text/x-python',       // .py
                        'application/pdf',     // .pdf
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation' // .pptx
                    ];

                    // DOM references
                    this.uploadButton = uploadButton || document.getElementById('file-upload');
                    this.dropZone = document.getElementById('drop-zone');
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
                    input.id = 'file-input';
                    input.multiple = true;
                    input.accept = [
                        '.txt', '.md', '.html', '.py', '.pdf', '.docx', '.pptx',
                        'text/plain', 'text/markdown', 'text/html', 'text/x-python',
                        'application/pdf',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                    ].join(',');

                    input.style.display = 'none';
                    document.body.appendChild(input);
                    return input;
                }

                /**
                 * Main entry point to set up event listeners and drag-and-drop.
                 */
                async initializeFileUpload() {
                    if (this.initialized) return true;
                    try {
                        if (this.isMobile) {
                            await this.setupMobileSpecificHandling();
                        } else {
                            this.setupDragAndDrop();
                        }
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
                 * Wires up drag-and-drop functionality if a drop zone is present.
                 */
                setupDragAndDrop() {
                    if (!this.dropZone) return;

                    // Configure drop zone positioning
                    this.dropZone.style.zIndex = '9999';
                    this.dropZone.style.pointerEvents = 'none';
                    
                    // Update input height CSS variable
                    document.documentElement.style.setProperty(
                        '--chat-input-height',
                        `${this.chatInput?.offsetHeight || 120}px`
                    );

                    const highlight = () => this.dropZone.classList.add('drag-active');
                    const unhighlight = () => this.dropZone.classList.remove('drag-active');

                    const handleDrag = (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        highlight();
                    };

                    const handleDrop = (e) => {
                        e.preventDefault();
                        unhighlight();
                        const files = Array.from(e.dataTransfer.files);
                        this.handleNewFiles(files);
                    };

                    this.dropZone.addEventListener('dragenter', handleDrag);
                    this.dropZone.addEventListener('dragover', handleDrag);
                    this.dropZone.addEventListener('dragleave', unhighlight);
                    this.dropZone.addEventListener('drop', handleDrop);
                }

                /**
                 * Sets up click/selection listeners on file input and button.
                 */
                setupEventListeners() {
                    // File input change
                    this.fileInput.addEventListener('change', async (e) => {
                        const files = Array.from(e.target.files);
                        await this.handleNewFiles(files);
                    });

                    // Upload button click (desktop)
                    this.uploadButton?.addEventListener('click', () => {
                        // Only show file dialog on non-mobile view
                        if (window.innerWidth > 640) {
                            this.fileInput.click();
                        }
                    });

                    // Adjust mobile menu on window resize
                    window.addEventListener('resize', () => this.updateMobileMenuVisibility());
                }

                /**
                 * Processes newly added files: validates them, adds to queue, shows errors if any.
                 */
                async handleNewFiles(files) {
                    const { validFiles, errors } = await this.processFiles(files);

                    // Show any errors
                    errors.forEach(({ file, errors }) => {
                        this.showError(errors.join(', '), file);
                    });

                    // Append valid files to local queue and update UI
                    if (validFiles.length) {
                        this.uploadedFiles.push(...validFiles);
                        // Trigger the onFilesChanged callback if it exists
                        if (typeof this.onFilesChanged === 'function') {
                            this.onFilesChanged(this.uploadedFiles);
                        }
                        // Update token display
                        this.updateTokenDisplay();
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
                    if (!this.ALLOWED_FILE_TYPES.includes(fileType)) {
                        errors.push(`Unsupported file type: ${fileType}`);
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
                        md: 'text/markdown',
                        html: 'text/html',
                        pdf: 'application/pdf',
                        docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                        py: 'text/x-python'
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

                                // Revised logic: separate check for success vs. saved_files presence
                                if (!result.success) {
                                    throw new Error(result.error || 'File upload unsuccessful');
                                } else if (!result.saved_files?.length) {
                                    // If the server indicates success but returned no saved files,
                                    // we won't treat it as an error, but log a warning to console.
                                    console.warn('No saved files were returned by the server. Possibly invalid or empty upload.');
                                } else {
                                    const savedFile = result.saved_files[0];
                                    if (!savedFile.id || !savedFile.filename) {
                                        throw new Error('Invalid file metadata returned from server');
                                    }

                                    // Return richer metadata
                                    uploadedFiles.push({
                                        id: savedFile.id,
                                        name: savedFile.filename,
                                        url: savedFile.filepath,
                                        mime_type: savedFile.mime_type,
                                        size: savedFile.size,
                                        uploaded_at: new Date().toISOString()
                                    });
                                }

                                // As soon as we finish this file, update progress
                                const percent = Math.round(((fileIndex + 1) / this.uploadedFiles.length) * 100);
                                this.updateProgress(percent);
                            }
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
                    const fileList = document.getElementById('file-list');
                    if (!fileList) return;

                    fileList.innerHTML = this.uploadedFiles.map(file => `
                        <div class="file-item flex items-center justify-between" data-filename="${file.name}">
                            <span>${file.name}</span>
                            <button class="remove-file" data-filename="${file.name}">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    `).join('');

                    fileList.querySelectorAll('.remove-file').forEach(btn => {
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
                    const image = await createImageBitmap(blob);
                    const canvas = document.createElement('canvas');
                    canvas.width = image.width;
                    canvas.height = image.height;
                    
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(image, 0, 0);
                    
                    return new Promise(resolve => {
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
                        files: this.ALLOWED_FILE_TYPES.join(',')  // ensure no "capture" appended
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

            // Expose the class globally
            window.FileUploadManager = FileUploadManager;
        }
    })();
