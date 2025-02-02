Below is an example of how you can extend your existing Chatter project (available at https://github.com/henryperkins/chatter.git) by integrating an Azure AI Search resource to “read” your markdown notes and provide context when answering messages. In this example you will:

• Build a document ingestion module that parses markdown files, generates embeddings, and indexes them into an Azure Cognitive Search index.
• Create helper functions for querying the Azure Search index and form a context‐enriched prompt.
• Update your chat route (e.g. in chat_routes.py) so that before sending a prompt to your Azure OpenAI chat model, you first retrieve related excerpts from your indexed notes.
• Optionally, use metadata (like last accessed timestamps) to recommend files that you haven’t recently visited.

The following sections detail an integration plan and sample code. You can then adapt these code samples into your repository’s structure and wire them into your existing routes.

---

## 1. Create a Document Ingestion Module

Create a new file (for example, `doc_indexer.py`) that preprocesses markdown files, generates embeddings (using your OpenAI embedding endpoint), and creates a JSON store that you can later upload to Azure Search.

```python
# doc_indexer.py
import os
import json
import time
from openai.embeddings_utils import get_embedding  # Replace with your embedding call
from dotenv import load_dotenv

load_dotenv()

def preprocess_markdown(file_path):
    """Read a markdown file and extract its title, content, and metadata."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    title = os.path.basename(file_path)
    return {
        "id": file_path,  # use the file path as a unique ID in the index
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

Run this script after adding your markdown files to the `notes` folder (or your chosen folder):

```bash
python doc_indexer.py
```

---

## 2. Create the Azure Cognitive Search Index and Upload Documents

Create a new module (e.g. `azure_indexer.py`) that defines your index schema and uploads your JSON documents into Azure Search. This example uses the Azure Search Python SDK.

```python
# azure_indexer.py
import os
import json
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchableField, SearchFieldDataType,
    SearchField, VectorSearch,
    HnswAlgorithmConfiguration, VectorSearchProfile,
    AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters
)
from azure.search.documents import SearchClient
from dotenv import load_dotenv

load_dotenv()

AZURE_SEARCH_SERVICE_ENDPOINT = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
AZURE_SEARCH_ADMIN_KEY = os.environ["AZURE_SEARCH_ADMIN_KEY"]
INDEX_NAME = "markdown-index"
EMBEDDING_DIMENSIONS = 1536  # Adjust to match your embedding model

def create_index():
    index_client = SearchIndexClient(endpoint=AZURE_SEARCH_SERVICE_ENDPOINT,
                                     credential=AZURE_SEARCH_ADMIN_KEY)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="path", type=SearchFieldDataType.String),
        SimpleField(name="last_accessed", type=SearchFieldDataType.Double),
        SearchField(name="embedding",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    vector_search_dimensions=EMBEDDING_DIMENSIONS,
                    vector_search_profile_name="myVectorProfile")
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="myHnsw")],
        profiles=[VectorSearchProfile(
            name="myVectorProfile",
            algorithm_configuration_name="myHnsw",
            vectorizer_name="myVectorizer"
        )],
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
    search_client = SearchClient(endpoint=AZURE_SEARCH_SERVICE_ENDPOINT,
                                 index_name=INDEX_NAME,
                                 credential=AZURE_SEARCH_ADMIN_KEY)
    with open(document_store, "r") as f:
        documents = json.load(f)
    result = search_client.upload_documents(documents)
    print(f"Uploaded {len(documents)} documents")

if __name__ == "__main__":
    create_index()
    upload_documents()
```

Run this module to create the index and upload your processed documents:

```bash
python azure_indexer.py
```

---

## 3. Add a Context-Retrieval Module for Your Chatbot

Next, create a module (e.g. `chat_context.py`) that provides functions to query Azure Search using a vector search and assemble a context-enriched prompt from your markdown notes. You can then call this function from your chat route.

```python
# chat_context.py
import os
import time
from azure.search.documents import SearchClient
from dotenv import load_dotenv
from openai.embeddings_utils import get_embedding  # Use your embedding function
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
    """Search the index for documents relevant to the query."""
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
    return [doc for doc in results]

def form_context_prompt(user_query: str, docs: list) -> str:
    """Form a context-aware prompt by concatenating document excerpts."""
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

