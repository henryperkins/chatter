### Using o1 Models from Azure OpenAI

**I. Setup and Prerequisites:**

1. **Azure OpenAI Resource:**
    *   Create an Azure OpenAI resource in your Azure subscription.
    *   Note your resource's **endpoint** (e.g., `https://your-resource-name.openai.azure.com`).

2. **Model Deployment:**
    *   Deploy an o1 model within your Azure OpenAI resource.
    *   Note the **deployment ID** you assign to your o1 model.

3. **API Key or Bearer Token:**
    *   Obtain your Azure OpenAI resource's **API key** from the Azure portal.
    *   Alternatively, if using Azure Active Directory authentication, set up the necessary configuration to obtain a **bearer token**.

4. **Python Environment:**
    *   Make sure you have Python 3.7 or later installed.
    *   Install the `requests` library: `pip install requests`

**II. Basic Chat Completion with o1 Models (Non-Streaming):**

This example demonstrates a simple chat interaction without streaming.

```python
import requests
import json

# Replace with your Azure OpenAI details
ENDPOINT = "https://your-resource-name.openai.azure.com/openai"
API_KEY = "YOUR_API_KEY"
DEPLOYMENT_ID = "YOUR_O1_MODEL_DEPLOYMENT_ID"
API_VERSION = "2024-12-01-preview"

CHAT_COMPLETIONS_URL = f"{ENDPOINT}/deployments/{DEPLOYMENT_ID}/chat/completions?api-version={API_VERSION}"

HEADERS = {
    "Content-Type": "application/json",
    "api-key": API_KEY,  # Or "Authorization": "Bearer YOUR_TOKEN"
}

def generate_chat_completion(messages):
    """
    Generates a chat completion using an o1 model.

    Args:
        messages: A list of chat messages (dictionaries) conforming to chatCompletionRequestMessage.

    Returns:
        A dictionary representing the API response, or None if an error occurred.
    """
    data = {
        "messages": messages,
        "max_tokens": 500,  # Adjust as needed
        "temperature": 0.7,
        "reasoning_effort": "medium",  # o1 model specific
        "max_completion_tokens": 256,  # o1 model specific
    }

    try:
        response = requests.post(CHAT_COMPLETIONS_URL, headers=HEADERS, json=data)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None

# Example Usage:
messages = [
    {
        "role": "developer",
        "content": "You are a friendly chatbot that answers questions accurately and concisely."
    },
    {"role": "user", "content": "What is the highest mountain in the world?"},
]

response = generate_chat_completion(messages)

if response:
    print(f"Response: {json.dumps(response, indent=2)}")
    assistant_message = response["choices"][0]["message"]["content"]
    print(f"\nAssistant: {assistant_message}")
```

**III. Chat Completion with Streaming:**

This example demonstrates how to receive responses in a streaming fashion.

```python
import requests
import json

# ... (ENDPOINT, API_KEY, DEPLOYMENT_ID, API_VERSION, HEADERS are the same)
CHAT_COMPLETIONS_URL = f"{ENDPOINT}/deployments/{DEPLOYMENT_ID}/chat/completions?api-version={API_VERSION}"

def generate_chat_completion_stream(messages):
    """
    Generates a chat completion using an o1 model with streaming.

    Args:
        messages: A list of chat messages (dictionaries).

    Yields:
        Chunks of the streamed response.
    """
    data = {
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7,
        "reasoning_effort": "high",  # Example of using high reasoning effort
        "max_completion_tokens": 256,
        "stream": True,  # Enable streaming
    }

    try:
        response = requests.post(CHAT_COMPLETIONS_URL, headers=HEADERS, json=data, stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode("utf-8")
                if decoded_line.startswith("data:"):
                    chunk = decoded_line[6:]  # Remove "data: "
                    if chunk.strip() == "[DONE]":
                        break
                    yield json.loads(chunk)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

# Example Usage:
messages = [
    {
        "role": "developer",
        "content": "You are a helpful assistant that explains complex topics in simple terms.",
    },
    {"role": "user", "content": "Explain the concept of artificial intelligence to me."},
]

for chunk in generate_chat_completion_stream(messages):
    # print(f"Received chunk: {chunk}")
    if "choices" in chunk:
      for choice in chunk["choices"]:
          if "delta" in choice and "content" in choice["delta"]:
              print(choice["delta"]["content"], end="", flush=True)

```

