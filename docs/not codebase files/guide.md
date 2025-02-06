# Azure OpenAI API Comprehensive Guide

## 1. Authentication

### Setup Environment Variables
```env
# .env file
AZURE_OPENAI_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
```

### Authentication Methods

```python
import os
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables
load_dotenv()

# Method 1: API Key Authentication
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# Method 2: Microsoft Entra ID Authentication
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)

client_entra = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_ad_token_provider=token_provider,
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)
```

## 2. Chat Completion

### Basic Chat Completion
```python
def basic_chat_completion(client, prompt):
    try:
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error: {e}")
        return None

# Usage
response = basic_chat_completion(client, "What is Azure OpenAI?")
print(response)
```

### Multi-turn Conversation
```python
def chat_conversation(client):
    conversation = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]

    try:
        while True:
            user_input = input("You: ")
            if user_input.lower() == 'quit':
                break

            conversation.append({"role": "user", "content": user_input})

            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                messages=conversation
            )

            assistant_response = response.choices[0].message.content
            conversation.append({"role": "assistant", "content": assistant_response})

            print(f"Assistant: {assistant_response}\n")

    except Exception as e:
        print(f"Error: {e}")

# Usage
chat_conversation(client)
```

## 3. Chat Completion with Streaming

### Basic Streaming
```python
def stream_chat_completion(client, prompt):
    try:
        stream = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            messages=[
                {"role": "user", "content": prompt}
            ],
            stream=True
        )

        print("Assistant: ", end="", flush=True)
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n")

    except Exception as e:
        print(f"Error: {e}")

# Usage
stream_chat_completion(client, "Tell me a story about a brave knight")
```

### Streaming with Conversation History
```python
def streaming_conversation(client):
    conversation = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]

    try:
        while True:
            user_input = input("You: ")
            if user_input.lower() == 'quit':
                break

            conversation.append({"role": "user", "content": user_input})

            stream = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                messages=conversation,
                stream=True
            )

            print("Assistant: ", end="", flush=True)
            assistant_response = ""

            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    assistant_response += content
                    print(content, end="", flush=True)

            print("\n")
            conversation.append({"role": "assistant", "content": assistant_response})

    except Exception as e:
        print(f"Error: {e}")

# Usage
streaming_conversation(client)
```

## 4. Response Format

### Understanding Response Structure
```python
def examine_response_structure(client, prompt):
    try:
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Print full response structure
        print("Full Response Structure:")
        print(response.model_dump_json(indent=2))

        # Access specific components
        print("\nKey Components:")
        print(f"Model ID: {response.model}")
        print(f"Created Timestamp: {response.created}")
        print(f"Response Content: {response.choices[0].message.content}")
        print(f"Finish Reason: {response.choices[0].finish_reason}")
        print(f"Usage - Prompt Tokens: {response.usage.prompt_tokens}")
        print(f"Usage - Completion Tokens: {response.usage.completion_tokens}")
        print(f"Usage - Total Tokens: {response.usage.total_tokens}")

        return response

    except Exception as e:
        print(f"Error: {e}")
        return None

# Usage
response = examine_response_structure(client, "What is the capital of France?")
```

### Response Processing Utilities
```python
class ResponseProcessor:
    @staticmethod
    def extract_message_content(response):
        """Extract just the message content from the response"""
        return response.choices[0].message.content

    @staticmethod
    def get_token_usage(response):
        """Extract token usage information"""
        return {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }

    @staticmethod
    def get_finish_reason(response):
        """Get the finish reason"""
        return response.choices[0].finish_reason

    @staticmethod
    def format_response_summary(response):
        """Create a formatted summary of the response"""
        return {
            'content': response.choices[0].message.content,
            'model': response.model,
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            },
            'finish_reason': response.choices[0].finish_reason
        }

# Usage Example
def process_chat_response(client, prompt):
    try:
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Use the response processor
        processor = ResponseProcessor()

        # Get just the content
        content = processor.extract_message_content(response)
        print(f"Content: {content}\n")

        # Get token usage
        usage = processor.get_token_usage(response)
        print(f"Token Usage: {usage}\n")

        # Get complete summary
        summary = processor.format_response_summary(response)
        print("Complete Summary:")
        print(json.dumps(summary, indent=2))

    except Exception as e:
        print(f"Error: {e}")

# Usage
process_chat_response(client, "Explain quantum computing in simple terms")
```

### Error Handling and Response Validation
```python
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ChatResponse:
    content: str
    usage: Dict[str, int]
    finish_reason: str
    raw_response: Any

    @classmethod
    def from_api_response(cls, response) -> 'ChatResponse':
        return cls(
            content=response.choices[0].message.content,
            usage={
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            },
            finish_reason=response.choices[0].finish_reason,
            raw_response=response
        )

def safe_chat_completion(
    client,
    prompt: str,
    max_retries: int = 3
) -> Optional[ChatResponse]:
    """
    Safely handle chat completion with retries and proper error handling
    """
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return ChatResponse.from_api_response(response)

        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Final attempt failed: {e}")
                return None
            print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
            time.sleep(1 * (attempt + 1))  # Exponential backoff

# Usage
result = safe_chat_completion(client, "What is machine learning?")
if result:
    print(f"Content: {result.content}")
    print(f"Token Usage: {result.usage}")
    print(f"Finish Reason: {result.finish_reason}")
```

This guide covers the main aspects of working with the Azure OpenAI API, including authentication, different types of chat completions, streaming, and response handling. Remember to handle errors appropriately and implement retry logic for production use cases.
