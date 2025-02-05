# Azure OpenAI Service Quick Start & Reference Guide
(Based on API Specification v2025-01-01-preview)

## Authentication & Headers

```python
# Environment Variables (Best Practice)
AZURE_OPENAI_ENDPOINT = "https://{your-resource-name}.openai.azure.com"
AZURE_OPENAI_API_KEY = "your-api-key"
AZURE_OPENAI_DEPLOYMENT_ID = "your-deployment-id"  # e.g., "gpt-4", "gpt-35-turbo"
API_VERSION = "2025-01-01-preview"

# Required Headers
headers = {
    "Content-Type": "application/json",
    "api-key": AZURE_OPENAI_API_KEY,  # API Key Auth
    # OR for Bearer Token Auth:
    "Authorization": f"Bearer {token}"  # OAuth2.0 with api.read scope
}
```

## Chat Completions

### Basic Chat Request
```python
endpoint = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT_ID}/chat/completions"

basic_payload = {
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is Azure OpenAI?"}
    ],
    "temperature": 0.7,
    "max_tokens": 800
}

response = requests.post(
    f"{endpoint}?api-version={API_VERSION}",
    headers=headers,
    json=basic_payload
)
```

### Streaming Response
```python
streaming_payload = {
    "messages": [...],
    "stream": True,
    "stream_options": {
        "include_usage": True  # Get token usage stats in stream
    }
}

import sseclient

def process_stream(response):
    client = sseclient.SSEClient(response)
    buffer = ""
    
    try:
        for event in client.events():
            if event.event == "error":
                raise Exception(f"Stream error: {event.data}")
                
            if event.data == "[DONE]":
                break
                
            try:
                # Handle potential partial JSON chunks
                buffer += event.data
                if buffer.endswith("}"):
                    json_response = json.loads(buffer)
                    buffer = ""
                    yield json_response
            except json.JSONDecodeError:
                continue  # Wait for complete JSON
                
    except Exception as e:
        # Handle stream interruption
        print(f"Stream error: {str(e)}")
        raise

with requests.post(
    f"{endpoint}?api-version={API_VERSION}",
    headers=headers,
    json=streaming_payload,
    stream=True
) as response:
    for chunk in process_stream(response):
        # Process streaming response
```

### O1 Series Models Specific Features
```python
o1_payload = {
    "messages": [...],
    "max_completion_tokens": 1000,  # Instead of max_tokens
    "reasoning_effort": "high",     # "low", "medium", "high"
}
```

### GPT-4 Models with Vision
```python
vision_payload = {
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What's in this image?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{format};base64,{base64_string}" if is_base64 else url,
                        "detail": "high",  # "auto", "low", "high"
                        "format": format  # "png", "jpeg", etc.
                    }
                }
            ]
        }
    ]
}
```

## Vector Stores & File Management

### Create Vector Store
```python
vector_store_endpoint = f"{AZURE_OPENAI_ENDPOINT}/openai/vector_stores"

create_store_payload = {
    "name": "my-vector-store",
    "expires_after": {
        "anchor": "last_active_at",
        "days": 30
    },
    "chunking_strategy": {
        "type": "static",
        "static": {
            "max_chunk_size_tokens": 800,
            "chunk_overlap_tokens": 400
        }
    }
}

store_response = requests.post(
    f"{vector_store_endpoint}?api-version={API_VERSION}",
    headers=headers,
    json=create_store_payload
)
vector_store_id = store_response.json()["id"]
```

### Add Files to Vector Store
```python
files_endpoint = f"{vector_store_endpoint}/{vector_store_id}/files"

# Single File
single_file_payload = {
    "file_id": "existing-file-id",
    "chunking_strategy": {
        "type": "auto"  # Uses default settings
    }
}

# Batch Files
batch_endpoint = f"{vector_store_endpoint}/{vector_store_id}/file_batches"
batch_payload = {
    "file_ids": ["file-id-1", "file-id-2"],
    "chunking_strategy": {
        "type": "static",
        "static": {
            "max_chunk_size_tokens": 1000,
            "chunk_overlap_tokens": 200
        }
    }
}
```