**IV. Handling o1 Model Specific Parameters:**

*   **`reasoning_effort`:**
    *   Experiment with different values (`low`, `medium`, `high`) to see the impact on response quality and latency.
    *   Consider using `low` for faster responses where deep reasoning is not critical.
    *   Use `high` for tasks that require more complex reasoning, but be prepared for potentially slower response times.

*   **`max_completion_tokens`:**
    *   Set this parameter to limit the total tokens generated by the model, including those used for reasoning.
    *   This can help control costs and prevent the model from generating excessively long responses.
    *   Remember to account for both the visible output and reasoning tokens when setting this value.

**V. Advanced Usage:**

1. **Adding `data_sources`:**
    *   If you want to integrate your model with Azure data sources like Azure Cognitive Search or Cosmos DB, you'll need to configure the `data_sources` parameter in your request.
    *   Refer to the OpenAPI specification section on `azureChatExtensionConfiguration` for detailed information on how to structure this parameter.

2. **Using `tools` and `tool_choice`:**
    *   The `tools` parameter lets you define functions the model can call. For o1, at this time, this is only `functions`.
    *   `tool_choice` gives you control over how the model uses those functions.
    *   Refer to the specification for the correct structure of the `tools` and `function` objects.

3. **Error Handling:**
    *   Implement robust error handling in your application to gracefully handle API errors, network issues, and unexpected responses.

4. **Conversation Management:**
    *   Your application will need to manage the conversation state by storing and updating the `messages` array as the conversation progresses.

**VI. Tips for o1 Models:**

*   **Experiment:** The best way to find the optimal settings for `temperature`, `top_p`, `reasoning_effort`, and other parameters is to experiment and see how they affect the model's responses in your specific application.
*   **Prompt Engineering:** Carefully craft your prompts (both `developer` and `user` messages) to guide the model towards the desired behavior. Provide clear instructions and context.
*   **Monitor Usage:** Keep track of your token usage to avoid unexpected costs.
*   **Stay Updated:** The Azure OpenAI service is constantly evolving. Stay informed about new features and updates by referring to the official documentation.

This guide, along with the code examples, will help you get started with integrating your chat application with Azure OpenAI using o1 models. Remember to adapt the examples to your application's specific requirements and explore the full capabilities of the API by referring to the OpenAPI specification.

---

### Advanced Usage Expanded

Okay, let's delve into the advanced usage of the Azure OpenAI API with o1 models, focusing on data sources, tools, error handling, and conversation management.

**1. Using `data_sources` for Grounding:**

The `data_sources` parameter is a powerful feature that lets you connect your o1 model to external data sources, enabling it to provide answers grounded in your specific data.

**Supported Data Sources:**

The OpenAPI spec you provided indicates support for these Azure data sources:

*   `azure_search` (Azure Cognitive Search)
*   `azure_cosmos_db` (Azure Cosmos DB for MongoDB vCore)
*   `elasticsearch` (Elasticsearch)
*   `mongo_db` (MongoDB)
*   `pinecone` (Pinecone)

**How it Works:**

1. **Configuration:** You configure the `data_sources` array in your `createChatCompletionRequest`. Each element in the array represents a data source.
2. **Query Augmentation:** When the model receives a user query, it can use the configured data sources to find relevant information.
3. **Context Injection:** The retrieved information is then injected into the model's context, allowing it to generate responses that are grounded in the data.
4. **Citations:** The response can include citations that indicate the source of the information, enhancing transparency and trustworthiness.

**Example (Azure Cognitive Search):**

