import os
import json
import time
import base64
from typing import List, Dict, Any, Optional
from openai import AzureOpenAI
from dotenv import load_dotenv
from azure_file_manager import AzureOpenAIFileManager

load_dotenv()

class DocumentProcessor:
    """Handles document processing and indexing with vector store support"""

    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
        )

        # Initialize file manager if vector store is enabled
        self.use_vector_store = os.getenv("USE_VECTOR_STORE", "false").lower() == "true"
        self.file_manager = None
        if self.use_vector_store:
            self.file_manager = AzureOpenAIFileManager(
                endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                api_key=os.environ["AZURE_OPENAI_KEY"]
            )

    def get_embedding(self, text: str, model: str = "text-embedding-ada-002") -> List[float]:
        """Generate an embedding using Azure OpenAI's API."""
        response = self.client.embeddings.create(
            model=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            input=text
        )
        return response.data[0].embedding

    @staticmethod
    def encode_key(key: str) -> str:
        """Encode a key to be safe for Azure Search."""
        return base64.urlsafe_b64encode(key.encode()).decode().rstrip('=')

    def preprocess_markdown(self, file_path: str) -> Dict[str, Any]:
        """
        Read a markdown file, extract its title and content, and record metadata.
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        title = os.path.basename(file_path)
        safe_id = self.encode_key(file_path)

        return {
            "id": safe_id,
            "title": title,
            "content": content,
            "filepath": file_path,  # Changed from path to filepath for consistency
            "url": f"file://{os.path.abspath(file_path)}",  # Added URL field
            "last_accessed": time.time()
        }

    def generate_embedding(self, document: Dict[str, Any], model: str = "text-embedding-ada-002") -> Dict[str, Any]:
        """
        Generate an embedding for the document content using Azure OpenAI's embedding model.
        """
        document["contentvector"] = self.get_embedding(document["content"], model=model)  # Changed from embedding to contentvector
        return document

    def create_or_update_vector_store(self, documents: List[Dict[str, Any]], store_name: str) -> Optional[str]:
        """
        Create or update a vector store with the provided documents.

        Args:
            documents: List of processed documents
            store_name: Name for the vector store

        Returns:
            Vector store ID if successful, None otherwise
        """
        if not self.use_vector_store or not self.file_manager:
            return None

        try:
            # Create vector store
            result = self.file_manager.create_vector_store(
                name=store_name,
                file_ids=[doc["id"] for doc in documents],
                chunking_strategy={
                    "type": "static",
                    "static": {
                        "max_chunk_size_tokens": 1000,
                        "chunk_overlap_tokens": 100
                    }
                }
            )

            vector_store_id = result.get("id")
            if not vector_store_id:
                raise ValueError("Failed to get vector store ID from response")

            # Wait for vector store to be ready
            if not self.file_manager.wait_for_vector_store_ready(vector_store_id):
                raise TimeoutError("Vector store processing timed out")

            return vector_store_id

        except Exception as e:
            logger.error(f"Error creating vector store: {str(e)}")
            return None

    def process_markdown_directory(
        self,
        markdown_dir: str = "notes",
        output_store: str = "document_store.json",
        vector_store_name: Optional[str] = None
    ) -> None:
        """
        Process all markdown files in the specified directory and store the processed documents.

        Args:
            markdown_dir: Directory containing markdown files
            output_store: Path to output JSON file for traditional storage
            vector_store_name: Optional name for vector store (if enabled)
        """
        if not os.path.exists(markdown_dir):
            print(f"Directory {markdown_dir} does not exist. Creating it...")
            os.makedirs(markdown_dir, exist_ok=True)

        documents = []
        for filename in os.listdir(markdown_dir):
            if filename.endswith(".md"):
                file_path = os.path.join(markdown_dir, filename)
                doc = self.preprocess_markdown(file_path)
                doc = self.generate_embedding(doc)
                documents.append(doc)

        # Save to traditional document store
        with open(output_store, "w", encoding="utf-8") as out_file:
            json.dump(documents, out_file, indent=2)
        print(f"Processed {len(documents)} markdown documents. JSON file written to {output_store}.")

        # Create vector store if enabled
        if self.use_vector_store and vector_store_name:
            vector_store_id = self.create_or_update_vector_store(
                documents=documents,
                store_name=vector_store_name
            )
            if vector_store_id:
                print(f"Vector store created with ID: {vector_store_id}")
            else:
                print("Failed to create vector store")

if __name__ == "__main__":
    processor = DocumentProcessor()
    processor.process_markdown_directory(
        vector_store_name=os.getenv("VECTOR_STORE_NAME", "markdown-store")
    )
