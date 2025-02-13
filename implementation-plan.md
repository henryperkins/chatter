# File Upload Interface Improvement Plan - Core Issues

## 1. File Integration & Staging Issues

### Problem
- Files appear as duplicates because they're not properly integrated with the backend
- Files are just visual placeholders without proper system integration
- Close buttons lack proper system feedback

### Solution
1. Implement proper file tracking:
```javascript
class FileTracker {
    constructor() {
        this.stagedFiles = new Map(); // Track files by unique ID
        this.uploadedFiles = new Map(); // Track successfully uploaded files
    }
    
    addFile(file) {
        const fileId = generateUniqueId(file);
        if (!this.stagedFiles.has(fileId) && !this.uploadedFiles.has(fileId)) {
            this.stagedFiles.set(fileId, file);
            return true;
        }
        return false;
    }
}
```

2. Implement proper backend integration:
```javascript
async function uploadFile(file) {
    // Generate unique file ID
    const fileId = await generateFileId(file);
    
    // Check if file already exists in system
    const exists = await checkFileExists(fileId);
    if (exists) {
        return { error: 'File already exists' };
    }
    
    // Upload and verify
    const result = await uploadToServer(file);
    if (result.success) {
        // Update system records
        await updateSystemRecords(fileId, result.metadata);
        return result;
    }
}
```

3. Add proper system feedback:
```javascript
async function removeFile(fileId) {
    // Remove from backend first
    const removed = await removeFromSystem(fileId);
    if (removed) {
        // Then update UI
        this.stagedFiles.delete(fileId);
        this.updateUI();
    }
    return removed;
}
```

## 2. Mobile Upload Reliability

### Problem
- Upload button frequently fails on mobile devices
- No proper error handling or recovery
- No network condition handling

### Solution
1. Implement proper mobile upload handling:
```javascript
class MobileUploadManager {
    constructor() {
        this.networkMonitor = new NetworkMonitor();
        this.uploadQueue = new UploadQueue();
    }
    
    async upload(file) {
        // Check network conditions
        if (!this.networkMonitor.isReliable()) {
            return this.queueForLater(file);
        }
        
        // Implement chunked upload for large files
        if (file.size > CHUNK_SIZE) {
            return this.chunkedUpload(file);
        }
        
        // Regular upload with retry logic
        return this.reliableUpload(file);
    }
    
    async reliableUpload(file, retries = 3) {
        try {
            return await this.uploadWithProgress(file);
        } catch (error) {
            if (retries > 0 && this.isRetryableError(error)) {
                await this.wait(1000);
                return this.reliableUpload(file, retries - 1);
            }
            throw error;
        }
    }
}
```

## 3. Token Counting Accuracy

### Problem
- Token counts are inaccurate
- No proper validation against system limits
- No handling of different file types

### Solution
1. Implement accurate token counting:
```javascript
class TokenCounter {
    constructor() {
        this.typeHandlers = new Map([
            ['text/plain', this.countTextTokens],
            ['application/pdf', this.countPDFTokens],
            ['application/msword', this.countWordTokens]
        ]);
    }
    
    async countTokens(file) {
        const handler = this.typeHandlers.get(file.type);
        if (!handler) {
            return this.estimateTokens(file);
        }
        
        const count = await handler(file);
        await this.validateAgainstLimits(count);
        return count;
    }
    
    async validateAgainstLimits(count) {
        const systemLimits = await getSystemLimits();
        if (count > systemLimits.maxTokens) {
            throw new TokenLimitError(count, systemLimits.maxTokens);
        }
    }
}
```

## 4. Interface Layout & Visibility

### Problem
- Chat window being obscured by panels
- Inactive grey protrusion above tab menu
- Poor layout on mobile devices

### Solution
1. Implement proper layout management:
```javascript
class LayoutManager {
    constructor() {
        this.panels = new Set();
        this.visibilityObserver = new IntersectionObserver(
            this.handleVisibilityChange.bind(this)
        );
    }
    
    handleVisibilityChange(entries) {
        for (const entry of entries) {
            if (entry.target.classList.contains('chat-message') && 
                entry.intersectionRatio < 0.5) {
                this.adjustPanels();
            }
        }
    }
    
    adjustPanels() {
        const chatVisible = this.ensureChatVisible();
        if (!chatVisible) {
            this.collapsePanels();
        }
    }
}
```

## Implementation Strategy

1. Phase 1: Core System Integration
- Implement FileTracker
- Add proper backend integration
- Set up system validation

2. Phase 2: Mobile Reliability
- Implement MobileUploadManager
- Add network monitoring
- Implement retry logic

3. Phase 3: Token Accuracy
- Implement TokenCounter
- Add proper validation
- Implement type-specific handlers

4. Phase 4: Layout Fixes
- Implement LayoutManager
- Fix panel behavior
- Ensure chat visibility

## Success Criteria

1. System Integration
- No duplicate files possible
- All files properly tracked in system
- Proper feedback for all operations

2. Mobile Reliability
- Successful uploads on various network conditions
- Proper error recovery
- Progress tracking and resume capability

3. Token Accuracy
- Accurate counts for all file types
- Proper system limit validation
- Clear feedback on limits

4. Layout
- Chat always visible
- No UI glitches
- Proper mobile layout

## Testing Requirements

1. Integration Tests
- File tracking accuracy
- System synchronization
- Error handling

2. Mobile Tests
- Network condition handling
- Upload reliability
- Error recovery

3. Token Tests
- Counting accuracy
- Limit validation
- Type handling

4. Layout Tests
- Visibility checks
- Panel behavior
- Mobile responsiveness