```python
data_sources = [
    {
        "type": "azure_search",
        "parameters": {
            "endpoint": "YOUR_AZURE_SEARCH_ENDPOINT",
            "index_name": "YOUR_AZURE_SEARCH_INDEX_NAME",
            "fields_mapping": {
                "content_fields_separator": "\n",
                "content_fields": ["content"],
                "filepath_field": "filepath",
                "title_field": "title",
                "url_field": "url",
                "vector_fields": [
                   "contentVector"
                 ]
            },
            "in_scope": True,
            "query_type": "vectorSimpleHybrid",
            "semantic_configuration": "YOUR_SEMANTIC_CONFIG_NAME",
            "embedding_dependency": {
                "type": "deployment_name",
                "deployment_name": "YOUR_EMBEDDING_MODEL_DEPLOYMENT_ID"
            },
            "authentication": {
                "type": "api_key",
                "key": "YOUR_AZURE_SEARCH_ADMIN_KEY"
            }
        }
    }
]

messages = [
    {
        "role": "developer",
        "content": "You are a helpful assistant, grounding your answers in the provided data sources when possible."
    },
    {
        "role": "user",
        "content": "What are some recent developments in renewable energy?"
    }
]

data = {
    "messages": messages,
    "data_sources": data_sources,
    "max_tokens": 500,
    "temperature": 0.5,
}
```

**Explanation:**

*   **`type`: `azure_search`:** Specifies Azure Cognitive Search as the data source.
*   **`endpoint`:** Your Azure Cognitive Search endpoint.
*   **`index_name`:** The name of your search index.
*   **`fields_mapping`:**  Maps fields in your index to common fields like `content`, `title`, `url`, etc., so the model knows which fields to search.
*   **`in_scope`:** If `true`, only data from the provided source will be used.
*   **`query_type`**: Specifies the type of query to use, e.g., `vector` or `simple`.
*   **`semantic_configuration`:** For using semantic search.
*   **`embedding_dependency`**: For specifying which embedding model to use.
*   **`authentication`:**  Provides authentication credentials for accessing the search service.

**2. Using `tools` and `tool_choice`:**

The `tools` parameter allows you to extend the capabilities of your o1 model by enabling it to call custom functions (tools). `tool_choice` controls how and when the model uses these tools.

**Example:**

```python
# Define a simple function to be used as a tool
def get_current_weather(location):
    """Gets the current weather for a given location."""
    # In a real application, you would fetch weather data from an API here.
    # For this example, we'll just return a mock response.
    if location.lower() == "london":
        return json.dumps({"temperature": "22 degrees Celsius", "condition": "Sunny"})
    elif location.lower() == "tokyo":
        return json.dumps({"temperature": "25 degrees Celsius", "condition": "Cloudy"})
    else:
        return json.dumps({"error": "Location not found."})

# In your chat completion request:
data = {
    "messages": [
        {
            "role": "user",
            "content": "What's the weather like in London?"
        }
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Gets the current weather for a given location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state, e.g. San Francisco, CA"
                        }
                    },
                    "required": ["location"]
                }
            }
        }
    ],
    "tool_choice": "auto", # Let the model decide whether to use the tool
    "max_tokens": 256,
    "reasoning_effort": "medium"
}

# ... send request to Azure OpenAI ...
# In a real app, you would need to check the response to see if the model decided to call a tool.
# If it did, you would call the corresponding function and then send the result back to the model
# in a subsequent turn. This part is omitted in this example for brevity.
```

**Explanation:**

*   **Define a Function:** Create a Python function that performs the desired task (e.g., `get_current_weather`).
*   **Describe the Function:**  In the `tools` array, define a `function` object with:
    *   `name`: The name of your function.
    *   `description`: A description of what your function does.
    *   `parameters`: A JSON Schema that describes the input parameters your function expects.
*   **`tool_choice`:**
    *   `auto`: The model decides whether to call a tool.
    *   `none`: The model will not call a tool.
    *   `{"type": "function", "function": {"name": "get_current_weather"}}`: Forces the model to call the specified function.

**Handling Tool Calls in Your Application:**

1. **Check for Tool Calls:** In the response from the API, check the `choices[].message.tool_calls` array. If it's not empty, the model wants to call a tool.
2. **Execute the Tool:** Extract the `name` and `arguments` from the `tool_calls` array. Call the corresponding function in your application, passing the arguments.
3. **Send Tool Output Back:** Create a new message with the `role` set to `tool` and `content` set to the output of your function (serialized as a JSON string). Include the `tool_call_id` from the message. Append this message to the `messages` array.
4. **Make Another API Call:** Send the updated `messages` array back to the API to continue the conversation.

**3. Error Handling:**

