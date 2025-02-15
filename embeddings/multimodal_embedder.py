"""Multi-modal embedding generation for text and media content."""

import os
from typing import Dict, List, Optional, Union, Any
import numpy as np
from openai import AzureOpenAI
from PIL import Image
import io
import base64
from logging_config import get_logger

logger = get_logger(__name__)

# Retrieve your Azure deployment names from environment variables,
# or provide defaults as needed.
TEXT_EMBEDDING_DEPLOYMENT = os.getenv("TEXT_EMBEDDING_DEPLOYMENT", "text-embedding-deployment")
VISION_EMBEDDING_DEPLOYMENT = os.getenv("VISION_EMBEDDING_DEPLOYMENT", "vision-embedding-deployment")

class MultiModalEmbedder:
    """Generates and manages embeddings for text and media content."""

    def __init__(self):
        """Initialize the embedder with Azure OpenAI client."""
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            # Use a valid Azure OpenAI API version that supports embeddings:
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        # Cache for embeddings
        self.embedding_cache: Dict[str, np.ndarray] = {}

    async def generate_text_embedding(self, text: str) -> np.ndarray:
        """Generate embeddings for text content."""
        try:
            # Use your Azure deployment name instead of the base model name:
            response = await self.client.embeddings.create(
                model=TEXT_EMBEDDING_DEPLOYMENT,  
                input=text
            )
            return np.array(response.data[0].embedding)
        except Exception as e:
            logger.error(f"Text embedding generation failed: {str(e)}")
            raise

    async def generate_image_embedding(self, image_data: Union[str, bytes]) -> np.ndarray:
        """Generate embeddings for image content."""
        try:
            # Convert image data to base64 if needed
            if isinstance(image_data, bytes):
                image_b64 = base64.b64encode(image_data).decode('utf-8')
            else:
                image_b64 = image_data

            # This assumes your vision-embedding-deployment can accept image data in the format shown
            # If you have a different approach, adjust accordingly
            response = await self.client.embeddings.create(
                model=VISION_EMBEDDING_DEPLOYMENT,
                input=[{
                    "type": "image",
                    "image": image_b64
                }]
            )
            return np.array(response.data[0].embedding)
        except Exception as e:
            logger.error(f"Image embedding generation failed: {str(e)}")
            raise

    def combine_embeddings(
        self,
        text_embedding: Optional[np.ndarray] = None,
        image_embedding: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """Combine text and image embeddings if both are present."""
        if text_embedding is not None and image_embedding is not None:
            # Normalize and then concatenate
            text_norm = text_embedding / np.linalg.norm(text_embedding)
            image_norm = image_embedding / np.linalg.norm(image_embedding)
            return np.concatenate([text_norm, image_norm])
        elif text_embedding is not None:
            return text_embedding
        elif image_embedding is not None:
            return image_embedding
        else:
            raise ValueError("At least one embedding type (text or image) is required")

    def get_embeddings_sync(
        self,
        text: Optional[str] = None,
        image: Optional[Union[str, bytes]] = None
    ) -> Dict[str, Any]:
        """Synchronous version of get_embeddings for text/image content."""
        embeddings = {}

        if text:
            cache_key = f"text:{hash(text)}"
            if cache_key in self.embedding_cache:
                embeddings["text"] = self.embedding_cache[cache_key]
            else:
                resp = self.client.embeddings.create(
                    model=TEXT_EMBEDDING_DEPLOYMENT,
                    input=text
                )
                embeddings["text"] = np.array(resp.data[0].embedding)
                self.embedding_cache[cache_key] = embeddings["text"]

        if image:
            cache_key = f"image:{hash(str(image))}"
            if cache_key in self.embedding_cache:
                embeddings["image"] = self.embedding_cache[cache_key]
            else:
                if isinstance(image, bytes):
                    image_b64 = base64.b64encode(image).decode('utf-8')
                else:
                    image_b64 = image
                resp = self.client.embeddings.create(
                    model=VISION_EMBEDDING_DEPLOYMENT,
                    input=[{
                        "type": "image",
                        "image": image_b64
                    }]
                )
                embeddings["image"] = np.array(resp.data[0].embedding)
                self.embedding_cache[cache_key] = embeddings["image"]

        if "text" in embeddings or "image" in embeddings:
            embeddings["combined"] = self.combine_embeddings(
                embeddings.get("text"),
                embeddings.get("image")
            )

        return embeddings

    async def get_embeddings(
        self,
        text: Optional[str] = None,
        image: Optional[Union[str, bytes]] = None
    ) -> Dict[str, Any]:
        """Get embeddings for text and/or image content (async version)."""
        embeddings = {}

        if text:
            cache_key = f"text:{hash(text)}"
            if cache_key in self.embedding_cache:
                embeddings["text"] = self.embedding_cache[cache_key]
            else:
                embeddings["text"] = await self.generate_text_embedding(text)
                self.embedding_cache[cache_key] = embeddings["text"]

        if image:
            cache_key = f"image:{hash(str(image))}"
            if cache_key in self.embedding_cache:
                embeddings["image"] = self.embedding_cache[cache_key]
            else:
                embeddings["image"] = await self.generate_image_embedding(image)
                self.embedding_cache[cache_key] = embeddings["image"]

        if "text" in embeddings or "image" in embeddings:
            embeddings["combined"] = self.combine_embeddings(
                embeddings.get("text"),
                embeddings.get("image")
            )

        return embeddings
