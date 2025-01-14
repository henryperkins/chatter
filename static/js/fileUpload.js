
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

  // Render the file list
  renderFileList() {
    const fileList = document.getElementById('file-list');
    if (!fileList) return;

    fileList.innerHTML = '';

    this.uploadedFiles.forEach((file, index) => {
      const fileDiv = document.createElement('div');
      fileDiv.className = 'file-item flex justify-between items-center p-2 bg-gray-100 dark:bg-gray-800 rounded mb-2';
      fileDiv.innerHTML = `
        <span class="truncate">${file.name} (${(file.size / 1024).toFixed(2)} KB)</span>
        <button onclick="fileUploadManager.removeFile(${index})" class="text-red-500 hover:text-red-700">
          <i class="fas fa-times"></i>
        </button>
      `;
      fileList.appendChild(fileDiv);
    });

    // Show/hide the upload area
    const uploadArea = document.getElementById('uploaded-files');
    if (uploadArea) {
      uploadArea.classList.toggle('hidden', this.uploadedFiles.length === 0);
    }
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
}

// Initialize the file upload manager
const fileUploadManager = new FileUploadManager();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FileUploadManager;
} else {
  window.fileUploadManager = fileUploadManager;
}