*   **Network Errors:** Use `try...except` blocks to catch `requests.exceptions.RequestException` and handle network issues gracefully.
*   **API Errors:**
    *   Check the HTTP status code of the response using `response.status_code`.
    *   Handle status codes like 400 (Bad Request), 401 (Unauthorized), 429 (Too Many Requests), and 500 (Internal Server Error) appropriately.
    *   The `error` object in the response body will provide more details about the error.
*   **Data Source Errors:** If you're using `data_sources`, be prepared to handle errors that might occur when querying those sources.
*   **Tool Call Errors:** Handle potential errors when executing the functions you've defined as tools.

**4. Conversation Management:**

*   **Storing State:** Your application needs to store the conversation history (the `messages` array) between turns. You can use:
    *   In-memory storage (for simple applications or testing).
    *   Databases (e.g., Redis, PostgreSQL).
    *   Session management mechanisms provided by your web framework.

*   **Context Window:** Be mindful of the model's context window limit. You might need to implement strategies for truncating or summarizing older messages to prevent exceeding the limit. You can use the `truncation_strategy` object in your request to specify the strategy to use, as described in the specification.

*   **User Turns:** Ensure that user input is correctly formatted as a message with the `user` role before sending it to the API.

*   **System Messages:** Use `developer` messages to provide initial instructions and context to the model. You can update these instructions dynamically to influence the model's behavior during the conversation.

**Example of Handling a Tool Call (Simplified):**

```python
# ... (previous code)

response = generate_chat_completion(messages)

if response:
    choice = response["choices"][0]
    if choice["finish_reason"] == "tool_calls":
        tool_call = choice["message"]["tool_calls"][0]
        function_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])

        if function_name == "get_current_weather":
            tool_output = get_current_weather(arguments["location"])
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": tool_output,
                }
            )

            # Make another API call with the updated messages
            response = generate_chat_completion(messages)
            if response:
                print(response["choices"][0]["message"]["content"])

```

This is a simplified example and does not include the handling of streaming or other types of tool calls. You would need to adapt this logic for a real-world application. Remember that the example provided is a basic illustration. Real-world chat applications require more sophisticated error handling, state management, and potentially streaming. Always refer to the Azure OpenAI documentation for the most up-to-date information and best practices.

---
### Using `data_sources` with o1 Models

**`data_sources`: Grounding Your Model with External Data**

The `data_sources` parameter in the `createChatCompletionRequest` allows you to connect your Azure OpenAI o1 model to external data sources. This process is often referred to as "grounding" because it grounds the model's responses in real-world data, making them more relevant, accurate, and trustworthy.

**How It Works with o1 Models**

1. **Request Time:** When you send a chat completions request to the API, you include the `data_sources` array if you want to use data grounding.
2. **Query Augmentation:** The o1 model receives the user's query within the `messages` array. If `data_sources` are configured, the Azure OpenAI service will analyze the query and determine if it can be augmented with data from the specified sources. This might involve rewriting the query to make it more suitable for searching the external data.
3. **Data Retrieval:** The service then queries the configured data sources using the augmented query, and the model's reasoning capability specified by the `reasoning_effort` property.
4. **Context Injection:** Relevant data retrieved from the data sources is injected into the context that the o1 model uses to generate its response. This context is provided alongside the `messages` history.
5. **Response Generation:** The o1 model generates a response, taking into account both the conversation history in `messages` and the information retrieved from the data sources.
6. **Citations (Optional):** The response can include citations in the `context` field of the message. These citations indicate the source from which specific information was obtained, adding transparency and verifiability to the response.

**Structure of `data_sources`**

The `data_sources` parameter is an array of `azureChatExtensionConfiguration` objects. Each object defines a single data source.

```json
"data_sources": [
  {
    "type": "azure_search", // Or "azure_cosmos_db", "elasticsearch", "mongo_db", "pinecone"
    "parameters": {
      // ... specific parameters for the data source type ...
    }
  }
]
```

**Supported Data Sources (Based on the Spec):**

*   **`azure_search`:** Azure Cognitive Search
*   **`azure_cosmos_db`:** Azure Cosmos DB for MongoDB vCore
*   **`elasticsearch`:** Elasticsearch
*   **`mongo_db`:** MongoDB
*   **`pinecone`:** Pinecone

**`azureChatExtensionConfiguration`:**

