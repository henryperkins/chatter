window.FileUploadManager = class {
    constructor(chatId, userId, uploadButton) {
        // Basic properties
        this.chatId = chatId;
        this.userId = userId;
        this.uploadedFiles = [];
        this.uploadQueue = [];
        this.currentUploads = 0;

        // File constraints
        this.MAX_FILES = 5;
        this.MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
        this.MAX_TOTAL_SIZE = 50 * 1024 * 1024; // 50 MB
        this.MAX_TOKENS = 32000; // Maximum tokens per file
        this.MAX_CONCURRENT_UPLOADS = 3;
        this.ALLOWED_FILE_TYPES = [
            // Text files
            'text/plain',
            'text/markdown',
            'text/html',

            // Application files
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
            'application/vnd.openxmlformats-officedocument.presentationml.presentation' // .pptx
        ];

        // DOM elements (fall back to ID-based references if not passed)
        this.uploadButton = uploadButton || document.getElementById('upload-button');
        this.dropZone = document.getElementById('drop-zone');
        this.fileInput = document.getElementById('file-input');
        this.mobileUploadMenu = document.getElementById('mobile-upload-controls');
        this.uploadedFilesDiv = document.getElementById('uploaded-files');

        // Create file input if it doesn't exist
        if (!this.fileInput) {
            this.fileInput = document.createElement('input');
            this.fileInput.type = 'file';
            this.fileInput.id = 'file-input';
            this.fileInput.multiple = true;
            // Convert MIME types to file extensions for better browser compatibility
            const acceptTypes = [
                // Text files
                '.txt', '.md', '.html',
                // Application files
                '.pdf', '.docx', '.pptx',
                // Also include MIME types for better coverage
                'text/plain',
                'text/markdown',
                'text/html',
                'application/pdf',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            ].join(',');
            this.fileInput.accept = acceptTypes;
            this.fileInput.style.display = 'none';
            document.body.appendChild(this.fileInput);
        }

        // Initialize
        this.setupDragAndDrop();
        this.setupEventListeners();
        this.setupMobileUpload();
    }

    setupMobileUpload() {
        if (!this.mobileUploadMenu) return;

        // Show mobile upload controls on small screens
        if (window.innerWidth <= 640) {
            this.mobileUploadMenu.style.display = 'block';
        }

        // Update visibility on resize
        window.addEventListener('resize', () => this.updateMobileMenuVisibility());
    }

    /**
     * Validate an individual file for type, size, and duplication.
     */
    validateFile(file) {
        const errors = [];

        // File type validation
        const fileType = file.type || this.getMimeType(file.name);
        if (!fileType) {
            errors.push(`Could not determine file type for: ${file.name}`);
            return errors;
        }

        // Check if file type is allowed
        const isText = fileType.startsWith('text/') || fileType === 'application/json';
        const isImage = fileType.startsWith('image/');
        const isPDF = fileType === 'application/pdf';
        const isDoc = fileType.includes('msword') || fileType.includes('wordprocessingml');

        if (!isText && !isImage && !isPDF && !isDoc) {
            errors.push(`Unsupported file type: ${fileType}`);
            return errors;
        }

        // Size validation based on file type
        if (isText && file.size > 1024 * 1024) {
            errors.push(`Text file too large: ${file.name} (max 1MB)`);
        }

        // Additional validation for binary files
        if (!fileType.startsWith('text/') && !fileType.includes('json')) {
            const maxBinarySize = 5 * 1024 * 1024; // 5MB limit for binary files
            if (file.size > maxBinarySize) {
                errors.push(`Binary file too large: ${(file.size / 1024 / 1024).toFixed(2)} MB (max ${maxBinarySize / 1024 / 1024}MB)`);
            }
        }

        // File size validation
        if (file.size > this.MAX_FILE_SIZE) {
            errors.push(`File too large: ${(file.size / 1024 / 1024).toFixed(2)} MB`);
        }

        // Duplicate check (same name and size)
        if (this.uploadedFiles.some(f => f.name === file.name && f.size === file.size)) {
            errors.push(`Duplicate file: ${file.name}`);
        }

        // Estimate token count
        if (file.size > 0) {
            const estimatedTokens = this.estimateFileTokens(file);
            file.tokenCount = estimatedTokens;

            // Check against token limits
            const currentTotal = this.uploadedFiles.reduce((sum, f) => sum + (f.tokenCount || 0), 0);
            if (currentTotal + estimatedTokens > this.MAX_TOKENS) {
                errors.push(`File would exceed token limit: ${file.name}`);
            }
        }

        return errors;
    }

    getMimeType(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const mimeTypes = {
            // Text files
            'txt': 'text/plain',
            'md': 'text/markdown',
            'js': 'application/javascript',
            'py': 'text/x-python',
            'json': 'application/json',
            'csv': 'text/csv',
            'html': 'text/html',
            'css': 'text/css',
            'xml': 'text/xml',
            'yaml': 'text/yaml',
            'yml': 'text/yaml',

            // Binary files
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        };

        const mimeType = mimeTypes[ext];
        if (!mimeType && ext) {
            // For unknown extensions, try to infer text vs binary
            if (['log', 'cfg', 'conf', 'ini', 'env'].includes(ext)) {
                return 'text/plain';
            }
        }
        return mimeType;
    }


    estimateFileTokens(file) {
        // Estimate tokens based on file size and type
        const charsPerToken = 4; // Conservative estimate
        const baseTokens = Math.ceil(file.size / charsPerToken);

        // Add overhead for file metadata
        return baseTokens + 10;
    }

    /**
     * Update the visual progress bar for a given file.
     */
    showUploadProgress(file, progress) {
        const progressElement = document.getElementById(`progress-${file.name}`);
        if (progressElement) {
            progressElement.style.width = `${progress}%`;
            progressElement.textContent = `${Math.round(progress)}%`;
        }
    }

    /**
     * Display an error using the global feedback mechanism (if available).
     */
    showError(message, file = null) {
        let errorMessage = message;
        if (file) {
            const fileSize = file.size ? `(${(file.size / 1024 / 1024).toFixed(2)} MB)` : '';
            const fileType = file.type || this.getMimeType(file.name) || 'unknown type';
            errorMessage = `${file.name} ${fileSize}: ${message} [${fileType}]`;
        }
        window.utils.showFeedback(
            errorMessage,
            'error',
            { duration: 7000, position: 'top' }
        );
        console.debug('File validation error:', { file, message });
    }

    /**
     * Check each file against validation rules and overall size limits.
     */
    processFiles(files) {
        const validFiles = [];
        const errors = [];

        // Calculate current total size
        const currentTotalSize = this.uploadedFiles.reduce((sum, file) => sum + file.size, 0);

        for (const file of files) {
            const fileErrors = this.validateFile(file);

            // Skip invalid files
            if (fileErrors.length > 0) {
                errors.push({ file: file.name, errors: fileErrors });
                continue;
            }

            // Check total limit if adding this file
            if (currentTotalSize + file.size > this.MAX_TOTAL_SIZE) {
                errors.push({ file: file.name, errors: ['Total size limit exceeded'] });
                continue;
            }

            validFiles.push(file);
        }

        return { validFiles, errors };
    }

    /**
     * Return a Font Awesome icon class based on file type.
     */
    getFileIcon(fileType) {
        const iconMap = {
            'application/pdf': 'file-pdf',
            'image/': 'file-image',
            'text/': 'file-alt',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'file-word',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'file-excel',
            'application/zip': 'file-archive'
        };

        for (const [type, icon] of Object.entries(iconMap)) {
            if (fileType.includes(type)) {
                return icon;
            }
        }
        return 'file';
    }

    /**
     * Update the on-page file list and storage usage bar.
     */
    renderFileList() {
        const fileList = document.getElementById('file-list');
        const totalSizeEl = document.getElementById('total-size');
        if (!fileList || !totalSizeEl) return;

        // Build the file list markup
        fileList.innerHTML = this.uploadedFiles.map((file, index) => `
            <div class="file-item group flex flex-col p-3 bg-white dark:bg-gray-800 rounded-lg mb-2 shadow-sm hover:shadow-md transition-all duration-200">
                <div class="flex items-center justify-between w-full">
                    <div class="flex items-center space-x-3 flex-1">
                        <div class="flex-shrink-0">
                            <i class="fas fa-${this.getFileIcon(file.type)} text-2xl text-blue-500"></i>
                        </div>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between">
                                <span class="block text-sm font-medium text-gray-900 dark:text-gray-100 truncate" title="${file.name}">
                                    ${file.name}
                                </span>
                                <div class="flex items-center space-x-2 ml-2">
                                    ${file.version ? `<span class="text-xs bg-blue-100 dark:bg-blue-800 text-blue-800 dark:text-blue-100 px-2 py-0.5 rounded">v${file.version}</span>` : ''}
                                    <span class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                                        ${(file.size / 1024).toFixed(2)} KB
                                    </span>
                                    ${file.token_count ? `<span class="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded">${file.token_count} tokens</span>` : ''}
                                    ${file.is_truncated ? `<span class="text-xs bg-yellow-100 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-100 px-2 py-0.5 rounded">Truncated</span>` : ''}
                                </div>
                            </div>
                            <div class="flex items-center text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                <span class="mr-2">${file.mime_type || file.type}</span>
                                ${file.uploadTime ? `<span>• Uploaded: ${new Date(file.uploadTime).toLocaleString()}</span>` : ''}
                            </div>
                            <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-1">
                                <div id="progress-${file.name}"
                                    class="bg-blue-500 h-1.5 rounded-full text-[10px] text-center text-white"
                                    style="width: 0%">0%</div>
                            </div>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        <button onclick="window.fileUploadManager.showPreview(${index})"
                                class="text-gray-500 hover:text-blue-500 p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                                aria-label="Preview file">
                            <i class="fas fa-eye text-sm"></i>
                        </button>
                        <button onclick="window.fileUploadManager.removeFile(${index})"
                                class="text-gray-500 hover:text-red-500 p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                                aria-label="Remove file">
                            <i class="fas fa-times text-sm"></i>
                        </button>
                    </div>
                </div>
                <div class="mt-2">
                    <textarea
                        class="w-full px-3 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder="Add a description..."
                        rows="1"
                        onchange="window.fileUploadManager.updateFileDescription(${index}, this.value)"
                    >${file.description || ''}</textarea>
                </div>
            </div>
        `).join('');

        // Update total size display
        const totalBytes = this.uploadedFiles.reduce((sum, file) => sum + file.size, 0);
        const totalMB = (totalBytes / 1024 / 1024).toFixed(2);
        const maxMB = (this.MAX_TOTAL_SIZE / 1024 / 1024).toFixed(2);
        const percentage = Math.min((totalBytes / this.MAX_TOTAL_SIZE) * 100, 100);

        totalSizeEl.innerHTML = `
            <div class="flex items-center justify-between text-sm">
                <span class="text-gray-700 dark:text-gray-300">Storage Used</span>
                <span class="font-medium">${totalMB} MB / ${maxMB} MB</span>
            </div>
            <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mt-1">
                <div class="bg-blue-500 h-2 rounded-full" style="width: ${percentage}%"></div>
            </div>
        `;

        // Show/hide the entire upload section
        if (this.uploadedFilesDiv) {
            this.uploadedFilesDiv.classList.toggle('hidden', this.uploadedFiles.length === 0);
        }
    }

    /**
     * Remove a file from the list (by index) and re-render.
     */
    removeFile(index) {
        this.uploadedFiles.splice(index, 1);
        this.renderFileList();
    }

    /**
     * Perform the actual upload of the files to the server (if any).
     */
    async uploadFiles(chatId) {
        if (this.uploadedFiles.length === 0) {
            window.utils.showFeedback('No files to upload', 'warning');
            return;
        }

        const uploadBtn = this.uploadButton;
        if (!uploadBtn) return;

        try {
            await window.utils.withLoading(uploadBtn, async () => {
                const formData = new FormData();

                // Add files and their descriptions
                this.uploadedFiles.forEach(file => {
                    formData.append('files[]', file);
                    if (file.description) {
                        formData.append(`description_${file.name}`, file.description);
                    }
                });

                const response = await window.utils.fetchWithCSRF(`/api/files/upload/${chatId}`, {
                    method: 'POST',
                    body: formData
                });

                if (response.success) {
                    // Keep track of uploaded files
                    const uploadedFiles = response.saved_files.map(file => ({
                        ...file,
                        type: file.mime_type,
                        uploadTime: file.upload_time,
                        version: file.version || 1
                    }));

                    window.utils.showFeedback('Files uploaded successfully', 'success');

                    // Emit custom event for chat interface with uploaded files
                    window.dispatchEvent(new CustomEvent('filesUploaded', {
                        detail: {
                            files: uploadedFiles,
                            totalSize: response.total_size
                        }
                    }));

                    // Return uploaded files for further processing
                    return uploadedFiles;
                } else {
                    throw new Error(response.error || 'Upload failed');
                }
            }, { text: 'Uploading...' });
        } catch (error) {
            this.showError(error.message);
        }
    }

    /**
     * Initialize drag-and-drop events (if dropZone is available).
     */
    setupDragAndDrop() {
        if (!this.dropZone) return;

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.dropZone.addEventListener(eventName, this.preventDefaults, false);
        });

        this.dropZone.addEventListener('dragenter', () => {
            this.dropZone.classList.remove('hidden');
        });

        this.dropZone.addEventListener('dragleave', (e) => {
            if (!e.relatedTarget || !this.dropZone.contains(e.relatedTarget)) {
                this.dropZone.classList.add('hidden');
            }
        });

        this.dropZone.addEventListener('drop', (e) => {
            try {
                this.dropZone.classList.add('hidden');
                if (!e.dataTransfer?.files) {
                    window.utils.showFeedback('No files dropped', 'error');
                    return;
                }
                const files = Array.from(e.dataTransfer.files);
                if (files.length === 0) {
                    window.utils.showFeedback('No files dropped', 'error');
                    return;
                }
                const { validFiles, errors } = this.processFiles(files);
                if (errors.length > 0) {
                    errors.forEach(err => window.utils.showFeedback(err.errors.join(', '), 'error'));
                }
                if (validFiles.length > 0) {
                    this.uploadedFiles.push(...validFiles);
                    this.renderFileList();
                }
            } catch (error) {
                console.error('Error handling file drop:', error);
                window.utils.showFeedback('Failed to process dropped files', 'error');
            } finally {
                this.dropZone.classList.add('hidden');
            }
        });
    }

    /**
     * Prevent browser defaults on drag events to allow drop handling.
     */
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    /**
     * Set up file input and preview/close event listeners.
     */
    setupEventListeners() {
        // If the file input is present, handle change events (with debouncing).
        if (this.fileInput) {
            this.fileInput.style.display = 'none';
            this.fileInput.addEventListener('change', window.utils.debounce((e) => {
                const files = Array.from(e.target.files);
                const { validFiles, errors } = this.processFiles(files);

                errors.forEach(error => {
                    this.showError(error.errors.join(', '), { filename: error.file });
                });

                if (validFiles.length > 0) {
                    this.uploadedFiles.push(...validFiles);
                    this.renderFileList();
                }
            }, 300));
        }

        // If the upload button is present, wire it to open the file dialog
        if (this.uploadButton) {
            this.uploadButton.addEventListener('click', () => {
                if (this.fileInput && window.innerWidth > 640) {
                    this.fileInput.click();
                }
            });
        }

        // Close preview modal when clicking outside it
        document.addEventListener('click', (e) => {
            const previewModal = document.getElementById('file-preview-modal');
            if (
                previewModal &&
                !previewModal.contains(e.target) &&
                !e.target.closest('.file-item')
            ) {
                previewModal.classList.add('hidden');
            }
        });

        // Handle mobile upload menu
        this.setupMobileUploadMenu();
    }

    setupMobileUploadMenu() {
        const mobileMenu = document.getElementById('mobile-upload-menu');
        if (!mobileMenu) return;

        // Handle camera capture
        const cameraBtn = mobileMenu.querySelector('[onclick*="camera"]');
        if (cameraBtn) {
            cameraBtn.onclick = () => this.triggerFileInput('image/*;capture=camera');
        }

        // Handle gallery selection
        const galleryBtn = mobileMenu.querySelector('[onclick*="gallery"]');
        if (galleryBtn) {
            galleryBtn.onclick = () => this.triggerFileInput('image/*');
        }

        // Handle file selection
        const filesBtn = mobileMenu.querySelector('[onclick*="files"]');
        if (filesBtn) {
            filesBtn.onclick = () => this.triggerFileInput(this.ALLOWED_FILE_TYPES.join(','));
        }
    }

    updateMobileMenuVisibility() {
        if (this.mobileUploadMenu) {
            this.mobileUploadMenu.style.display = window.innerWidth <= 640 ? 'block' : 'none';
        }
    }

    /**
     * Show a quick preview of an uploaded file in a modal.
     */
    updateFileDescription(index, description) {
        if (this.uploadedFiles[index]) {
            this.uploadedFiles[index].description = description;
        }
    }

    showPreview(index) {
        const file = this.uploadedFiles[index];
        if (!file) return;

        // Create or reuse a preview modal container
        let previewModal = document.getElementById('file-preview-modal');
        if (!previewModal) {
            previewModal = document.createElement('div');
            previewModal.id = 'file-preview-modal';
            previewModal.className =
                'fixed inset-0 bg-black/50 backdrop-blur-sm z-modal flex items-center justify-center p-4 hidden';
            previewModal.innerHTML = `
                <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
                    <div class="flex justify-between items-center p-4 border-b border-gray-200 dark:border-gray-700">
                        <div class="flex-1 mr-4">
                            <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">${file.name}</h3>
                            <div class="flex items-center text-sm text-gray-500 dark:text-gray-400 mt-1">
                                <span class="mr-3">${file.mime_type || file.type}</span>
                                <span class="mr-3">${(file.size / 1024).toFixed(2)} KB</span>
                                ${file.version ? `<span class="bg-blue-100 dark:bg-blue-800 text-blue-800 dark:text-blue-100 px-2 py-0.5 rounded text-xs">v${file.version}</span>` : ''}
                            </div>
                            ${file.uploadTime ? `<div class="text-sm text-gray-500 dark:text-gray-400 mt-1">Uploaded: ${new Date(file.uploadTime).toLocaleString()}</div>` : ''}
                        </div>
                        <button onclick="this.closest('#file-preview-modal').classList.add('hidden')"
                                class="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors duration-200"
                                aria-label="Close preview">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="flex-1 overflow-auto" id="file-preview-content"></div>
                    <div class="p-4 border-t border-gray-200 dark:border-gray-700">
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Description</label>
                        <textarea
                            class="w-full px-3 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="Add a description..."
                            rows="2"
                            onchange="window.fileUploadManager.updateFileDescription(${index}, this.value)"
                        >${file.description || ''}</textarea>
                    </div>
                </div>
            `;
            document.body.appendChild(previewModal);
        }

        const previewContent = document.getElementById('file-preview-content');
        previewContent.innerHTML = this.getPreviewContent(file);
        previewContent.className = 'flex-1 overflow-auto p-4';

        previewModal.classList.remove('hidden');

        // If it's a text/markdown file, load contents asynchronously
        if (file.type === 'text/plain' || file.type === 'text/markdown') {
            this.loadTextFileContent(file);
        }
    }

    /**
     * Return HTML snippet to preview the file based on type.
     */
    getPreviewContent(file) {
        // For files that haven't been uploaded yet
        if (!file.id) {
            if (file.type.startsWith('image/')) {
                return `<img src="${URL.createObjectURL(file)}" alt="Preview of ${file.name}" class="max-w-full h-auto rounded-lg">`;
            } else if (file.type === 'application/pdf') {
                return `
                    <div class="h-[70vh]">
                        <iframe src="${URL.createObjectURL(file)}" class="w-full h-full rounded-lg" title="PDF Preview"></iframe>
                    </div>
                `;
            } else if (file.type === 'text/plain' || file.type === 'text/markdown') {
                return `
                    <div class="bg-gray-100 dark:bg-gray-700 p-4 rounded-lg">
                        <pre class="whitespace-pre-wrap break-words text-sm">Loading...</pre>
                    </div>
                `;
            }
        }

        // For uploaded files, use the server preview route
        if (file.id) {
            if (file.type.startsWith('image/')) {
                return `<img src="/api/files/preview/${file.id}" alt="Preview of ${file.name}" class="max-w-full h-auto rounded-lg">`;
            } else if (file.type === 'application/pdf') {
                return `
                    <div class="h-[70vh]">
                        <iframe src="/api/files/preview/${file.id}" class="w-full h-full rounded-lg" title="PDF Preview"></iframe>
                    </div>
                `;
            } else if (file.type === 'text/plain' || file.type === 'text/markdown') {
                return `
                    <div class="bg-gray-100 dark:bg-gray-700 p-4 rounded-lg">
                        <pre class="whitespace-pre-wrap break-words text-sm">Loading...</pre>
                    </div>
                `;
            }
        }

        // Default for unsupported types
        return `
            <div class="text-center py-8">
                <i class="fas fa-file text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-500 dark:text-gray-400">Preview not available for this file type</p>
            </div>
        `;
    }

    /**
     * Asynchronously load text/markdown content from the selected file for preview.
     */
    async loadTextFileContent(file) {
        const previewContent = document.getElementById('file-preview-content');
        if (!previewContent) return;

        try {
            let text;
            if (file.id) {
                // For uploaded files, fetch from server
                const response = await fetch(`/api/files/preview/${file.id}`);
                if (!response.ok) throw new Error('Failed to fetch file content');
                text = await response.text();
            } else {
                // For files not yet uploaded
                text = await file.text();
            }

            const preElement = previewContent.querySelector('pre');
            if (preElement) {
                preElement.textContent = text;
            }
        } catch (error) {
            console.error('Failed to load file content:', error);
            if (previewContent.querySelector('pre')) {
                previewContent.querySelector('pre').textContent = 'Failed to load file content';
            }
        }
    }

    triggerFileInput(accept) {
        if (!this.fileInput) return;

        // Handle special cases for mobile capture
        if (accept === 'image/*;capture=camera' || accept === 'image/*') {
            this.fileInput.accept = accept;
        } else {
            // Use our standard accept types for regular file selection
            const acceptTypes = [
                '.txt', '.md', '.py', '.js', '.json', '.csv', '.html', '.css', '.xml', '.yaml', '.yml',
                '.pdf', '.doc', '.docx',
                '.jpg', '.jpeg', '.png', '.gif', '.webp',
                'text/*',
                'application/json',
                'application/pdf',
                'image/*'
            ].join(',');
            this.fileInput.accept = acceptTypes;
        }

        // Trigger click
        this.fileInput.click();
    }

}

// Expose globally if needed
window.FileUploadManager = FileUploadManager;
