import os
import json
import time
import base64
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

def get_embedding(text, model="text-embedding-ada-002"):
    """Generate an embedding using Azure OpenAI's API."""
    client = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
    )

    response = client.embeddings.create(
        model=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
        input=text
    )
    return response.data[0].embedding

def encode_key(key):
    """Encode a key to be safe for Azure Search."""
    return base64.urlsafe_b64encode(key.encode()).decode().rstrip('=')

def preprocess_markdown(file_path):
    """
    Read a markdown file, extract its title and content, and record metadata.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    title = os.path.basename(file_path)
    safe_id = encode_key(file_path)
    return {
        "id": safe_id,
        "title": title,
        "content": content,
        "path": file_path,
        "last_accessed": time.time()
    }

def generate_embedding(document, model="text-embedding-ada-002"):
    """
    Generate an embedding for the document content using Azure OpenAI's embedding model.
    """
    document["embedding"] = get_embedding(document["content"], model=model)
    return document

def process_markdown_directory(markdown_dir="notes", output_store="document_store.json"):
    """
    Process all markdown files in the specified directory and store the processed documents as JSON.
    """
    documents = []
    if not os.path.exists(markdown_dir):
        print(f"Directory {markdown_dir} does not exist. Creating it...")
        os.makedirs(markdown_dir, exist_ok=True)
    for filename in os.listdir(markdown_dir):
        if filename.endswith(".md"):
            file_path = os.path.join(markdown_dir, filename)
            doc = preprocess_markdown(file_path)
            doc = generate_embedding(doc)
            documents.append(doc)
    with open(output_store, "w", encoding="utf-8") as out_file:
        json.dump(documents, out_file, indent=2)
    print(f"Processed {len(documents)} markdown documents. JSON file written to {output_store}.")

if __name__ == "__main__":
    process_markdown_directory()