This object has two main properties:

*   **`type`:** A string that specifies the type of data source (e.g., `"azure_search"`).
*   **`parameters`:** An object that contains the configuration parameters specific to the data source type.

**Example: Configuring Azure Cognitive Search (`azure_search`)**

Let's break down the example I provided earlier for Azure Cognitive Search:

```json
"data_sources": [
    {
        "type": "azure_search",
        "parameters": {
            "endpoint": "YOUR_AZURE_SEARCH_ENDPOINT",
            "index_name": "YOUR_AZURE_SEARCH_INDEX_NAME",
            "fields_mapping": {
                "content_fields_separator": "\\n",
                "content_fields": ["content"],
                "filepath_field": "filepath",
                "title_field": "title",
                "url_field": "url",
                "vector_fields": [
                  "contentVector"
                ]
            },
            "in_scope": true,
            "query_type": "vectorSimpleHybrid",
            "semantic_configuration": "YOUR_SEMANTIC_CONFIG_NAME",
            "embedding_dependency": {
                "type": "deployment_name",
                "deployment_name": "YOUR_EMBEDDING_MODEL_DEPLOYMENT_ID"
            },
            "authentication": {
                "type": "api_key",
                "key": "YOUR_AZURE_SEARCH_ADMIN_KEY"
            }
        }
    }
]
```

**Explanation of Parameters:**

*   **`endpoint`:** The endpoint URL of your Azure Cognitive Search service.
*   **`index_name`:** The name of the search index you want to use.
*   **`fields_mapping`:**  This is crucial for mapping fields in your search index to the fields that the o1 model expects:
    *   **`content_fields_separator`:** A separator used to join multiple content fields.
    *   **`content_fields`:** An array of fields in your index that contain the primary content to be searched.
    *   **`filepath_field`:** The field that contains file paths (if applicable).
    *   **`title_field`:** The field that contains document titles.
    *   **`url_field`:** The field that contains URLs (if applicable).
    *   **`vector_fields`:** The fields that contain vector data for semantic search.
*   **`in_scope`:**  If `true`, the model will only use data from this source to answer the query. If `false`, the model might still use its general knowledge.
*   **`query_type`:**  Specifies how the query should be executed:
    *   **`simple`:**  Default, simple query parser.
    *   **`semantic`:** Semantic search, which attempts to understand the meaning of the query.
    *   **`vector`:** Vector search using embeddings.
    *   **`vectorSimpleHybrid`:** A combination of keyword and vector search.
    *   **`vectorSemanticHybrid`:** A combination of semantic and vector search.
*   **`semantic_configuration`:** The name of your semantic configuration in Azure Cognitive Search (if using semantic search).
*   **`embedding_dependency`:** Specifies how to vectorize the search query. For o1 models, you can set this to `deployment_name` which will use the Azure OpenAI embeddings model you specify.
*   **`authentication`:** Specifies how to authenticate with the search service. You can use:
    *   **`api_key`:** An API key for your Azure Cognitive Search service.
    *   **`system_assigned_managed_identity`:** System assigned managed identity
    *   **`user_assigned_managed_identity`:** User assigned managed identity
    *   **`access_token`:** Access token

**o1 Model Specifics with `data_sources`**

*   **`reasoning_effort`:** When using `data_sources`, the `reasoning_effort` parameter can influence how deeply the o1 model analyzes the retrieved data and integrates it into its response. Higher `reasoning_effort` might lead to more nuanced and contextually relevant answers.
*   **`max_completion_tokens`:** Remember that using data sources can increase the number of tokens used, especially if large amounts of data are retrieved. Adjust `max_completion_tokens` accordingly to avoid truncation.
*   **`developer` role:** For instructions related to data sources, you might use the `developer` role in your `messages` to tell the model how to use the retrieved information. For example:
    ```json
    {
        "role": "developer",
        "content": "Use the provided data sources to answer the user's question about company policy. If the answer is not found in the data sources, say you don't know."
    }
    ```

**Example Scenario:**

Let's say you have an Azure Cognitive Search index containing your company's internal documents. You want to build a chat application where employees can ask questions about company policies, and the o1 model will answer based on the indexed documents.

