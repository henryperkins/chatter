import os
from openai import AzureOpenAI

# Get configuration from environment
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# Test the deployment
try:
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10
    )
    print("Success! Deployment is working.")
    print(f"Response: {response}")
except Exception as e:
    print(f"Error: {str(e)}")
