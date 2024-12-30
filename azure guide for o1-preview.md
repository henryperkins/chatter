# Guide for Azure OpenAI

## 1. Authentication Guide for Azure OpenAI API

**Overview:**
To use the Azure OpenAI API, you need to authenticate requests with an API key. This guide covers environment setup and authentication. The default API version is `2024-10-01-preview`.

**Initialize the Client:**
Use `AzureOpenAI` for synchronous or `AsyncAzureOpenAI` for asynchronous operations. Initialize with your endpoint, API key, and desired `api_version`.

```python
import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()
azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
api_key = os.getenv('AZURE_OPENAI_KEY')
api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-10-01-preview')

client = AzureOpenAI(
    azure_endpoint=azure_endpoint,
    api_key=api_key,
    api_version=api_version
)
```

**Validate the Connection:**
Make a simple API call to validate your setup.

```python
response = client.chat.completions.create(
    model="gpt-35-turbo",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=10
)
print("Connection successful!")
print(response.choices[0].message.content)
```

### Debugging Tips
* **Check Environment Variables:** Ensure variables are set correctly.
* **API Key Validity:** Verify your API key is active.
* **Endpoint URL:** Double-check the endpoint URL.
* **API Version:** Use the correct `api_version`.
* **Error Handling:** Implement error handling.

