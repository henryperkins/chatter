import os
from dotenv import load_dotenv
from openai import AzureOpenAI


def initialize_azure_client():
    """Initialize and return the Azure OpenAI client using environment variables."""
    # Load environment variables
    load_dotenv()
    
    # Get Azure configuration from environment
    azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    api_key = os.getenv('AZURE_OPENAI_KEY')
    api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview')
    deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')

    # Validate required environment variables
    if not all([azure_endpoint, api_key, api_version, deployment_name]):
        raise ValueError(
            "Missing required Azure OpenAI environment variables. "
            "Please check your .env file."
        )

    # Validate endpoint is a non-empty string
    if not azure_endpoint or not isinstance(azure_endpoint, str):
        raise ValueError("Azure endpoint must be a non-empty string")
        
    # Initialize and return the client
    client = AzureOpenAI(
        azure_endpoint=azure_endpoint,
        api_key=api_key,
        api_version=api_version
    )
    return client, deployment_name

def initialize_client_from_model(model_config):
    """Initialize and return the client using model configuration."""
    if not model_config:
        raise ValueError("Model configuration is required")
        
    if model_config["model_type"] != "azure":
        raise ValueError(f"Unsupported model type: {model_config['model_type']}")
        
    # Validate required configuration
    if not all([model_config["api_endpoint"], model_config["api_key"]]):
        raise ValueError("Model configuration is missing required fields")
        
    # Initialize and return the client
    client = AzureOpenAI(
        azure_endpoint=model_config["api_endpoint"],
        api_key=model_config["api_key"],
        api_version="2024-12-01-preview"
    )
    return client, model_config["name"]


def create_completion(client, deployment_name, messages):
    """Create a completion using the Azure OpenAI API."""
    try:
        response = client.chat.completions.create(
            model=deployment_name,
            messages=messages,
            temperature=1,
            max_completion_tokens=32000,
            response_format={"type": "text"}
        )
        return response
    except Exception as e:
        raise RuntimeError(f"Failed to create completion: {str(e)}")