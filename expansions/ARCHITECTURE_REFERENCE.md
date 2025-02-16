# Chatter Platform Architecture Reference

## Core Architecture Patterns

### 1. Azure Integration
```python
# config.py - Endpoint Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT") 
  or "https://o1models.openai.azure.com"  # Hardcoded fallback

# Special Model Handling
MODEL_CONFIG = {
    "o1-preview": {
        "fixed_params": {
            "temperature": 1.0,  # Strict requirement
            "supports_streaming": False  # Disabled for all o1 models
        },
        "capabilities": {
            "max_tokens": 200000,  # Hard limit
            "valid_reasoning_efforts": ["low", "medium", "high"]  # Enforced values
        }
    }
}
```

### 2. Security Implementation
```python
# config.py - Encryption Handling
def _process_encryption_key(key: str) -> str:
    # Requires 32-byte key with Fernet validation
    key_bytes = base64.urlsafe_b64decode(key.encode())
    if len(key_bytes) != 32:
        key_bytes = key_bytes[:32].ljust(32, b'\0')  # Force 32-byte length

# Database Security
DATABASE_URI = urlparse(uri)._replace(scheme='postgresql')  # Auto-convert scheme
```

### 3. Frontend Initialization
```javascript
// core.js - Startup Sequence
init() {
    // 1. Monitoring first
    await this.initMonitoring();
    
    // 2. Parallel core dependencies
    await Promise.all([
        this.initializeMarkdown(),
        this.initializePrism(),
        this.initializeDarkMode()
    ]);
    
    // 3. Chat-specific components
    if (document.getElementById('chat-container')) {
        await this.initializeChatComponents();
    }
}
```

## Critical Configuration

### Azure Search Limits
```python
# azure_search_config.py
SEARCH_MAX_CONCURRENCY = 4  # Must match Azure tier limits
FILE_INDEX_NAME = "chatter-documents"  # Pre-configured index
```

### Model Constraints
```python
# config.py
DEFAULT_MAX_TOKENS = 200000  # Absolute maximum
DEFAULT_MAX_COMPLETION_TOKENS = 100000  # Response limit
VALID_REASONING_EFFORTS = ["low", "medium", "high"]  # Only allowed values
```

## Frontend Configuration

### Tailwind Design System
```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          900: '#1E3A8A'  // Deep azure blue
        },
        error: {
          900: '#7F1D1D'  // Dark error state
        }
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out'  // Required animation
      }
    }
  }
}
```

### Component Initialization
```javascript
// core.js - Dependency Tracking
components: {
    monitoring: false,  // Strict initialization order
    utils: false,
    markdown: false,
    prism: false,
    darkMode: false
}
```

## Error Handling Patterns

### Layered Error Recovery
```javascript
// core.js
handleInitializationError(error) {
    if (this.components.monitoring) {
        window.monitoring.logError(error);
    }
    this.showFallbackError('Initialization failed');
}

showFallbackError(message) {
    // DOM-based fallback when utils unavailable
    const errorDiv = document.createElement('div');
    errorDiv.className = 'fixed top-4 left-1/2 transform -translate-x-1/2 ...';
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);
}
```

## Development Constraints

### Build Process
```json
// package.json
"scripts": {
    "build": "npm run build:css && echo 'Build completed'",
    "build:css": "tailwindcss -i ./static/css/input.css -o ./static/css/output.css --minify"
}
```

### Model Validation
```python
# config.py
def validate_model_config(config: dict):
    if config.get("temperature") != 1.0:
        raise ValueError("o1-preview requires temperature=1.0")
    if config.get("max_completion_tokens", 0) > 100000:
        raise ValueError("Exceeds 100k token limit")
```

## Ethical Scraping Requirements
```python
# ethical_scraper.py
def get_delay():
    return random.uniform(2.5, 5.0)  # Enforced crawl interval

def validate_content(text):
    if len(text) < 500:
        raise ValueError("Insufficient content")
    if any(phrase in text for phrase in FORBIDDEN_PHRASES):
        raise PermissionError("Prohibited content")
```

## Development Workflow

