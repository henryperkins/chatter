import logging
from typing import Optional, List, Dict, Union, Generator, Any
from openai import OpenAIError
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from utils.config import Config
from services.database.models import Model

# Type aliases for better readability
ResponseType = Union[str, Generator[ChatCompletionChunk, None, None]]
ApiParams = Dict[str, Any]

logger = logging.getLogger(__name__)


def get_azure_response(
    messages: List[Dict[str, str]],
    deployment_name: Optional[str] = None,
    selected_model_id: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    api_endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: Optional[str] = None,
    requires_o1_handling: bool = False,
    stream: bool = False,
    timeout_seconds: int = 600,  # Increased timeout to 10 minutes
) -> ResponseType:
    """
    Sends a chat message to the Azure OpenAI API and returns the response.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys.
        deployment_name: The name of the deployment (model) to use.
        selected_model_id: The ID of the selected model (optional).
        max_completion_tokens: The maximum number of completion tokens to generate.
        api_endpoint: The Azure OpenAI endpoint URL (optional).
        api_key: The Azure OpenAI API key (optional).
        api_version: The Azure OpenAI API version (optional).
        requires_o1_handling: Whether to use o1-preview specific handling.
        stream: Whether to return a streaming response.
        timeout_seconds: Request timeout in seconds.

    Returns:
        The response from the Azure OpenAI API.

    Raises:
        ValueError: If the selected model is not found.
        OpenAIError: If there is an error during API communication.
    """
    try:
        # Initialize defaults with proper types
        api_params: Dict[str, Any] = {
            "messages": [],  # Will be populated based on model type
            "stream": stream and not requires_o1_handling,  # Enable streaming if requested and supported
        }

        # Create model config from provided credentials or get from database
        model_config = {}
        if selected_model_id:
            model = Model.get_by_id(selected_model_id)
            if not model:
                raise ValueError("Selected model not found.")
            model_config = model.__dict__

        # Override with any provided credentials
        if api_endpoint:
            model_config["api_endpoint"] = api_endpoint
        if api_key:
            model_config["api_key"] = api_key
        if api_version:
            model_config["api_version"] = api_version
        if deployment_name:
            model_config["deployment_name"] = deployment_name
        model_config["requires_o1_handling"] = requires_o1_handling

        # Initialize client from model config
        from utils.config.azure import initialize_client_from_model
        (
            client,
            deployment_name,
            temperature,
            max_tokens,
            max_completion_tokens,
            requires_o1_handling,
        ) = initialize_client_from_model(
            model_config,
            timeout_seconds=timeout_seconds,
        )

        # Update api_params with model/deployment info
        api_params["model"] = deployment_name
        if max_completion_tokens:
            api_params["max_completion_tokens"] = max_completion_tokens

        # Filter messages based on model requirements
        api_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if not requires_o1_handling or msg["role"] != "system"
        ]
        api_params["messages"] = api_messages

        # Set parameters based on model type
        if requires_o1_handling:
            # Required parameters for o1-preview
            api_params.update(
                {
                    "temperature": 1,  # Must be 1 for o1-preview
                    "max_completion_tokens": max_completion_tokens or Config.DEFAULT_MAX_COMPLETION_TOKENS,
                    "stream": False,  # Streaming not supported
                }
            )
            # Remove 'max_tokens' if present
            api_params.pop("max_tokens", None)
        else:
            # Parameters for other models
            if temperature is not None:
                api_params["temperature"] = temperature
            if max_tokens is not None:
                api_params["max_tokens"] = max_tokens
            # Remove 'max_completion_tokens' if present
            api_params.pop("max_completion_tokens", None)

        # Log the final API parameters for debugging
        logger.debug("Final API parameters: %s", api_params)
        logger.debug("Sending request to Azure OpenAI with parameters: %s", api_params)

        # Make the API call
        response = client.chat.completions.create(**api_params)

        # Handle streaming response
        if stream and not requires_o1_handling:
            logger.debug("Returning streaming response")
            return response

        # Handle non-streaming response
        logger.debug("Raw API response: %s", response.model_dump_json())

        # Extract model response with enhanced error checking
        if not response.choices:
            logger.error("No choices in model response")
            raise ValueError("Model response contained no choices")

        if not response.choices[0].message:
            logger.error("No message in first choice")
            raise ValueError("Model response choice contained no message")

        model_response = response.choices[0].message.content
        if not model_response:
            logger.error("Empty content in model response")
            raise ValueError("Model returned empty response content")

        # Log successful response
        logger.info(
            "Response received from the model (length: %d): %s",
            len(model_response),
            model_response[:100] + "..." if len(model_response) > 100 else model_response,
        )
        return model_response

    except OpenAIError as e:
        logger.exception(
            "OpenAI API error with %s model: %s",
            "o1-preview" if requires_o1_handling else "standard",
            str(e)
        )
        safe_api_params = {k: v for k, v in api_params.items() if k != 'api_key'}
        logger.debug("API parameters at the time of error: %s", safe_api_params)
        raise
    except Exception as e:
        logger.exception(
            "Error in get_azure_response (%s model): %s",
            "o1-preview" if requires_o1_handling else "standard",
            str(e)
        )
        safe_api_params = {k: v for k, v in api_params.items() if k != 'api_key'}
        logger.debug("API parameters at the time of error: %s", safe_api_params)
        raise