1. **Index your documents:** Ensure your documents are indexed in Azure Cognitive Search with appropriate fields (e.g., `content`, `title`, `filepath`).
2. **Deploy an o1 model:** Deploy an o1 model in your Azure OpenAI resource.
3. **Configure `data_sources`:** In your chat application's backend, when sending requests to the Azure OpenAI API, configure the `data_sources` parameter to point to your Azure Cognitive Search index, similar to the example above.
4. **Craft your prompt:** Use the `developer` role to instruct the model to use the data source to answer questions.
5. **Handle responses:** Your application should be able to process the responses from the API, which might now include citations referencing the documents in your search index.

**Other Data Sources:**

The process for configuring other data sources (`azure_cosmos_db`, `elasticsearch`, `mongo_db`, `pinecone`) is similar, but the specific parameters within the `parameters` object will vary. Refer to the OpenAPI specification section on each data source type for the exact parameters you need to provide.

**Key Takeaways:**

*   The `data_sources` parameter is a powerful way to enhance your o1 model's responses by grounding them in your data.
*   Properly configuring the `data_sources` parameter, especially `fields_mapping`, is essential for the model to correctly interpret the data from your sources.
*   Experiment with different `reasoning_effort` settings to optimize the balance between response quality and latency.
*   Make sure to handle potential errors when querying data sources.

By understanding and effectively using the `data_sources` feature, you can build more intelligent and helpful chat applications with Azure OpenAI's o1 models. Remember to consult the official Azure OpenAI documentation for the most up-to-date information and best practices.

---

### Summary of o1 Interactions

**Guide: Integrating a Chat Application with Azure OpenAI o1 Models for Document Interaction**

This guide explains how to integrate a chat application with Azure OpenAI, specifically using the o1 model series, to enable users to interact with and discuss uploaded documents.

**I. Introduction**

This guide focuses on leveraging the capabilities of Azure OpenAI's o1 models for building a chat application that can interact with user-uploaded documents. We will primarily utilize the `data_sources` parameter with the `file_search` tool for document retrieval and the `code_interpreter` for file manipulation, as detailed in the provided OpenAPI specification.

**II. Prerequisites**

1. **Azure OpenAI Resource:**
    *   Create an Azure OpenAI resource in your Azure subscription.
    *   Note your resource's endpoint (e.g., `https://your-resource-name.openai.azure.com`).

2. **o1 Model Deployment:**
    *   Deploy an o1 series model within your Azure OpenAI resource.
    *   Note the deployment ID.

3. **API Key or Bearer Token:**
    *   Obtain your API key from the Azure portal or set up Azure Active Directory authentication for a bearer token.

4. **Python Environment:**
    *   Python 3.7 or later.
    *   Install the `requests` library: `pip install requests`

**III. Methods for Document Interaction**

We will focus on two primary methods for enabling document interaction:

**A. Method 1: Using `file_search` with a Vector Store (Recommended)**

This method is best for scenarios where you want the model to search and retrieve information from documents to answer user queries.

**Steps:**

1. **Create a Vector Store:**
    *   Use the `/vector_stores` endpoint (POST request) to create a vector store. You can use `file_ids` at this stage, or add them later. You can also specify a `name` and `metadata` for the vector store.
    *   **Code Example:**

        ```python
        import requests
        import json

        vector_store_url = f"{ENDPOINT}/vector_stores?api-version={API_VERSION}"

        create_vector_store_data = {
          "name": "document-store"
        }
        
        response = requests.post(vector_store_url, headers=HEADERS, json=create_vector_store_data)
        response.raise_for_status()
        
        vector_store_id = response.json()['id']
        ```

2. **Upload Files:**
    *   Use the `/files` endpoint (POST request) to upload files.
    *   **Code Example:**

        ```python
        files_url = f"{ENDPOINT}/files?api-version={API_VERSION}"

        files = {
          "file": ("mydocument.pdf", open("mydocument.pdf", "rb"), "application/pdf"),
          "purpose": "file-search",
        }
        
        response = requests.post(files_url, headers=HEADERS, files=files)
        response.raise_for_status()

        file_id = response.json()['id']
        ```

