Based on your current chat.html, here's how to properly integrate the tabbed panel. You already have most of the structure in place - we just need to enhance the "Multi-Tab Usage Panel" section and ensure proper styling.

Replace your current usage panel section with this updated version:

```html
<!-- Multi-Tab Usage Panel -->
<div id="usage-panel" class="w-full bg-white/95 dark:bg-gray-800/95 p-2 rounded-t-md shadow-inner border-t border-gray-200 dark:border-gray-700">
    <!-- Tab Buttons -->
    <div class="usage-tabs flex gap-4 border-b border-gray-200 dark:border-gray-700 mb-2 px-2">
        <button class="tab flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100/90 dark:hover:bg-gray-700/90 transition-colors tab-active" 
                data-panel="token-usage-panel">
            <i class="fas fa-chart-pie"></i>
            Token Usage
        </button>
        <button class="tab flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100/90 dark:hover:bg-gray-700/90 transition-colors" 
                data-panel="file-usage-panel">
            <i class="fas fa-file-upload"></i>
            Files
        </button>
    </div>

    <!-- Token Usage Panel -->
    <div id="token-usage-panel" class="panel-content">
        <div class="token-panel-container">
            {% include 'partials/token_panel.html' %}
        </div>
    </div>

    <!-- File Usage Panel -->
    <div id="file-usage-panel" class="panel-content hidden">
        <div class="p-2">
            <!-- File List -->
            <div id="file-list" class="space-y-2 max-h-32 overflow-y-auto mb-3">
                <!-- Files will be dynamically inserted here -->
            </div>

            <!-- Upload Button -->
            <div class="flex justify-between items-center">
                <button id="upload-trigger" 
                        class="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors">
                    <i class="fas fa-upload"></i>
                    Upload File
                </button>
                <span class="text-xs text-gray-600 dark:text-gray-300">
                    Max size: 10MB
                </span>
            </div>
        </div>
    </div>
</div>
```

Add these styles to your chat.css:

```css
/* Tab Styling */
.usage-tabs .tab {
    position: relative;
}

.usage-tabs .tab.tab-active {
    background-color: rgba(var(--color-gray-100), 0.9);
}

.usage-tabs .tab.tab-active::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    right: 0;
    height: 2px;
    background-color: var(--color-blue-600);
}

/* File List Styling */
.file-item {
    @apply flex items-center justify-between bg-gray-100/50 dark:bg-gray-700/50 rounded-md px-3 py-2;
}

.file-item .file-name {
    @apply text-sm text-gray-700 dark:text-gray-300 truncate mr-2;
}

.file-item .file-size {
    @apply text-xs text-gray-500 dark:text-gray-400;
}

.file-item .remove-btn {
    @apply p-1 text-gray-400 hover:text-red-400 transition-colors;
}

/* Panel Animation */
.panel-content {
    transition: opacity 0.2s ease;
}

.panel-content.hidden {
    display: none;
    opacity: 0;
}
```

Update your file handling in chat.js:

```javascript
// Add to your existing initialization code
function initializeFilePanel() {
    const uploadTrigger = document.getElementById('upload-trigger');
    const fileInput = document.getElementById('file-upload'); // Your existing file input

    if (uploadTrigger && fileInput) {
        uploadTrigger.addEventListener('click', () => {
            fileInput.click();
        });
    }

    // Update file list when files change
    if (window.fileUploadManager) {
        window.fileUploadManager.onFilesChanged = updateFileList;
    }
}

function updateFileList() {
    const fileList = document.getElementById('file-list');
    if (!fileList || !window.fileUploadManager?.uploadedFiles) return;

    fileList.innerHTML = window.fileUploadManager.uploadedFiles.map(file => `
        <div class="file-item">
            <div class="flex items-center gap-2 flex-1">
                <i class="fas fa-file-alt text-gray-400"></i>
                <span class="file-name">${file.name}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
            </div>
            <button class="remove-btn" data-filename="${file.name}">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');

    // Add remove handlers
    fileList.querySelectorAll('.remove-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            window.fileUploadManager.removeFile(btn.dataset.filename);
        });
    });
}

// Add to your DOMContentLoaded handler
document.addEventListener('DOMContentLoaded', () => {
    initializeFilePanel();
});
```

This implementation:
1. Maintains your existing dark theme and styling
2. Works with your current FileUploadManager
3. Integrates with your existing file input
4. Uses your existing CSS classes and color scheme
5. Preserves all current functionality while adding the tabbed interface

The panel seamlessly integrates with your chat interface, matching the dark theme and providing a cohesive experience for managing both tokens and files.
