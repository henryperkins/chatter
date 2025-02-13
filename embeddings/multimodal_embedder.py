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

class MultiModalEmbedder:
    """Generates and manages embeddings for text and media content."""
    
    def __init__(self):
        """Initialize the embedder with Azure OpenAI client."""
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        
        # Cache for embeddings
        self.embedding_cache: Dict[str, np.ndarray] = {}
        
    async def generate_text_embedding(self, text: str) -> np.ndarray:
        """Generate embeddings for text content."""
        try:
            response = await self.client.embeddings.create(
                model="text-embedding-ada-002",  # or your Azure deployment name
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
                
            # Use CLIP-like model for image embeddings
            response = await self.client.embeddings.create(
                model="vision-embedding-model",  # your Azure deployment name
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
        """Combine text and image embeddings if both present."""
        if text_embedding is not None and image_embedding is not None:
            # Normalize and concatenate
            text_norm = text_embedding / np.linalg.norm(text_embedding)
            image_norm = image_embedding / np.linalg.norm(image_embedding)
            return np.concatenate([text_norm, image_norm])
        elif text_embedding is not None:
            return text_embedding
        elif image_embedding is not None:
            return image_embedding
        else:
            raise ValueError("At least one embedding type required")

    async def get_embeddings(
        self,
        text: Optional[str] = None,
        image: Optional[Union[str, bytes]] = None
    ) -> Dict[str, Any]:
        """Get embeddings for text and/or image content."""
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