Based on these notes and my query: "{user_query}",
provide a detailed and context-aware answer.
"""
    return prompt

def get_stale_files(threshold_days=30, docs=None):
    """Return documents that haven’t been accessed in threshold_days."""
    stale_files = []
    current_time = time.time()
    if docs:
        for doc in docs:
            if current_time - doc.get("last_accessed", current_time) > threshold_days * 86400:
                stale_files.append(doc)
    return stale_files

# Configure Azure OpenAI parameters (adjust as needed)
openai.api_type = "azure"
openai.api_base = os.environ["AZURE_OPENAI_ENDPOINT"]
openai.api_version = "2023-09-01-preview"
openai.api_key = os.environ["AZURE_OPENAI_API_KEY"]
DEPLOYMENT_ID = os.environ.get("OPENAI_DEPLOYMENT_ID", "YOUR_CHAT_MODEL_DEPLOYMENT_ID")

def get_chat_response(prompt: str) -> str:
    """Send the context-aware prompt to the chat model and return the answer."""
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
        suggestion_text = "\nConsider reviewing the following files, as you haven't seen them recently:\n"
        for doc in stale_files:
            suggestion_text += f"- {doc['title']} (Path: {doc['path']}, Last Accessed: {time.ctime(doc['last_accessed'])})\n"
        response += suggestion_text
    return response

if __name__ == "__main__":
    # For testing purposes
    query = "How does the project architecture relate to the client modules?"
    print(chat_with_context(query))
```

---

## 4. Integrate the Context Functions into Your Chat Routes

Locate your chat message handler in your `chat_routes.py` file. You’ll modify it so that before calling the Azure OpenAI chat model, it calls your new context-retrieval functions from `chat_context.py`.

For example, in your `handle_chat()` route (cut for brevity), you can add:

```python
# Import the context functions at the top of chat_routes.py
from chat_context import chat_with_context

@chat_routes.route("/", methods=["POST"])
@login_required
def handle_chat():
    try:
        # (Existing code to validate and process the incoming message...)
        user_message = request.form.get("message", "").strip()
        if not user_message:
            return jsonify({"error": "Message is required."}), 400

        # -------------------------------
        # NEW: Retrieve additional context
        # -------------------------------
        # Call our context-enhancing function which searches your markdown notes
        context_enriched_response = chat_with_context(user_message)

        # You could also merge this with your conversation history if desired.
        # For example, by prepending this context to the conversation history.

        # Save user message and add context to the conversation (if required)
        conversation_manager.add_message(
            chat_id=session.get("chat_id"),
            role="user",
            content=user_message,
            # ... any additional parameters
        )

        # Instead of calling get_azure_response directly with only conversation history,
        # use the context_enriched_response as the final answer.
        # (Option 1) Send the response directly:
        return jsonify({"message": {"role": "assistant", "content": context_enriched_response }})

    except Exception as e:
        # (Error handling as already present)
        return jsonify({"error": str(e)}), 500
```

In this code, when a user sends a chat message, your system will use the query to search your Azure Search index (populated with your markdown note data), form a richer prompt, and then get a response from your Azure OpenAI chat model.

---

## 5. Final Steps

1. **Add New Dependencies:**
   Update your `requirements.txt` (or equivalent) to include packages such as `azure-search-documents`, `python-dotenv`, and `openai`.

2. **Configure Environment Variables:**
   In your `.env` file, include variables such as:
   - `AZURE_SEARCH_SERVICE_ENDPOINT`
   - `AZURE_SEARCH_ADMIN_KEY`
   - `AZURE_OPENAI_ENDPOINT`
   - `AZURE_OPENAI_API_KEY`
   - `OPENAI_DEPLOYMENT_ID`
   - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` (if applicable)

3. **Test All Components:**
   Make sure to test your indexing pipeline, search queries, and overall chat response to verify that your chatbot now “reads” your markdown files and uses them as contextual information.

4. **Deploy and Monitor:**
   Once integrated and tested locally, deploy your updated Chatter project. Monitor logging to be sure the Azure Search queries and subsequent chat responses are working as expected.

---

## Summary

With these changes, your Chatter project now uses an Azure Cognitive Search resource to search through indexed markdown files. This lets the chatbot enrich its responses by referencing your own notes and suggesting less-visited files. You have:

- A document ingestion pipeline (doc_indexer.py)
- An index creation and upload module (azure_indexer.py)
- A context retrieval module (chat_context.py)
- Modified chat routes in chat_routes.py that use the retrieved context before calling the chat model

Integrate these modules into your project as shown, and you’ll have a more context-aware and note–integrated chatbot environment.

Feel free to adjust specific model parameters and error handling to match your production needs. Happy coding!