### References
* [Azure OpenAI Quickstart Guide](https://learn.microsoft.com/en-us/azure/ai-services/openai/quickstart)
* [Python Dotenv Documentation](https://pypi.org/project/python-dotenv/)
* [Switching between Azure OpenAI and OpenAI endpoints](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/switching-endpoints?source=recommendations)

## 2. Using `o1-preview` Models from Azure OpenAI

**Overview:**
`o1-preview` models have specific requirements.

**Specific Requirements of `o1-preview` Models:**
1.  **No System Messages:** Do not include system messages.
2.  **No Streaming:** Use non-streaming methods.
3.  **Temperature Fixed at 1:** Set `temperature` to 1.
4.  **`max_completion_tokens`:** Use `max_completion_tokens`.
5.  **Specific API Version:** Use `2024-12-01-preview` or newer.

**Example API Call for `o1-preview`:**
```python
from openai import AzureOpenAI
client = AzureOpenAI(
  api_version="2024-12-01-preview",
  azure_endpoint="https://your-resource.openai.azure.com/",
  api_key=os.getenv("AZURE_OPENAI_API_KEY"),
)
response = client.chat.completions.create(
    model="your-o1-preview-deployment",
    messages=[{"role": "user", "content": "Your prompt here"}],
    temperature=1,
    max_completion_tokens=500,
)
print(response.model_dump_json(indent=2))
```

**Important Considerations:**
*   **Verify Feature Support:** Check supported features.
*   **Error Handling:** Implement specific error handling.
*   **User Guidance:** Provide clear configuration instructions.

**Reference:**
[Azure OpenAI o1 series reasoning models](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/reasoning?tabs=python#usage)


## 5. Token Management and Cost Optimization

**Overview:**
Manage token usage for cost optimization. Limit tokens in prompts and responses. The Assistants API supports `max_prompt_tokens` and `max_completion_tokens`.

```python
from tiktoken import encoding_for_model

def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    encoding = encoding_for_model(model)
    return len(encoding.encode(text))

def optimize_prompt(text: str, max_tokens: int = 4000):
    current_tokens = estimate_tokens(text)
    if current_tokens > max_tokens:
        encoding = encoding_for_model("gpt-4")
        tokens = encoding.encode(text)
        truncated_tokens = tokens[:max_tokens]
        return encoding.decode(truncated_tokens)
    return text

def managed_completion(prompt: str, max_tokens: int = 4000):
    optimized_prompt = optimize_prompt(prompt, max_tokens)
    estimated_cost = estimate_tokens(optimized_prompt) * 0.00002
    print(f"Estimated tokens: {estimate_tokens(optimized_prompt)}")
    print(f"Estimated cost: ${estimated_cost:.4f}")
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": optimized_prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content
```

**Reference:**
[Token Management Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/manage-tokens)

## 6. Error Handling and Monitoring

**Overview:**
Implement error handling with specific error types and enhanced monitoring.

```python
from enum import Enum
from typing import Optional, Dict, Any
from openai import AzureOpenAI
from pydantic import BaseModel

class OpenAIErrorType(Enum):
    RATE_LIMIT = "rate_limit_error"
    QUOTA_EXCEEDED = "quota_exceeded_error"
    INVALID_REQUEST = "invalid_request_error"
    API_ERROR = "api_error"
    RESPONSIBLE_AI_POLICY_VIOLATION = "ResponsibleAIPolicyViolation"

class OpenAIErrorHandler:
    def __init__(self):
        self.error_counts: Dict[str, int] = {error.value: 0 for error in OpenAIErrorType}
    def handle_error(self, error: Exception) -> Dict[str, Any]:
        error_response = {
            "success": False,
            "error_type": None,
            "message": str(error),
            "retry_after": None,
            "content_filter_results": None
        }
        if hasattr(error, 'response'):
            error_data = error.response.json().get('error', {})
            error_type = error_data.get('type')
            inner_error = error_data.get('inner_error', {})
            if inner_error and inner_error.get('content_filter_results'):
                error_response["content_filter_results"] = inner_error.get('content_filter_results')
            if error_type:
                self.error_counts[error_type] += 1
                error_response["error_type"] = error_type
                if error_type == OpenAIErrorType.RATE_LIMIT.value:
                    error_response["retry_after"] = error.response.headers.get('Retry-After')
            if error_type == OpenAIErrorType.RESPONSIBLE_AI_POLICY_VIOLATION.value:
                if inner_error and inner_error.get('content_filter_results'):
                    error_response["content_filter_results"] = inner_error.get('content_filter_results')
        return error_response

class EnhancedOpenAIMonitor:
    def __init__(self):
        self.request_metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0,
            "completion_tokens": 0,
            "prompt_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0
        }
        self.error_handler = OpenAIErrorHandler()
    def log_request(self, response: Optional[Dict] = None, error: Optional[Exception] = None):
        self.request_metrics["total_requests"] += 1
        if error:
            self.request_metrics["failed_requests"] += 1
            return self.error_handler.handle_error(error)
        if response:
            self.request_metrics["successful_requests"] += 1
            if 'usage' in response:
                self.request_metrics["total_tokens"] += response['usage'].get('total_tokens', 0)
                self.request_metrics["completion_tokens"] += response['usage'].get('completion_tokens', 0)
                self.request_metrics["prompt_tokens"] += response['usage'].get('prompt_tokens', 0)
                if 'prompt_tokens_details' in response['usage'] and response['usage']['prompt_tokens_details'] and response['usage']['prompt_tokens_details'].get("cached_tokens"):
                    self.request_metrics["cached_tokens"] += response['usage']['prompt_tokens_details'].get("cached_tokens", 0)
                if 'completion_tokens_details' in response['usage'] and response['usage']['completion_tokens_details'] and response['usage']['completion_tokens_details'].get('reasoning_tokens'):
                  self.request_metrics["reasoning_tokens"] += response['usage']['completion_tokens_details'].get("reasoning_tokens", 0)
        return {"success": True}
    def get_metrics_summary(self):
      return self.request_metrics

import asyncio
async def robust_completion_with_monitoring(prompt: str, monitor: EnhancedOpenAIMonitor, client: AzureOpenAI, retries: int = 3) -> Dict[str, Any]:
    for attempt in range(retries):
        try:
            response = await client.chat.completions.acreate(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}]
            )
            monitor.log_request(response=response.dict())
            return {
                "content": response.choices[0].message.content,
                "usage": response.usage.dict()
            }
        except Exception as e:
            error_response = monitor.log_request(error=e)
            if attempt == retries - 1:
                return error_response
            await asyncio.sleep(2 ** attempt)
```

**Reference:**
[Error Handling Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference)

## 7. Batch Processing with Rate Limiting

**Overview:**
Enhanced batch processing with rate limiting and quota management.

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio
from typing import List, Dict, Any
from openai import AzureOpenAI

@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    tokens_per_minute: int = 40000
    max_retries: int = 3
    retry_delay: float = 1.0

class RateLimiter:
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.request_timestamps: List[datetime] = []
        self.token_usage: List[tuple[datetime, int]] = []
        self.semaphore = asyncio.Semaphore(config.requests_per_minute)
    async def acquire(self, estimated_tokens: int = 0) -> bool:
        now = datetime.now()
        self.request_timestamps = [
            ts for ts in self.request_timestamps
            if ts > now - timedelta(minutes=1)
        ]
        self.token_usage = [
            (ts, tokens) for ts, tokens in self.token_usage
            if ts > now - timedelta(minutes=1)
        ]
        if len(self.request_timestamps) >= self.config.requests_per_minute:
            return False
        total_tokens = sum(tokens for _, tokens in self.token_usage)
        if total_tokens + estimated_tokens > self.config.tokens_per_minute:
            return False
        async with self.semaphore:
            self.request_timestamps.append(now)
            if estimated_tokens > 0:
                self.token_usage.append((now, estimated_tokens))
            return True

class EnhancedBatchProcessor:
    def __init__(self, rate_limiter: RateLimiter, client: AzureOpenAI, max_concurrent: int = 5):
        self.rate_limiter = rate_limiter
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.client = client
        self.results: List[Dict[str, Any]] = []
    async def process_item(self, item: str, estimated_tokens: int = 1000) -> Dict[str, Any]:
        async with self.semaphore:
            for attempt in range(self.rate_limiter.config.max_retries):
                if await self.rate_limiter.acquire(estimated_tokens):
                    try:
                        response = await self.client.chat.completions.acreate(
                            model="gpt-4",
                            messages=[{"role": "user", "content": item}]
                        )
                        return {
                            "input": item,
                            "output": response.choices[0].message.content,
                            "usage": response.usage.dict()
                        }
                    except Exception as e:
                        if "rate_limit" in str(e).lower():
                            await asyncio.sleep(
                                self.rate_limiter.config.retry_delay * (2 ** attempt)
                            )
                            continue
                        return {"input": item, "error": str(e)}
                await asyncio.sleep(self.rate_limiter.config.retry_delay)
            return {"input": item, "error": "Rate limit exceeded after retries"}
    async def process_batch(self, items: List[str], estimated_tokens_per_item: int = 1000) -> List[Dict[str, Any]]:
        tasks = [
            self.process_item(item, estimated_tokens_per_item)
            for item in items
        ]
        self.results = await asyncio.gather(*tasks)
        return self.results

rate_limit_config = RateLimitConfig(
    requests_per_minute=60,
    tokens_per_minute=40000,
    max_retries=3,
    retry_delay=1.0
)
rate_limiter = RateLimiter(rate_limit_config)
batch_processor = EnhancedBatchProcessor(rate_limiter, client)

async def process_with_monitoring(items: List[str]):
    start_time = datetime.now()
    results = await batch_processor.process_batch(items)
    successful = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    total_tokens = sum(r.get("usage", {}).get("total_tokens", 0) for r in successful)
    print(f"Processed {len(successful)} successfully, {len(failed)} failed")
    print(f"Total tokens used: {total_tokens}")
    print(f"Processing time: {datetime.now() - start_time}")
    return results
```

## 8. Advanced Prompt Management

**Overview:**
Enhanced prompt management with different message roles and structured content.

```python
from enum import Enum
from typing import List, Dict, Any, Optional
from openai import AzureOpenAI

class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class PromptTemplate:
    def __init__(self, template: str, required_variables: List[str], role: MessageRole = MessageRole.USER):
        self.template = template
        self.required_variables = required_variables
        self.role = role
    def format(self, variables: Dict[str, str]) -> Dict[str, str]:
        missing = [var for var in self.required_variables if var not in variables]
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        return {
            "role": self.role.value,
            "content": self.template.format(**variables)
        }

class EnhancedPromptManager:
    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}
        self.system_message: Optional[str] = None
    def set_system_message(self, message: str):
        self.system_message = message
    def add_template(self, name: str, template: PromptTemplate):
        self.templates[name] = template
    def create_messages(self, template_name: str, variables: Dict[str, str], include_system: bool = True) -> List[Dict[str, str]]:
        messages = []
        if include_system and self.system_message:
            messages.append({
                "role": MessageRole.SYSTEM.value,
                "content": self.system_message
            })
        if template_name not in self.templates:
            raise ValueError(f"Template {template_name} not found")
        messages.append(self.templates[template_name].format(variables))
        return messages
    async def execute(self, template_name: str, variables: Dict[str, str], client: AzureOpenAI, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        messages = self.create_messages(template_name, variables)
        request_params = {
            "model": "gpt-4",
            "messages": messages
        }
        if config:
            request_params.update(config)
        response = await client.chat.completions.acreate(**request_params)
        return {
            "content": response.choices[0].message.content,
            "usage": response.usage.dict(),
            "finish_reason": response.choices[0].finish_reason
        }

prompt_manager = EnhancedPromptManager()
prompt_manager.set_system_message(
    "You are a helpful assistant that provides clear and concise responses."
)
prompt_manager.add_template(
    "summarize",
    PromptTemplate(
        "Summarize the following {document_type} in {style} style:\n\n{content}",
        ["document_type", "style", "content"]
    )
)
prompt_manager.add_template(
    "analyze",
    PromptTemplate(
        "Analyze the following {data_type} and provide {analysis_type} analysis:\n\n{content}",
        ["data_type", "analysis_type", "content"]
    )
)
config = {
    "temperature": 0.7,
    "max_tokens": 500,
    "response_format": {"type": "json_object"}
}
```

**Reference:**
[Prompt Engineering Guide](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/prompt-engineering)

## 9. Advanced RAG with Hybrid Search

**Overview:**
Combine RAG with hybrid search. Includes integrated vectorization within Azure Search.

```python
from azure.search.documents.models import Vector
import numpy as np
from openai import AzureOpenAI

class HybridSearchRAG:
    def __init__(self, search_client, embedding_client: AzureOpenAI):
        self.search_client = search_client
        self.embedding_client = embedding_client
    async def get_embeddings(self, text: str):
        response = await self.embedding_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
    async def hybrid_search(self, query: str, top_k: int = 3):
        query_vector = await self.get_embeddings(query)
        results = self.search_client.search(
            search_text=query,
             vector_queries=[{
                "vector": query_vector,
                "k": top_k,
                 "fields": "content_vector"
            }],
            select=["content", "title"],
            top=top_k
        )
        return [{"content": doc["content"], "title": doc["title"]} for doc in results]

async def enhanced_rag_query(query: str, client: AzureOpenAI, search_client):
    rag = HybridSearchRAG(search_client, client)
    context_docs = await rag.hybrid_search(query)
    context = "\n".join([f"Title: {doc['title']}\nContent: {doc['content']}"
                         for doc in context_docs])
    response = await client.chat.completions.acreate(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"Context:\n{context}"},
            {"role": "user", "content": query}
        ]
    )
    return response.choices[0].message.content
```

**Reference:**
[Hybrid Search Documentation](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview)

## 10. Advanced Caching Strategy

**Overview:**
Implement caching to improve performance and reduce costs. Includes `cached_tokens` information.

```python
from functools import lru_cache
import hashlib
import redis
from typing import Optional

class ResponseCache:
    def __init__(self, redis_url: str):
        self.redis_client = redis.from_url(redis_url)
        self.default_ttl = 3600
    def generate_cache_key(self, prompt: str, model: str) -> str:
        content = f"{prompt}:{model}".encode()
        return hashlib.sha256(content).hexdigest()
    async def get_cached_response(self, prompt: str, model: str) -> Optional[str]:
        cache_key = self.generate_cache_key(prompt, model)
        cached = self.redis_client.get(cache_key)
        return cached.decode() if cached else None
    async def cache_response(self, prompt: str, model: str, response: str, ttl: int = None):
        cache_key = self.generate_cache_key(prompt, model)
        self.redis_client.setex(
            cache_key,
            ttl or self.default_ttl,
            response.encode()
        )

class CachedOpenAIClient:
    def __init__(self, cache: ResponseCache, client: AzureOpenAI):
        self.cache = cache
        self.client = client
    async def get_completion(self, prompt: str, model: str = "gpt-4", use_cache: bool = True) -> str:
        if use_cache:
            cached_response = await self.cache.get_cached_response(prompt, model)
            if cached_response:
                return cached_response
        response = await self.client.chat.completions.acreate(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = response.choices[0].message.content
        if use_cache:
            await self.cache.cache_response(prompt, model, response_text)
        return response_text
```

**Reference:**
[Caching Documentation](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
[Prompt caching with Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/prompt-caching)


## 15. Implementing Retrieval-Augmented Generation (RAG)

**Overview:**
Use RAG to integrate external knowledge. Shows Azure Search and Assistants API usage.

```python
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI
from typing import List, Dict, Any, Optional

async def rag_query(user_query: str, client: AzureOpenAI, search_client: SearchClient):
    search_results = search_client.search(
        search_text=user_query,
        select=["content", "title"],
        top=3
    )
    context = "\n".join([doc["content"] for doc in search_results])
    messages = [
        {"role": "system", "content": "Use the following context to answer questions:\n" + context},
        {"role": "user", "content": user_query}
    ]
    response = await client.chat.completions.acreate(
        model="gpt-4",
        messages=messages,
        temperature=0.7
    )
    return response.choices[0].message.content

async def rag_assistant_query(user_query: str, client: AzureOpenAI, assistant_id: str, search_index_name: str, search_endpoint: str, search_key: str, embedding_deployment_name: str) -> Dict[str, Any]:
    thread = await client.beta.threads.create(
        metadata= { "search_index": search_index_name} ,
        tool_resources = {
             "file_search" : {
                 "vector_stores": [ {
                         "file_ids": [],
                          "metadata":  { "search_index": search_index_name}
                     }
                     ]
             }
         }
    )
    messages = await client.beta.threads.messages.create(
        thread_id = thread.id,
        role = "user",
        content = user_query
    )
    run = await client.beta.threads.runs.create(
            thread_id = thread.id,
            assistant_id = assistant_id,
            tools=[
                {
                      "type": "file_search",
                  }
            ],
            tool_resources={
                "file_search":{
                    "vector_store_ids":[]
                }
            },
        )
    while True:
      run_response = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
      if run_response.status == "completed":
        messages = await client.beta.threads.messages.list(thread_id=thread.id)
        assistant_message = [message for message in messages.data if message.role == "assistant"]
        response_text = assistant_message[-1].content[0].text.value if assistant_message and assistant_message[-1].content else None
        return {
          "response": response_text,
          "usage": None
        }
      if run_response.status in ["failed", "cancelled", "expired"]:
         return {
             "error": f"Run failed with status: {run_response.status}"
          }
      await asyncio.sleep(1)
```

**Reference:**
[RAG Documentation](https://learn.microsoft.com/en-us/azure/search/semantic-search-overview)

## 16. Generating Embeddings

**Overview:**
Generate embeddings for similarity search and clustering. Supports `dimensions` parameter.

```python
from openai import AzureOpenAI

async def generate_embeddings(text: str, client: AzureOpenAI, model: str ="text-embedding-ada-002", dimensions: Optional[int] = None):
    response = await client.embeddings.create(
        model=model,
        input=text,
        dimensions=dimensions
    )
    return response.data[0].embedding
```

**Reference:**
[Generating Embeddings Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/understand-embeddings)

## 18. Stream Response Processing

**Overview:**
Handle streaming responses for real-time content generation. Includes usage information with `stream_options`.

```python
from typing import AsyncGenerator, Dict, Any
from openai import AzureOpenAI

async def process_stream_response(prompt: str, client: AzureOpenAI) -> AsyncGenerator[str, None]:
    try:
        stream = await client.chat.completions.acreate(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
             stream_options = {"include_usage": True}
        )
        collected_messages = []
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                collected_messages.append(content)
                yield content
            elif chunk.usage:
                 yield f"Usage: {chunk.usage}"
    except Exception as e:
        yield f"Error during streaming: {str(e)}"

async def stream_example(client: AzureOpenAI):
    async for content in process_stream_response("Generate a story", client=client):
        print(content, end="", flush=True)
```

## 19. Advanced Configuration Management

**Overview:**
Fine-tune API responses with configurable parameters. Includes `max_prompt_tokens` and `max_completion_tokens` for Assistants API.

```python
from typing import Dict, Any, Optional
from dataclasses import dataclass
from openai import AzureOpenAI

@dataclass
class OpenAIConfig:
    temperature: float = 0.7
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    seed: Optional[int] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    max_prompt_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    def to_dict(self) -> Dict[str, Any]:
        config = {
            "temperature": self.temperature,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "seed": self.seed
        }
        if self.max_tokens:
             config["max_tokens"] = self.max_tokens
        if self.top_p:
              config["top_p"] = self.top_p
        return config
    def to_assistant_dict(self) -> Dict[str, Any]:
        config = {
            "temperature": self.temperature,
             "top_p": self.top_p,
             "max_prompt_tokens": self.max_prompt_tokens,
             "max_completion_tokens": self.max_completion_tokens
        }
        return config

class ConfigurableOpenAIClient:
    def __init__(self, config: OpenAIConfig, client: AzureOpenAI):
        self.config = config
        self.client = client
    async def get_completion(self, prompt: str, response_format: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        request_params = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": prompt}],
            **self.config.to_dict()
        }
        if response_format:
            request_params["response_format"] = response_format
        response = await self.client.chat.completions.acreate(**request_params)
        return {
            "content": response.choices[0].message.content,
            "usage": response.usage.dict()
        }
    async def get_assistant_run(self, assistant_id: str, thread_id: str, prompt: str, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        request_params = {
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            **self.config.to_assistant_dict()
        }
        if tools:
            request_params["tools"]=tools
        message = await client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=prompt
                )
        run = await client.beta.threads.runs.create(**request_params)
        while True:
            run_response = await self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_response.status == "completed":
              messages = await client.beta.threads.messages.list(thread_id=thread_id)
              assistant_message = [message for message in messages.data if message.role == "assistant"]
              response_text = assistant_message[-1].content[0].text.value if assistant_message and assistant_message[-1].content else None
              return {
                  "content": response_text,
                  "usage": run_response.usage.dict() if run_response.usage else None,
                  "status": run_response.status
                }
            if run_response.status in ["failed", "cancelled", "expired"]:
                 return {
                    "error": f"Run failed with status: {run_response.status}",
                    "usage": None
                  }
            await asyncio.sleep(1)
```

## 20. Response Validation and Processing

**Overview:**
Implement response validation and processing for all relevant schemas, including the Assistants API.

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from openai import AzureOpenAI

class ChatChoice(BaseModel):
    index: int
    message: Dict[str, Any]
    finish_reason: str

class ChatUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: Optional[Dict[str, int]] = None
    completion_tokens_details: Optional[Dict[str, int]] = None

class ChatResponse(BaseModel):
    id: str
    object: str = Field("chat.completion")
    created: int
    model: str
    choices: List[ChatChoice]
    usage: ChatUsage
    
class RunCompletionUsage(BaseModel):
  prompt_tokens: int
  completion_tokens: int
  total_tokens: int
  
class RunObject(BaseModel):
  id: str
  object: str = Field("thread.run")
  status: str
  usage: Optional[RunCompletionUsage] = None
  
class ThreadMessageTextContent(BaseModel):
    value: str
    annotations: List[Any]
    
class ThreadMessageContent(BaseModel):
    type: str
    text: Optional[ThreadMessageTextContent] = None

class MessageObject(BaseModel):
  id: str
  object: str = Field("thread.message")
  role: str
  content: List[ThreadMessageContent]
  
  
class ResponseValidator:
    def __init__(self):
        self.validators: Dict[str, Any] = {
            "chat.completion": ChatResponse,
            "thread.run": RunObject
        }
    def validate_response(self, response: Dict[str, Any], response_type: str = "chat.completion") -> Dict[str, Any]:
        if response_type not in self.validators:
            raise ValueError(f"Unknown response type: {response_type}")
        validator = self.validators[response_type]
        validated = validator(**response)
        return validated.dict()

class ResponseProcessor:
    def __init__(self, validator: ResponseValidator):
        self.validator = validator
    async def process_response(self, response: Dict[str, Any], response_type: str ="chat.completion", extract_content: bool = True) -> Dict[str, Any]:
        validated = self.validator.validate_response(response, response_type)
        if extract_content and response_type == "chat.completion":
            return {
                "content": validated["choices"][0]["message"]["content"],
                "usage": validated["usage"],
                "model": validated["model"],
                "finish_reason": validated["choices"][0]["finish_reason"]
            }
        elif extract_content and response_type == "thread.run":
           return {
              "status": validated["status"],
               "usage": validated["usage"] if validated.get("usage") else None
           }
        return validated

validator = ResponseValidator()
processor = ResponseProcessor(validator)

async def make_validated_request(prompt: str, client: AzureOpenAI) -> Dict[str, Any]:
    response = await client.chat.completions.acreate(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return await processor.process_response(response.dict())
```

