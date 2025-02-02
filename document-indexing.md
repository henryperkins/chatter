Below is an example of how you can integrate an Azure AI Search–driven contextual layer into your existing Chatter project. In this approach, you’ll add modules to:

• Parse and index your markdown notes into Azure Cognitive Search
• Query those indexed notes to extract context for a user’s query
• Modify your chat message handling so that before—or even after—sending the conversation history to your Azure OpenAI chat model, you append or merge in excerpts extracted using the Azure Search resource

Because your project is already structured (see files such as app.py, context_manager.py, conversation_manager.py, etc.), you can add new modules and update your existing routes. The following sections outline the integration steps along with sample code.

---

## 1. Document Ingestion and Indexing

### a. Create a Markdown Processing Module

Create a new file called **doc_indexer.py** in your project root (or in a suitable directory). This script reads markdown files (for example, from a notes/ folder), generates embeddings using OpenAI’s embedding model, and outputs a JSON file for indexing.

```python
# doc_indexer.py

import os
import json
import time
from openai.embeddings_utils import get_embedding  # Replace or wrap with your preferred embedding call
from dotenv import load_dotenv

load_dotenv()

def preprocess_markdown(file_path):
    """Read a markdown file and extract its title, content, and metadata."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    title = os.path.basename(file_path)
    return {
        "id": file_path,  # Use file path as unique ID
        "title": title,
        "content": content,
        "path": file_path,
        "last_accessed": time.time()
    }

def generate_embedding(document, model="text-embedding-ada-002"):
    """Generate an embedding for the document content."""
    document["embedding"] = get_embedding(document["content"], model=model)
    return document

def process_markdown_directory(markdown_dir="notes", output_store="document_store.json"):
    documents = []
    for filename in os.listdir(markdown_dir):
        if filename.endswith(".md"):
            path = os.path.join(markdown_dir, filename)
            doc = preprocess_markdown(path)
            doc = generate_embedding(doc)
            documents.append(doc)
    with open(output_store, "w") as f:
        json.dump(documents, f, indent=2)
    print(f"Processed {len(documents)} documents.")

if __name__ == "__main__":
    process_markdown_directory()
```

Run this script (for example, by invoking `python doc_indexer.py`) to produce your JSON store.

### b. Create a Module for Azure Search Indexing

Create a new file called **azure_indexer.py**. This module creates an index with fields for your notes (including a vector field for embeddings) and then uploads the JSON documents to your index.

```python
# azure_indexer.py

import os
import json
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchableField, SearchFieldDataType,
    SearchField, VectorSearch, HnswAlgorithmConfiguration,
    VectorSearchProfile, AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters
)
from azure.search.documents import SearchClient
from dotenv import load_dotenv

load_dotenv()

AZURE_SEARCH_SERVICE_ENDPOINT = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
AZURE_SEARCH_ADMIN_KEY = os.environ["AZURE_SEARCH_ADMIN_KEY"]
INDEX_NAME = "markdown-index"
EMBEDDING_DIMENSIONS = 1536  # Adjust if your embedding model differs

def create_index():
    index_client = SearchIndexClient(
        endpoint=AZURE_SEARCH_SERVICE_ENDPOINT,
        credential=AZURE_SEARCH_ADMIN_KEY
    )
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="path", type=SearchFieldDataType.String),
        SimpleField(name="last_accessed", type=SearchFieldDataType.Double),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="myVectorProfile"
        )
    ]
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="myHnsw")
        ],
        profiles=[
            VectorSearchProfile(
                name="myVectorProfile",
                algorithm_configuration_name="myHnsw",
                vectorizer_name="myVectorizer"
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="myVectorizer",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=os.environ["AZURE_OPENAI_ENDPOINT"],
                    deployment_name=os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "embedding-deployment"),
                    model_name="text-embedding-ada-002",
                    api_key=os.environ["AZURE_OPENAI_KEY"]
                )
            )
        ]
    )

    index = SearchIndex(name=INDEX_NAME, fields=fields, vector_search=vector_search)
    result = index_client.create_or_update_index(index)
    print(f"Index {result.name} created")

def upload_documents(document_store="document_store.json"):
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_SERVICE_ENDPOINT,
        index_name=INDEX_NAME,
        credential=AZURE_SEARCH_ADMIN_KEY
    )
    with open(document_store, "r") as f:
        documents = json.load(f)
    result = search_client.upload_documents(documents)
    print(f"Uploaded {len(documents)} documents")

if __name__ == "__main__":
    create_index()
    upload_documents()
```

