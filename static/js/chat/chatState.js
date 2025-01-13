// chatState.js
// Holds chat-related state and constants

// A unique instance ID per session/initialization
export const instanceId = Date.now();

// Current list of uploaded files
export let uploadedFiles = [];

// Chat configuration constants
export const MAX_FILES = 5;
export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
export const MAX_MESSAGE_LENGTH = 1000;

export const ALLOWED_FILE_TYPES = [
  'text/plain',
  'application/pdf',
  'text/x-python',
  'application/javascript',
  'text/markdown',
  'image/jpeg',
  'image/png',
  'text/csv'
];

/**
 * Adds new files to the list of uploaded files.
 * @param {File[]} files - An array of file objects to be added to the uploaded files list.
 * @description Appends the provided files to the existing `uploadedFiles` array, allowing multiple file uploads.
 * @throws {Error} If the total number of files exceeds the maximum allowed files (5).
 */
export function addFiles(files) {
  uploadedFiles = uploadedFiles.concat(files);
}

/**
 * Resets the list of uploaded files to an empty array.
 * 
 * @description Clears all files that have been previously added to the upload queue, typically used after files have been successfully sent or when a user wants to start over.
 * 
 * @returns {void}
 * 
 * @example
 * // Clear all uploaded files after sending
 * clearFiles();
 * // uploadedFiles is now an empty array
 */
export function clearFiles() {
  uploadedFiles = [];
}
