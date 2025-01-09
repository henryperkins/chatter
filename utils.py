import requests
from werkzeug.utils import secure_filename as werkzeug_secure_filename

def count_tokens(text: str, model_name: str) -> int:
    """
    Count the number of tokens in a given text for a specific model.
    This is a placeholder function. Replace with actual token counting logic.
    """
    return len(text.split())

def secure_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it is safe for storage.
    """
    return werkzeug_secure_filename(filename)

def get_azure_response(messages, deployment_name, max_completion_tokens, api_endpoint, api_key, api_version, requires_o1_handling, timeout_seconds=30):
    """
    Send a request to the Azure OpenAI API and return the response.

    Args:
        messages: List of messages for the chat context.
        deployment_name: The deployment name of the Azure OpenAI model.
        max_completion_tokens: Maximum tokens for the response.
        api_endpoint: The API endpoint for Azure OpenAI.
        api_key: The API key for authentication.
        api_version: The API version to use.
        requires_o1_handling: Whether the model requires special handling.
        timeout_seconds: Timeout for the API request.

    Returns:
        The response from the Azure OpenAI API.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "messages": messages,
        "max_tokens": max_completion_tokens,
        "temperature": 0.7,
        "top_p": 0.95,
        "frequency_penalty": 0,
        "presence_penalty": 0,
    }
    try:
        response = requests.post(
            f"{api_endpoint}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}",
            json=payload,
            headers=headers,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error communicating with Azure OpenAI: {e}")