Run this script to create your index and push your documents.

---

## 2. Context Enrichment for Conversational Prompts

### a. Create a Context-Retrieval Module

Create a new module called **chat_context.py** that will query your Azure Search index when a user sends a message. It forms a context-enriched prompt by extracting relevant excerpts from your notes.

```python
# chat_context.py

import os
import time
from azure.search.documents import SearchClient
from dotenv import load_dotenv
from openai.embeddings_utils import get_embedding  # Use your same embedding function
import openai

load_dotenv()

AZURE_SEARCH_SERVICE_ENDPOINT = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
AZURE_SEARCH_ADMIN_KEY = os.environ["AZURE_SEARCH_ADMIN_KEY"]
INDEX_NAME = "markdown-index"

# Initialize Azure Search client
search_client = SearchClient(
    endpoint=AZURE_SEARCH_SERVICE_ENDPOINT,
    index_name=INDEX_NAME,
    credential=AZURE_SEARCH_ADMIN_KEY
)

def search_documents(query: str, top_k=3):
    """Query the index using vector search."""
    query_embedding = get_embedding(query, model="text-embedding-ada-002")
    vector_query = {
        "vector": query_embedding,
        "fields": "embedding",
        "kNearestNeighborsCount": 50
    }
    results = search_client.search(
        search_text=None,
        vector_queries=[vector_query],
        select=["id", "title", "content", "path", "last_accessed"],
        top=top_k
    )
    # Return a simple list of document dictionaries
    return [doc for doc in results]

def form_context_prompt(user_query: str, docs: list) -> str:
    """Assemble context from document excerpts along with the user’s query."""
    context_snippets = []
    for doc in docs:
        snippet = (
            f"Title: {doc['title']}\n"
            f"Path: {doc['path']}\n"
            f"Excerpt: {doc['content'][:150]}...\n"
            f"Last Accessed: {doc['last_accessed']}\n"
        )
        context_snippets.append(snippet)
    context = "\n---\n".join(context_snippets)
    prompt = f"""
The following excerpts are from my markdown notes:

{context}

Based on the above notes and my query: "{user_query}",
provide a detailed and context-aware answer.
"""
    return prompt

def get_stale_files(threshold_days=30, docs=None):
    """Return documents that haven't been accessed in at least threshold_days."""
    stale_files = []
    current_time = time.time()
    if docs:
        for doc in docs:
            if current_time - doc.get("last_accessed", current_time) > threshold_days * 86400:
                stale_files.append(doc)
    return stale_files

# Configure Azure OpenAI
openai.api_type = "azure"
openai.api_base = os.environ["AZURE_OPENAI_ENDPOINT"]
openai.api_version = "2023-09-01-preview"
openai.api_key = os.environ["AZURE_OPENAI_API_KEY"]
DEPLOYMENT_ID = os.environ.get("OPENAI_DEPLOYMENT_ID", "YOUR_CHAT_MODEL_DEPLOYMENT_ID")

def get_chat_response(prompt: str) -> str:
    """Send the enriched prompt to the chat model and return the response."""
    response = openai.ChatCompletion.create(
        model=DEPLOYMENT_ID,
        messages=[{"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

def chat_with_context(user_query: str) -> str:
    docs = search_documents(user_query, top_k=3)
    prompt = form_context_prompt(user_query, docs)
    response = get_chat_response(prompt)

    stale_files = get_stale_files(threshold_days=30, docs=docs)
    if stale_files:
        suggestion_text = "\nConsider reviewing these files, as you haven't seen them for a while:\n"
        for doc in stale_files:
            suggestion_text += f"- {doc['title']} (Path: {doc['path']}, Last Accessed: {time.ctime(doc['last_accessed'])})\n"
        response += suggestion_text
    return response

if __name__ == "__main__":
    # For ad-hoc testing:
    query = "How does the project architecture relate to the client modules?"
    print(chat_with_context(query))
```