3. **Attach Files to Vector Store:**
    *   You can create a file in the vector store using the `/vector_stores/{vector_store_id}/files` endpoint (POST).
    *   **Code Example:**
        ```python
        file_url = f"{ENDPOINT}/vector_stores/{vector_store_id}/files?api-version={API_VERSION}"
        file_data = {
            "file_id": file_id
        }
        
        response = requests.post(file_url, headers=HEADERS, json=file_data)
        response.raise_for_status()
        ```
    *   Alternatively, create a batch of files to add to the vector store using the `POST /vector_stores/{vector_store_id}/file_batches` endpoint.

4. **Configure `data_sources`, `tool_resources`, and `tools`:**
    *   In your chat completion request, set `data_sources` to use `file_search`, `tools` to indicate your assistant can use `file_search`, and `tool_resources` to make the vector store ID available to your assistant.

        ```python
        data = {
            "messages": [
                # ... your messages
            ],
            "data_sources": [
                {
                    "type": "file_search",
                    "parameters": {
                        "vector_store_id": vector_store_id
                    }
                }
            ],
            "tool_resources": {
                "file_search": {
                    "vector_store_ids": [
                         vector_store_id
                    ]
                }
            },
            "tools": [
              {
                "type": "file_search"
              }
            ],
            "reasoning_effort": "high",
            "max_completion_tokens": 512
        }
        ```

5. **Instruct the Model:**
    *   Use the `developer` or `system` role to tell the model to use `file_search`.
6. **Handle Tool Calls:**
    *   If the model wants to use `file_search`, it will include a `tool_calls` array in the response.
    *   Your application must detect this, perform the search using the vector store (implicitly handled by the Azure OpenAI service when you configured `data_sources` and `tools`), and send the search results back to the model in a subsequent turn.

**B. Method 2: Preprocessing and Embedding Files**

Use this method for more control over file processing or integration with existing search systems.

**Steps:**

1. **Preprocessing:**
    *   Extract text from files.
    *   Clean and format text.
    *   Chunk text into smaller sections.
2. **Embedding Generation:**
    *   Use an embedding model (e.g., `text-embedding-ada-002`) to generate embeddings for each chunk.
3. **Custom Storage:**
    *   Store embeddings and corresponding text in your own database.
4. **Query and Retrieve:**
    *   When a user asks a question, generate an embedding for the query.
    *   Search your database for relevant chunks based on embedding similarity.
5. **Context Injection:**
    *   Include the relevant text chunks in the `content` of `user` or `system` messages sent to the o1 model.

**C. Method 3: Using `code_interpreter`**
    * Upload files using the `/files` endpoint as described in Method 1, Step 2.
    * Add the `code_interpreter` tool to your assistant.
    * Set `tool_resources` to include the file IDs of the files you want to make available to the `code_interpreter`.

```python
"tools": [
    {
        "type": "code_interpreter"
    }
],
"tool_resources": {
    "code_interpreter": {
        "file_ids": [
            "file-..."
        ]
    }
}
```

* Provide instructions to your assistant in natural language on how to use the `code_interpreter` to process the files. For example, you could instruct the model to "Open the file 'data.csv' using the `code_interpreter` to summarize its contents."

**IV. Python Code Examples:**

**A. Non-Streaming Chat Completion with `file_search`:**

```python
import requests
import json

ENDPOINT = "https://your-resource-name.openai.azure.com/openai"  # Replace with your endpoint
API_KEY = "YOUR_API_KEY"  # Replace with your API key
DEPLOYMENT_ID = "YOUR_O1_MODEL_DEPLOYMENT_ID"  # Replace with your o1 model deployment ID
API_VERSION = "2024-12-01-preview"
VECTOR_STORE_ID = "YOUR_VECTOR_STORE_ID"  # Replace with your vector store ID

CHAT_COMPLETIONS_URL = f"{ENDPOINT}/deployments/{DEPLOYMENT_ID}/chat/completions?api-version={API_VERSION}"

HEADERS = {
    "Content-Type": "application/json",
    "api-key": API_KEY,
}

def generate_chat_completion(messages):
    data = {
        "messages": messages,
        "data_sources": [
            {
                "type": "file_search",
                "parameters": {
                    "vector_store_id": VECTOR_STORE_ID,
                },
            }
        ],
        "tool_resources": {
            "file_search": {
              "vector_store_ids": [
                VECTOR_STORE_ID
              ]
            }
          },
        "tools": [{"type": "file_search"}],
        "max_tokens": 800,
        "temperature": 0.7,
        "reasoning_effort": "medium",
        "max_completion_tokens": 500,
    }

    try:
        response = requests.post(CHAT_COMPLETIONS_URL, headers=HEADERS, json=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None

# Example Usage:
messages = [
    {
        "role": "developer",
        "content": "You are a helpful assistant. Use the file_search tool to answer questions based on the documents in the vector store.",
    },
    {
        "role": "user",
        "content": "What are the key features of this product?",
    },
]

response = generate_chat_completion(messages)

if response:
    print(json.dumps(response, indent=2))
    # You might need additional logic to handle tool calls and subsequent turns
    # if the model decides to use the file_search tool.
    if response["choices"][0]["finish_reason"] == "tool_calls":
        print("The model is requesting to use the file_search tool.")
```

