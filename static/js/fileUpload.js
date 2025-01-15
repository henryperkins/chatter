class FileUploadManager {
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
        this.MAX_CONCURRENT_UPLOADS = 3;
        this.ALLOWED_FILE_TYPES = [
            'text/plain',
            'application/pdf',
            'text/x-python',
            'application/javascript',
            'text/markdown',
            'image/jpeg',
            'image/png',
            'text/csv'
        ];

        // DOM elements (fall back to ID-based references if not passed)
        this.uploadButton = uploadButton || document.getElementById('upload-button');
        this.dropZone = document.getElementById('drop-zone');
        this.fileInput = document.getElementById('file-input');
        this.uploadedFilesDiv = document.getElementById('uploaded-files');

        // Initialize
        this.setupDragAndDrop();
        this.setupEventListeners();
    }

    /**
     * Validate an individual file for type, size, and duplication.
     */
    validateFile(file) {
        const errors = [];

        // File type validation
        if (!this.ALLOWED_FILE_TYPES.includes(file.type)) {
            errors.push(`Unsupported file type: ${file.type}`);
        }

        // File size validation
        if (file.size > this.MAX_FILE_SIZE) {
            errors.push(`File too large: ${(file.size / 1024 / 1024).toFixed(2)} MB`);
        }

        // Duplicate check (same name and size)
        if (this.uploadedFiles.some(f => f.name === file.name && f.size === file.size)) {
            errors.push(`Duplicate file: ${file.name}`);
        }

        return errors;
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
        window.utils.showFeedback(
            file ? `${file.name}: ${message}` : message,
            'error',
            { duration: 5000, position: 'top' }
        );
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
            <div class="file-item group flex items-center justify-between p-3 bg-white dark:bg-gray-800 rounded-lg mb-2 shadow-sm hover:shadow-md transition-all duration-200">
                <div class="flex items-center space-x-3 w-full">
                    <div class="flex-shrink-0">
                        <i class="fas fa-${this.getFileIcon(file.type)} text-2xl text-blue-500"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center justify-between">
                            <span class="block text-sm font-medium text-gray-900 dark:text-gray-100 truncate" title="${file.name}">
                                ${file.name}
                            </span>
                            <span class="text-xs text-gray-500 dark:text-gray-400 ml-2 whitespace-nowrap">
                                ${(file.size / 1024).toFixed(2)} KB
                            </span>
                        </div>
                        <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-1">
                            <div id="progress-${file.name}"
                                class="bg-blue-500 h-1.5 rounded-full text-[10px] text-center text-white"
                                style="width: 0%">0%</div>
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
                this.uploadedFiles.forEach(file => {
                    formData.append('files[]', file);
                });

                const response = await window.utils.fetchWithCSRF(`/chat/${chatId}/upload`, {
                    method: 'POST',
                    body: formData
                });

                if (response.success) {
                    window.utils.showFeedback('Files uploaded successfully', 'success');
                    this.uploadedFiles = [];
                    this.renderFileList();
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
                if (this.fileInput) {
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
    }

    /**
     * Show a quick preview of an uploaded file in a modal.
     */
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
                        <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">${file.name}</h3>
                        <button onclick="this.closest('#file-preview-modal').classList.add('hidden')"
                                class="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors duration-200"
                                aria-label="Close preview">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="flex-1 overflow-auto p-4" id="file-preview-content"></div>
                </div>
            `;
            document.body.appendChild(previewModal);
        }

        const previewContent = document.getElementById('file-preview-content');
        previewContent.innerHTML = this.getPreviewContent(file);

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
        } else {
            return `
                <div class="text-center py-8">
                    <i class="fas fa-file text-4xl text-gray-400 mb-4"></i>
                    <p class="text-gray-500 dark:text-gray-400">Preview not available for this file type</p>
                </div>
            `;
        }
    }

    /**
     * Asynchronously load text/markdown content from the selected file for preview.
     */
    async loadTextFileContent(file) {
        const previewContent = document.getElementById('file-preview-content');
        if (!previewContent) return;

        try {
            const text = await file.text();
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
}

// Expose globally if needed
window.FileUploadManager = FileUploadManager;
