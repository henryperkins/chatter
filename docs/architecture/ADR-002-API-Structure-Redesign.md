# ADR 002: API Structure Redesign

## Status
Proposed

## Context
To support the new chat interface architecture proposed in ADR-001, we need to ensure our API structure is optimized for:
- Real-time communication
- Efficient data loading
- Scalable state management
- Enhanced collaboration features
- Better error handling

## Decision
We propose to restructure the API with the following changes:

### 1. RESTful Resource Endpoints

```
/api/v1/
  /conversations
    GET    /                 # List conversations (paginated)
    POST   /                 # Create new conversation
    GET    /{id}            # Get conversation details
    PUT    /{id}            # Update conversation
    DELETE /{id}            # Delete conversation
    GET    /{id}/messages   # Get messages (paginated)
    POST   /{id}/messages   # Add message
    GET    /{id}/export     # Export conversation
    POST   /{id}/branch     # Create conversation branch

  /models
    GET    /                 # List available models
    GET    /{id}            # Get model details
    POST   /{id}/select     # Select model for conversation

  /files
    POST   /upload          # Upload file (chunked)
    GET    /{id}            # Get file metadata
    GET    /{id}/content    # Get file content
    DELETE /{id}            # Delete file

  /users
    GET    /me              # Get current user
    PUT    /me              # Update user preferences
    GET    /me/usage        # Get token usage stats
```

### 2. WebSocket Events

```javascript
// Client -> Server Events
{
  type: 'message.send',
  payload: {
    conversation_id: string,
    content: string,
    files?: string[]
  }
}

{
  type: 'typing.start',
  payload: {
    conversation_id: string
  }
}

// Server -> Client Events
{
  type: 'message.received',
  payload: {
    id: string,
    conversation_id: string,
    content: string,
    timestamp: string
  }
}

{
  type: 'typing.update',
  payload: {
    conversation_id: string,
    user_id: string,
    status: 'typing' | 'idle'
  }
}
```

### 3. Response Structure

```javascript
// Success Response
{
  success: true,
  data: {
    // Response data
  },
  meta?: {
    pagination?: {
      page: number,
      per_page: number,
      total: number
    },
    usage?: {
      tokens: number,
      cost: number
    }
  }
}

// Error Response
{
  success: false,
  error: {
    code: string,
    message: string,
    details?: any
  }
}
```

### 4. Caching Strategy

```python
# Cache Configuration
CACHE_CONFIG = {
    'conversation_list': {
        'ttl': 300,  # 5 minutes
        'max_size': 1000
    },
    'conversation_detail': {
        'ttl': 600,  # 10 minutes
        'max_size': 500
    },
    'message_list': {
        'ttl': 3600,  # 1 hour
        'max_size': 10000
    }
}

# Example Cache Implementation
class CacheManager:
    def get_conversation(self, id):
        key = f'conversation:{id}'
        return cache.get(key)

    def set_conversation(self, id, data):
        key = f'conversation:{id}'
        cache.set(key, data,
                 timeout=CACHE_CONFIG['conversation_detail']['ttl'])
```

### 5. Rate Limiting

```python
RATE_LIMITS = {
    'message_create': {
        'rate': '60/minute',
        'burst': 5
    },
    'file_upload': {
        'rate': '100/hour',
        'burst': 10
    },
    'model_switch': {
        'rate': '10/minute',
        'burst': 2
    }
}
```

## Consequences

### Positive
- Clear API structure and conventions
- Better support for real-time features
- Improved error handling
- Efficient caching
- Better rate limiting
- Versioned API endpoints

### Negative
- Additional complexity in API layer
- Need for API documentation
- Migration of existing endpoints
- Potential temporary backward compatibility issues

### Neutral
- Need for client library updates
- Additional monitoring requirements
- Updated testing requirements

## Implementation Plan

### Phase 1: Core API Structure
1. Set up new API routes
2. Implement response structure
3. Add basic error handling
4. Set up API versioning

### Phase 2: Real-time Features
1. Implement WebSocket server
2. Add event handlers
3. Set up client connections
4. Add real-time features

### Phase 3: Performance
1. Implement caching
2. Add rate limiting
3. Optimize response times
4. Add monitoring

### Phase 4: Migration
1. Create compatibility layer
2. Migrate existing endpoints
3. Update documentation
4. Deploy gradually

## Technical Details

### Authentication

```python
@dataclass
class TokenPayload:
    sub: str  # user_id
    exp: int  # expiration timestamp
    scope: List[str]  # user permissions

class AuthMiddleware:
    def authenticate(self, request):
        token = request.headers.get('Authorization')
        if not token:
            raise Unauthorized()

        try:
            payload = jwt.decode(token, settings.JWT_SECRET)
            return TokenPayload(**payload)
        except jwt.InvalidTokenError:
            raise Unauthorized()
```

### Request Validation

```python
from pydantic import BaseModel, Field

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=32000)
    model_id: str = Field(...)
    files: List[str] = Field(default_factory=list)

    class Config:
        schema_extra = {
            "example": {
                "content": "Hello, world!",
                "model_id": "gpt-4",
                "files": ["file1.pdf", "file2.jpg"]
            }
        }
```

### Error Handling

```python
class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code

@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message
            }
        }
    )
```

## Success Metrics

1. Performance
- API response time < 100ms (p95)
- WebSocket latency < 50ms
- Cache hit rate > 80%
- Error rate < 0.1%

2. Scalability
- Support 1000+ concurrent users
- Handle 100+ messages/second
- Maintain performance under load
- Efficient resource usage

3. Reliability
- 99.9% uptime
- Zero data loss
- Graceful degradation
- Quick error recovery

## References

- [REST API Best Practices](https://www.vinaysahni.com/best-practices-for-a-pragmatic-restful-api)
- [WebSocket Protocol](https://tools.ietf.org/html/rfc6455)
- [JSON API Specification](https://jsonapi.org/)
- [Rate Limiting Best Practices](https://cloud.google.com/architecture/rate-limiting-strategies-techniques)
