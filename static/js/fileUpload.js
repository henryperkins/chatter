
class FileUploadManager {
  constructor() {
    this.uploadedFiles = [];
    this.MAX_FILES = 5;
    this.MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
    this.MAX_TOTAL_SIZE = 50 * 1024 * 1024; // 50MB
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
    this.dropZone = document.getElementById('drop-zone');
    this.fileInput = document.getElementById('file-input');
    this.uploadButton = document.getElementById('upload-button');
    this.uploadedFilesDiv = document.getElementById('uploaded-files');
    this.setupDragAndDrop();
    this.setupEventListeners();
  }

  // Validate a single file
  validateFile(file) {
    const errors = [];
    if (!this.ALLOWED_FILE_TYPES.includes(file.type)) {
      errors.push(`Unsupported file type: ${file.type}`);
    }
    if (file.size > this.MAX_FILE_SIZE) {
      errors.push(`File too large: ${(file.size / 1024 / 1024).toFixed(2)} MB`);
    }
    if (this.uploadedFiles.some(f => f.name === file.name)) {
      errors.push(`Duplicate file: ${file.name}`);
    }
    return errors;
  }

  // Process multiple files
  processFiles(files) {
    const validFiles = [];
    const errors = [];
    const totalSize = this.uploadedFiles.reduce((sum, file) => sum + file.size, 0);

    for (const file of files) {
      const fileErrors = this.validateFile(file);
      if (fileErrors.length > 0) {
        errors.push({ file: file.name, errors: fileErrors });
        continue;
      }

      if (totalSize + file.size > this.MAX_TOTAL_SIZE) {
        errors.push({ file: file.name, errors: ['Total size limit exceeded'] });
        continue;
      }

      validFiles.push(file);
    }

    return { validFiles, errors };
  }

  // Get file type icon
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

  // Render the file list
  renderFileList() {
    const fileList = document.getElementById('file-list');
    const totalSize = document.getElementById('total-size');
    if (!fileList || !totalSize) return;

    fileList.innerHTML = '';
    let totalBytes = 0;

    this.uploadedFiles.forEach((file, index) => {
      totalBytes += file.size;
      const fileDiv = document.createElement('div');
      fileDiv.className = 'file-item flex items-center justify-between p-2 bg-gray-100 dark:bg-gray-800 rounded mb-2';
      fileDiv.innerHTML = `
        <div class="flex items-center space-x-2">
          <i class="fas fa-${this.getFileIcon(file.type)} text-blue-500"></i>
          <div>
            <span class="block text-sm font-medium text-gray-700 dark:text-gray-200 truncate">${file.name}</span>
            <span class="block text-xs text-gray-500 dark:text-gray-400">${(file.size / 1024).toFixed(2)} KB</span>
          </div>
        </div>
        <button onclick="fileUploadManager.removeFile(${index})" 
                class="text-red-500 hover:text-red-700 p-1 rounded-full hover:bg-red-100 dark:hover:bg-red-900 transition-colors"
                aria-label="Remove file">
          <i class="fas fa-times"></i>
        </button>
      `;
      fileList.appendChild(fileDiv);
    });

    // Update total size display
    const totalMB = (totalBytes / 1024 / 1024).toFixed(2);
    totalSize.textContent = `Total: ${totalMB} MB / ${(this.MAX_TOTAL_SIZE / 1024 / 1024).toFixed(2)} MB`;

    // Show/hide the upload area
    if (this.uploadedFilesDiv) {
      this.uploadedFilesDiv.classList.toggle('hidden', this.uploadedFiles.length === 0);
    }
  }

  // Show error message
  showError(message) {
    const errorDiv = document.getElementById('file-errors');
    if (!errorDiv) return;

    const errorElement = document.createElement('div');
    errorElement.className = 'text-sm text-red-500 flex items-center space-x-1';
    errorElement.innerHTML = `
      <i class="fas fa-exclamation-circle"></i>
      <span>${message}</span>
    `;
    errorDiv.appendChild(errorElement);

    // Auto-remove error after 5 seconds
    setTimeout(() => {
      errorElement.remove();
    }, 5000);
  }

  // Remove a file from the list
  removeFile(index) {
    this.uploadedFiles.splice(index, 1);
    this.renderFileList();
  }

  // Upload files to the server
  async uploadFiles(chatId) {
    if (this.uploadedFiles.length === 0) return;

    const formData = new FormData();
    this.uploadedFiles.forEach(file => formData.append('files[]', file));

    try {
      const response = await fetchWithCSRF(`/chat/${chatId}/upload`, {
        method: 'POST',
        body: formData
      });

      if (response.success) {
        showFeedback('Files uploaded successfully', 'success');
        this.uploadedFiles = []; // Clear the list after successful upload
        this.renderFileList();
      } else {
        throw new Error(response.error || 'Failed to upload files');
      }
    } catch (error) {
      console.error('Upload error:', error);
      showFeedback(error.message, 'error');
    }
  }

  // Setup drag-and-drop functionality
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
          showFeedback('No files dropped', 'error');
          return;
        }
        const files = Array.from(e.dataTransfer.files);
        if (files.length === 0) {
          showFeedback('No files dropped', 'error');
          return;
        }
        const { validFiles, errors } = this.processFiles(files);
        if (errors.length > 0) {
          errors.forEach(error => showFeedback(error.errors.join(', '), 'error'));
        }
        if (validFiles.length > 0) {
          this.uploadedFiles.push(...validFiles);
          this.renderFileList();
        }
      } catch (error) {
        console.error('Error handling file drop:', error);
        showFeedback('Failed to process dropped files', 'error');
      } finally {
        this.dropZone.classList.add('hidden');
      }
    });
  }

  // Prevent default drag-and-drop behavior
  preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  // Setup event listeners
  setupEventListeners() {
    if (this.fileInput) {
      this.fileInput.addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        const { validFiles, errors } = this.processFiles(files);

        if (errors.length > 0) {
          errors.forEach(error => showFeedback(error.errors.join(', '), 'error'));
        }

        if (validFiles.length > 0) {
          this.uploadedFiles.push(...validFiles);
          this.renderFileList();
        }
      });
    }

    if (this.uploadButton) {
      this.uploadButton.addEventListener('click', () => {
        this.fileInput.click();
      });
    }

    // Close preview modal when clicking outside
    document.addEventListener('click', (e) => {
      const previewModal = document.getElementById('file-preview-modal');
      if (previewModal && !previewModal.contains(e.target) && !e.target.closest('.file-item')) {
        previewModal.classList.add('hidden');
      }
    });
  }

  // Show file preview
  showPreview(index) {
    const file = this.uploadedFiles[index];
    if (!file) return;

    // Create or update preview modal
    let previewModal = document.getElementById('file-preview-modal');
    if (!previewModal) {
      previewModal = document.createElement('div');
      previewModal.id = 'file-preview-modal';
      previewModal.className = 'fixed inset-0 bg-black/50 backdrop-blur-sm z-modal flex items-center justify-center p-4 hidden';
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
  }

  // Get preview content based on file type
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

  // Load text file content
  async loadTextFileContent(file) {
    const previewContent = document.getElementById('file-preview-content');
    if (!previewContent) return;

    try {
      const text = await file.text();
      previewContent.querySelector('pre').textContent = text;
    } catch (error) {
      previewContent.querySelector('pre').textContent = 'Failed to load file content';
    }
  }
}

// Initialize the file upload manager
const fileUploadManager = new FileUploadManager();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FileUploadManager;
} else {
  window.fileUploadManager = fileUploadManager;
}