## Best Practices & Tips

### 1. Model Selection
- **GPT-4 Series:**
  ```json
  {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 4096,
    "top_p": 1.0
  }
  ```
- **O1 Series:**
  ```json
  {
    "model": "o1-series-model",
    "max_completion_tokens": 1000,
    "reasoning_effort": "medium",
    "temperature": 0.7
  }
  ```

### 2. Content Safety & Filtering
```python
# Request with content filtering monitoring
payload = {
    "messages": [...],
    "user": "unique-user-id",  # For abuse monitoring
    "user_security_context": {
        "application_name": "your-app-name",
        "end_user_id": "user-entra-id",
        "end_user_tenant_id": "tenant-id",
        "source_ip": "user-ip"
    }
}
```

### 3. Structured Outputs
```python
# JSON Mode
payload = {
    "messages": [...],
    "response_format": {
        "type": "json_object"
    }
}

# Schema Mode
payload = {
    "messages": [...],
    "response_format": {
        "type": "json_object",
        "schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The person's full name"
                },
                "age": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "The person's age in years"
                }
            },
            "required": ["name"]
        }
    }
}
```

### 4. Tool Usage (Functions)
```python
payload = {
    "messages": [...],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "unit": {"type": "string", "enum": ["C", "F"]}
                    },
                    "required": ["location"]
                }
            }
        }
    ],
    "tool_choice": "auto"  # or "none" or specific tool
}
```

### 5. File Search Integration
```python
assistant_payload = {
    "model": "gpt-4",
    "tools": [{"type": "file_search"}],
    "tool_resources": {
        "file_search": {
            "vector_store_ids": ["your-vector-store-id"]
        }
    }
}
```

### 6. Error Handling
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import backoff

def is_rate_limit_error(e):
    return isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 429

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(is_rate_limit_error)
)
def make_api_request(endpoint, headers, payload):
    try:
        response = requests.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        # Check for content filter flags
        if "prompt_filter_results" in result:
            filters = result["prompt_filter_results"]
            # Handle content filtering results
            
        # Process successful response
        choices = result["choices"]
        usage = result["usage"]
        
        return result
        
    except requests.exceptions.HTTPError as e:
        error_response = e.response.json() if e.response else None
        if error_response and "error" in error_response:
            error = error_response["error"]
            error_code = error.get("code")
            error_message = error.get("message")
            
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 1))
                raise backoff.expo(f"Rate limited. Retry after: {retry_after}s")
                
            elif e.response.status_code == 503:
                raise backoff.expo("Service unavailable. Retrying...")
                
            # Handle other specific error codes
            raise
```

### 7. Token Usage Monitoring
```python
# Track token usage in responses
def monitor_token_usage(response_json):
    usage = response_json.get("usage", {})
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "prompt_tokens_details": usage.get("prompt_tokens_details", {}),
        "completion_tokens_details": usage.get("completion_tokens_details", {})
    }
```

### 8. Environment Configuration
```python
# config.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    api_version: str = "2025-01-01-preview"
    deployment_id: str
    
    # Optional configurations
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0
    presence_penalty: float = 0
```

### 9. Rate Limiting & Retry Logic
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def make_api_request(endpoint, payload, headers):
    response = requests.post(endpoint, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()
```

This guide provides a foundation for working with the Azure OpenAI Service API based on the specification. Always refer to the latest documentation for updates and best practices, as the service evolves rapidly.

Remember to:
- Handle authentication securely
- Implement proper error handling
- Monitor and log API usage
- Use appropriate model parameters based on your use case
- Implement rate limiting and retry logic
- Follow content safety guidelines
- Test thoroughly in non-production environments first
