(() => {
    // Only define the class if it doesn't exist
    if (!window.FileUploadManager) {
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

                // DOM elements (fallback to ID-based references if not passed)
                this.uploadButton = uploadButton || document.getElementById('file-upload');
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
                    const acceptTypes = [
                        '.txt', '.md', '.html', '.pdf', '.docx', '.pptx',
                        'text/plain', 'text/markdown', 'text/html',
                        'application/pdf',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                    ].join(',');
                    this.fileInput.accept = acceptTypes;
                    this.fileInput.style.display = 'none';
                    document.body.appendChild(this.fileInput);
                }

                // Don't initialize in constructor; wait for explicit initialization
                this.initialized = false;
            }

            async initializeFileUpload() {
                if (this.initialized) return true;
                try {
                    this.setupDragAndDrop();
                    this.setupEventListeners();
                    this.setupMobileUpload();
                    this.initialized = true;
                    return true;
                } catch (error) {
                    console.error('FileUploadManager initialization failed:', error);
                    return false;
                }
            }

            // New method: uploads files to the backend API
            async uploadFiles() {
                if (!this.uploadedFiles.length) return [];
                const formData = new FormData();
                this.uploadedFiles.forEach(file => {
                    formData.append('files[]', file);
                });
                try {
                    const response = await fetch(`/api/files/upload/${this.chatId}`, {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-CSRFToken': window.CHAT_CONFIG.csrfToken
                        }
                    });
                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.error || 'Upload failed');
                    }
                    const result = await response.json();
                    if (!result.success) {
                        throw new Error(result.error || 'Upload failed');
                    }
                    return result.saved_files;
                } catch (error) {
                    console.error('File upload error:', error);
                    this.showError(`Failed to upload files: ${error.message}`);
                    return [];
                }
            }

            clearFiles() {
                this.uploadedFiles = [];
                this.updateFileList();
                if (this.fileInput) {
                    this.fileInput.value = '';
                }
                const progressElements = document.querySelectorAll('.file-progress');
                progressElements.forEach(el => el.remove());
                if (this.uploadedFilesDiv) {
                    this.uploadedFilesDiv.innerHTML = '';
                }
                const fileList = document.getElementById('file-list');
                if (fileList) {
                    fileList.innerHTML = '';
                }
            }

            updateFileList() {
                const fileList = document.getElementById('file-list');
                if (!fileList) return;
                fileList.innerHTML = this.uploadedFiles.map(file => `
                    <div class="flex items-center space-x-2 text-sm">
                        <span class="text-gray-600 dark:text-gray-400">${file.name}</span>
                        <button onclick="window.fileUploadManager.removeFile('${file.name}')"
                                class="text-red-500 hover:text-red-700 dark:hover:text-red-400">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `).join('');
            }

            removeFile(fileName) {
                this.uploadedFiles = this.uploadedFiles.filter(file => file.name !== fileName);
                this.updateFileList();
            }

            setupEventListeners() {
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
                            this.updateFileList();
                        }
                    }, 300));
                }
                if (this.uploadButton) {
                    this.uploadButton.addEventListener('click', () => {
                        if (this.fileInput && window.innerWidth > 640) {
                            this.fileInput.click();
                        }
                    });
                }
                this.setupMobileUploadMenu();
            }

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

            setupMobileUpload() {
                if (!this.mobileUploadMenu) return;
                if (window.innerWidth <= 640) {
                    this.mobileUploadMenu.style.display = 'block';
                }
                window.addEventListener('resize', () => this.updateMobileMenuVisibility());
            }

            updateMobileMenuVisibility() {
                if (this.mobileUploadMenu) {
                    this.mobileUploadMenu.style.display = window.innerWidth <= 640 ? 'block' : 'none';
                }
            }

            setupMobileUploadMenu() {
                const mobileMenu = document.getElementById('mobile-upload-menu');
                if (!mobileMenu) return;
                const cameraBtn = mobileMenu.querySelector('[onclick*="camera"]');
                if (cameraBtn) {
                    cameraBtn.onclick = () => this.triggerFileInput('image/*;capture=camera');
                }
                const galleryBtn = mobileMenu.querySelector('[onclick*="gallery"]');
                if (galleryBtn) {
                    galleryBtn.onclick = () => this.triggerFileInput('image/*');
                }
                const filesBtn = mobileMenu.querySelector('[onclick*="files"]');
                if (filesBtn) {
                    filesBtn.onclick = () => this.triggerFileInput(this.ALLOWED_FILE_TYPES.join(','));
                }
            }

            triggerFileInput(accept) {
                if (!this.fileInput) return;
                if (accept === 'image/*;capture=camera' || accept === 'image/*') {
                    this.fileInput.accept = accept;
                } else {
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
                this.fileInput.click();
            }

            validateFile(file) {
                const errors = [];
                const fileType = file.type || this.getMimeType(file.name);
                if (!fileType) {
                    errors.push(`Could not determine file type for: ${file.name}`);
                    return errors;
                }
                const isText = fileType.startsWith('text/') || fileType === 'application/json';
                const isImage = fileType.startsWith('image/');
                const isPDF = fileType === 'application/pdf';
                const isDoc = fileType.includes('msword') || fileType.includes('wordprocessingml');
                if (!isText && !isImage && !isPDF && !isDoc) {
                    errors.push(`Unsupported file type: ${fileType}`);
                    return errors;
                }
                if (isText && file.size > 1024 * 1024) {
                    errors.push(`Text file too large: ${file.name} (max 1MB)`);
                }
                if (!fileType.startsWith('text/') && !fileType.includes('json')) {
                    const maxBinarySize = 5 * 1024 * 1024;
                    if (file.size > maxBinarySize) {
                        errors.push(`Binary file too large: ${(file.size / 1024 / 1024).toFixed(2)} MB (max ${maxBinarySize / 1024 / 1024}MB)`);
                    }
                }
                if (file.size > this.MAX_FILE_SIZE) {
                    errors.push(`File too large: ${(file.size / 1024 / 1024).toFixed(2)} MB`);
                }
                if (this.uploadedFiles.some(f => f.name === file.name && f.size === file.size)) {
                    errors.push(`Duplicate file: ${file.name}`);
                }
                if (file.size > 0) {
                    const estimatedTokens = this.estimateFileTokens(file);
                    file.tokenCount = estimatedTokens;
                    const currentTotal = this.uploadedFiles.reduce((sum, f) => sum + (f.tokenCount || 0), 0);
                    if (currentTotal + estimatedTokens > this.MAX_TOKENS) {
                        errors.push(`File would exceed token limit: ${file.name}`);
                    }
                }
                return errors;
            }

            processFiles(files) {
                const validFiles = [];
                const errors = [];
                const currentTotalSize = this.uploadedFiles.reduce((sum, file) => sum + file.size, 0);
                for (const file of files) {
                    const fileErrors = this.validateFile(file);
                    if (fileErrors.length > 0) {
                        errors.push({ file: file.name, errors: fileErrors });
                        continue;
                    }
                    if (currentTotalSize + file.size > this.MAX_TOTAL_SIZE) {
                        errors.push({ file: file.name, errors: ['Total size limit exceeded'] });
                        continue;
                    }
                    validFiles.push(file);
                }
                return { validFiles, errors };
            }

            getMimeType(filename) {
                const ext = filename.split('.').pop().toLowerCase();
                const mimeTypes = {
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
                    if (['log', 'cfg', 'conf', 'ini', 'env'].includes(ext)) {
                        return 'text/plain';
                    }
                }
                return mimeType;
            }

            estimateFileTokens(file) {
                const charsPerToken = 4;
                const baseTokens = Math.ceil(file.size / charsPerToken);
                return baseTokens + 10;
            }

            setupDragAndDrop() {
                if (!this.dropZone) return;
                ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                    this.dropZone.addEventListener(eventName, (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                    });
                    document.body.addEventListener(eventName, (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                    });
                });
                ['dragenter', 'dragover'].forEach(eventName => {
                    this.dropZone.addEventListener(eventName, () => {
                        this.dropZone.classList.add('drag-active');
                    });
                });
                ['dragleave', 'drop'].forEach(eventName => {
                    this.dropZone.addEventListener(eventName, () => {
                        this.dropZone.classList.remove('drag-active');
                    });
                });
                this.dropZone.addEventListener('drop', (e) => {
                    const files = Array.from(e.dataTransfer.files);
                    const { validFiles, errors } = this.processFiles(files);
                    errors.forEach(error => {
                        this.showError(error.errors.join(', '), { filename: error.file });
                    });
                    if (validFiles.length > 0) {
                        this.uploadedFiles.push(...validFiles);
                        this.updateFileList();
                    }
                });
            }
        }
        // Expose to window
        window.FileUploadManager = FileUploadManager;
    }
})();