### b. Wire Context into Conversation Flow

Open your **chat_routes.py** (or whichever module contains your chat message handler). Then import and call the new `chat_with_context` function when processing a user message. For example, in your `handle_chat()` route you might add:

```python
# Within chat_routes.py at the top:
from chat_context import chat_with_context

# Later inside your POST handler for "/chat/"
@chat_routes.route("/", methods=["POST"])
@login_required
def handle_chat():
    try:
        user_message = request.form.get("message", "").strip()
        if not user_message:
            return jsonify({"error": "Message is required."}), 400

        # Optionally log and pre-process the message as you already do
        # ...

        # Retrieve enriched context from your notes before calling the chat API.
        context_enriched_response = chat_with_context(user_message)

        # Record the user's message in conversation_manager as before
        conversation_manager.add_message(
            chat_id=session.get("chat_id"),
            role="user",
            content=user_message,
            # additional parameters...
        )

        # Instead of calling your Azure chat endpoint directly with just conversation history,
        # return the enriched response from our new function.
        return jsonify({"message": {"role": "assistant", "content": context_enriched_response}})

    except Exception as e:
        logger.error("Error during chat handling: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500
```

This change makes your chat endpoint use contextual excerpts from your markdown notes to help generate better responses.

---

## 3. Update Your Project’s Configuration and Deployment

1. **Update your requirements.txt**
   Add any needed packages such as:
   • azure-search-documents
   • python-dotenv
   • openai

2. **Configure Environment Variables**
   In your project's .env file, add variables for your Azure resources:

   ```
   AZURE_SEARCH_SERVICE_ENDPOINT=https://<your-search-service>.search.windows.net
   AZURE_SEARCH_ADMIN_KEY=your-search-admin-key
   AZURE_OPENAI_ENDPOINT=https://<your-openai-resource>.openai.azure.com
   AZURE_OPENAI_API_KEY=your-openai-api-key
   OPENAI_DEPLOYMENT_ID=your-chat-model-deployment-id
   AZURE_OPENAI_EMBEDDING_DEPLOYMENT=your-embedding-deployment
   ```

3. **Test and Monitor**
   Run your application (using your current app.py, which already wires up blueprints such as chat_routes) and test that the enriched responses are returned correctly. Monitor your logs for any errors related to Azure Search queries or context construction.

---

## 4. Summary and Next Steps

- **Document Processing and Indexing:**
  You now have a separate module (**doc_indexer.py**) to parse markdown files and generate embeddings, plus another module (**azure_indexer.py**) to create and populate an Azure Search index.

- **Context Retrieval:**
  The **chat_context.py** module queries the indexed documents and builds an enriched prompt for the chat model, including suggestions for rarely accessed files.

- **Conversation Integration:**
  Your updated chat route (in **chat_routes.py**) now calls `chat_with_context` to merge user messages with contextual excerpts before sending a prompt to Azure OpenAI’s chat model.

- **Project Cohesion:**
  Since your project’s main application (app.py) and supporting modules like context_manager.py, conversation_manager.py, and database.py are already in place, simply add these new modules and update your routes accordingly.

By following these steps, you integrate an Azure AI Search resource that allows your Chatter project to “read” and reference your markdown notes, making responses more context-aware and helping to keep your stored knowledge relevant. Feel free to adjust token limits, search parameters, and context strategies according to your needs.

Happy coding!
