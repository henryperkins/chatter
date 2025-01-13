// chatFiles.js
// Manages file selection, validation, and rendering file lists

import { showFeedback } from '../utils.js'; // adjust path if needed
import {
  instanceId,
  uploadedFiles,
  addFiles,
  clearFiles,
  MAX_FILES,
  MAX_FILE_SIZE,
  ALLOWED_FILE_TYPES
} from './chatState.js';

/**
 * Processes newly selected or dropped files:
 * 1) Checks allowed types/sizes
 * 2) Updates the global `uploadedFiles` state
 * 3) Renders the file list in the UI
 */
export function processFiles(files) {
  const errors = [];
  const validFiles = [];
  const totalSize = uploadedFiles.reduce((sum, file) => sum + file.size, 0);

  for (const file of files) {
    // Check file type
    if (!ALLOWED_FILE_TYPES.includes(file.type)) {
      errors.push(`${file.name}: Unsupported file type.`);
      continue;
    }
    // Check individual file size
    if (file.size > MAX_FILE_SIZE) {
      errors.push(`${file.name}: File too large (max ${MAX_FILE_SIZE / 1024 / 1024}MB).`);
      continue;
    }
    // Check total size limit
    if (totalSize + file.size > MAX_FILE_SIZE * MAX_FILES) {
      errors.push(
        `${file.name}: Would exceed total size of ` +
        `${(MAX_FILES * MAX_FILE_SIZE) / (1024 * 1024)}MB.`
      );
      continue;
    }
    // Check file count limit
    if (uploadedFiles.length + validFiles.length >= MAX_FILES) {
      errors.push(`${file.name}: Maximum of ${MAX_FILES} files reached.`);
      continue;
    }
    // Check empty files
    if (file.size === 0) {
      errors.push(`${file.name}: File is empty.`);
      continue;
    }

    validFiles.push(file);
  }

  if (errors.length > 0) {
    showFeedback(errors.join('\n'), 'error', { duration: 10000 });
  }

  if (validFiles.length > 0) {
    addFiles(validFiles);
    renderFileList();

    // Summarize
    const totalMB = (
      uploadedFiles.reduce((sum, f) => sum + f.size, 0) /
      1024 /
      1024
    ).toFixed(1);
    showFeedback(`${validFiles.length} file(s) ready. Total size: ${totalMB}MB`, 'success');
  }
}

/**
 * Re-renders the list of uploaded files in the DOM.
 */
export function renderFileList() {
  const uploadedFilesDiv = document.getElementById('uploaded-files');
  const fileList = document.getElementById('file-list');
  if (!uploadedFilesDiv || !fileList) return;

  fileList.innerHTML = '';
  uploadedFiles.forEach((file, index) => {
    const fileDiv = document.createElement('div');
    fileDiv.className = 'flex items-center justify-between bg-gray-100 dark:bg-gray-800 p-2 rounded mb-2';
    fileDiv.innerHTML = `
      <span class="text-sm truncate">${file.name}</span>
      <button class="text-red-500 hover:text-red-700 transition-colors duration-200"
              data-index="${index}"
              aria-label="Remove ${file.name}">
        Remove
      </button>
    `;
    fileList.appendChild(fileDiv);
  });

  // Show/hide the files container
  uploadedFilesDiv.classList.toggle('hidden', uploadedFiles.length === 0);

  // Attach click handlers for remove
  fileList.querySelectorAll('button[data-index]').forEach(button => {
    button.addEventListener('click', () => {
      removeFile(parseInt(button.dataset.index, 10));
    });
  });
}

/**
 * Removes a file from the global uploadedFiles by index.
 */
export function removeFile(index) {
  uploadedFiles.splice(index, 1);
  renderFileList();
}
