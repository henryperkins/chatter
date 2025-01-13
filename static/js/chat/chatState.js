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
 * Adds new valid files to our global state.
 */
export function addFiles(files) {
  uploadedFiles = uploadedFiles.concat(files);
}

/**
 * Clears out all uploaded files (e.g., after a successful send).
 */
export function clearFiles() {
  uploadedFiles = [];
}
