import os
import json
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SimpleField,
    SearchableField,
    SearchIndex,
    SearchFieldDataType,
    SearchField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters
)
from azure.search.documents import SearchClient

load_dotenv()

AZURE_SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
AZURE_SEARCH_KEY = os.environ["AZURE_SEARCH_KEY"]
INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "markdown-index")
EMBEDDING_DIMENSIONS = 1536

def create_index():
    client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )

    index = SearchIndex(
        name=INDEX_NAME,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="path", type=SearchFieldDataType.String),
            SimpleField(name="last_accessed", type=SearchFieldDataType.Double),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                vector_search_dimensions=EMBEDDING_DIMENSIONS,
                vector_search_profile_name="defaultVectorProfile"
            )
        ],
        vector_search=VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(name="defaultHnsw")
            ],
            profiles=[
                VectorSearchProfile(
                    name="defaultVectorProfile",
                    algorithm_configuration_name="defaultHnsw",
                    vectorizer_name="defaultVectorizer"
                )
            ],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="defaultVectorizer",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=os.environ["AZURE_OPENAI_ENDPOINT"],
                        deployment_name=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
                        model_name="text-embedding-ada-002",
                        api_key=os.environ["AZURE_OPENAI_KEY"]
                    )
                )
            ]
        )
    )
    result = client.create_or_update_index(index)
    print(f"Index '{result.name}' created or updated successfully.")

def upload_documents(document_store="document_store.json"):
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY)
    )
    if not os.path.exists(document_store):
        print(f"Document store file '{document_store}' not found.")
        return
    with open(document_store, "r", encoding="utf-8") as f:
        documents = json.load(f)
    result = search_client.upload_documents(documents)
    print(f"Uploaded {len(documents)} documents. Result: {result}")

if __name__ == "__main__":
    create_index()
    upload_documents()