```bash
# Environment setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt  # Contains 150+ strict versions

# Frontend build
npm install
npm run build  # Generates minified Tailwind CSS

# Runtime configuration
export AZURE_OPENAI_KEY="your-key-here"
export ENCRYPTION_KEY="32-byte-fernkey-here"
```

## Application Features

### Core Integrations
- **Azure OpenAI Orchestration**: Direct integration with o1-preview models requiring:
  - Fixed temperature (1.0) and top_p (1.0) values
  - Mandatory reasoning effort levels (low/medium/high)
  - 200k context window with strict 100k response limit

### Conversation Management
```python
# conversation_manager.py - Context Optimization
class ConversationManager:
    def _manage_context_window(self, chat_id: str, max_tokens: Optional[int]) -> None:
        """Implements hybrid context management with:
        - Semantic analysis of message relationships
        - Token density scoring
        - Priority retention of system messages"""
        if hasattr(self.context_manager, "get_context"):
            optimized_context = self.context_manager.get_context(messages)
        else:  # Fallback to time-based pruning
            optimized_context = messages[-MAX_MESSAGES:]

    def _truncate_content(self, content: str, encoding: Any) -> str:
        """Enforces 8k user message limit with graceful truncation"""
        tokens = encoding.encode(content)[:MAX_MESSAGE_TOKENS]
        return encoding.decode(tokens) + "\n[Content truncated]"

# Message validation pipeline
def add_message(self, chat_id: str, role: str, content: str, **kwargs):
    # Multi-stage validation:
    if role == "user" and count_tokens(content) > 8192:
        content = self._truncate_content(content)
    if "bleach" in content:  # Sanitize HTML
        content = bleach.clean(content)
    if role not in ["user", "assistant", "system"]:
        raise InvalidRoleError(role)
```
- **Context Optimization Strategies**:
  - Hybrid semantic + time-based pruning
  - Message priority scoring (system > user > assistant)
  - Relationship graph analysis
- **Validation Pipeline**:
  - Role whitelisting
  - HTML sanitization
  - Token limit enforcement
  - Attachment processing quarantine
- **Token Accounting**:
  - Per-message token metadata
  - Context window utilization tracking
  - Compression ratio monitoring
- **Cognitive Search Hybridization**: Azure Search integration with:
  - Document index pre-configured as "chatter-documents"
  - 4 concurrent connection limit enforcement
  - 1536-dimension embedding alignment

### Security Implementation
- **Fernet-based Encryption**: Requires 32-byte keys with automatic padding validation
- **PostgreSQL Scheme Enforcement**: Auto-conversion of postgres:// to postgresql://
- **Credential Validation Chains**:
  - 12+ character SECRET_KEY requirement
  - BCrypt-exclusive password hashing
  - JWT session tokens with 45-minute expiration

### Frontend Operations
- **Dependency Ordered Initialization**:
  1. Monitoring → 2. Utilities → 3. Markdown/Prism/DarkMode (parallel)
  4. Chat components (conditional)
- **Component State Tracking**: Real-time initialization monitoring through:
  ```javascript
  components: {
    monitoring: false,
    utils: false,
    markdown: false,
    prism: false,
    darkMode: false
  }
  ```
- **Fallback UI System**: DOM-based error displays when core utilities fail

### Content Processing
- **Ethical Scraping Framework**:
  - 2.5-5 second randomized request delays
  - 500-character minimum content threshold
  - Phrase blocklist enforcement ("user-generated content", etc.)
- **Markdown Security**:
  - Bleach-based sanitization with allowed tag whitelist
  - Prism.js code highlighting with safe language subset
  - iframe/content security policy enforcement

### Administrative Controls
- **Model Configuration Validation**:
  - Temperature locking for o1-series models
  - Versioned file storage with SHA-256 checksums
  - Per-provider rate limiting
- **Token Accounting**:
  - Input/output token tracking
  - Context window utilization analytics
  - Per-user/conversation token budgets

### Compliance Features
- **GDPR-ready Logging**:
  - 45-day retention policy
  - PII redaction pipelines
  - Right-to-be-forgotten automation
- **Access Controls**:
  - Role-based access (user/admin/system)
  - Account locking with temporal locks
  - Session cookie hardening (Secure/HttpOnly/SameSite)