**B. Streaming Chat Completion with `file_search`:**

```python
import requests
import json

# ... (ENDPOINT, API_KEY, DEPLOYMENT_ID, API_VERSION, VECTOR_STORE_ID, HEADERS are the same)
CHAT_COMPLETIONS_URL = f"{ENDPOINT}/deployments/{DEPLOYMENT_ID}/chat/completions?api-version={API_VERSION}"

def generate_chat_completion_stream(messages):
    data = {
        "messages": messages,
        "data_sources": [
            {
                "type": "file_search",
                "parameters": {
                    "vector_store_id": VECTOR_STORE_ID,
                },
            }
        ],
        "tool_resources": {
            "file_search": {
              "vector_store_ids": [
                VECTOR_STORE_ID
              ]
            }
          },
        "tools": [{"type": "file_search"}],
        "max_tokens": 800,
        "temperature": 0.7,
        "reasoning_effort": "high",
        "max_completion_tokens": 256,
        "stream": True,
    }

    try:
        response = requests.post(CHAT_COMPLETIONS_URL, headers=HEADERS, json=data, stream=True)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode("utf-8")
                if decoded_line.startswith("data:"):
                    chunk = decoded_line[6:]
                    if chunk.strip() == "[DONE]":
                        break
                    yield json.loads(chunk)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

# Example Usage:
messages = [
    {
        "role": "developer",
        "content": "You are a helpful assistant. Use the file_search tool to answer questions based on the documents in the vector store.",
    },
    {
        "role": "user",
        "content": "Tell me more about the company's history.",
    },
]

for chunk in generate_chat_completion_stream(messages):
    # print(f"Received chunk: {chunk}")
    if "choices" in chunk:
        for choice in chunk["choices"]:
            if "delta" in choice and "content" in choice["delta"]:
                print(choice["delta"]["content"], end="", flush=True)
    # You'll need to add logic to handle tool calls in the streaming scenario as well.
```

**V. Advanced Considerations:**

*   **Error Handling:** Implement robust error handling to catch network issues, API errors, and data source errors.
*   **Conversation State:** Manage the conversation history (`messages` array) effectively.
*   **Token Usage:** Monitor token usage to avoid unexpected costs.
*   **Security:** Secure your API keys and follow best practices for data security.
*   **Prompt Engineering:** Experiment with different prompts and instructions to optimize the model's responses and tool usage.
*   **Chunking Strategy:** If using `auto` mode for chunking, be aware that the default settings are `max_chunk_size_tokens` of `800` and `chunk_overlap_tokens` of `400`.
*   **Vector Store File Batches:** For adding multiple files to a vector store at once, use `POST /vector_stores/{vector_store_id}/file_batches`.
*   **Asynchronous Operations:** Consider using asynchronous requests for long-running operations like uploading large files or creating a vector store with many files.

**VI. Conclusion:**

The `data_sources` feature, particularly when combined with `file_search` tool, offers a powerful mechanism for grounding your o1 model's responses in your data. The `code_interpreter` tool can enable file operations, but is less suitable for discussion of file contents. By carefully configuring your data sources, using appropriate parameters like `reasoning_effort` and `max_completion_tokens`, and handling tool calls, you can create a sophisticated chat application that provides accurate and contextually relevant information based on your uploaded files. Remember to consult the official Azure OpenAI documentation for the most current information and best practices.
