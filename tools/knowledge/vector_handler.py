"""
Vector Handler Tool

Handles text chunking and vector embedding generation using Google Gemini.
"""

import logging
import os
from typing import List, Dict, Any
from google import genai
from google.genai import types
from tools.resilience.retry_handler import with_retry, RetryConfig

logger = logging.getLogger(__name__)

class VectorHandler:
    """
    Handles vector operations: chunking and embedding generation.
    """
    
    def __init__(self):
        self.client = None
        self.project_id = None
        self.location = 'us-central1'
        self.embedding_model = "text-embedding-004"

    def _initialize_client(self):
        """Lazy initialization of the client."""
        if self.client:
            return

        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        # RAG/embeddings need regional endpoint (us-west1 for RAG corpus)
        self.location = os.getenv('VERTEX_AI_LOCATION', 'us-west1')
        
        if not self.project_id:
            logger.warning("⚠️ GOOGLE_CLOUD_PROJECT not set. Trying to infer from environment...")
            import google.auth
            try:
                _, project = google.auth.default()
                self.project_id = project
            except:
                pass

        if self.project_id:
            logger.info(f"🧠 Initializing Vertex AI Client (Project: {self.project_id}, Location: {self.location})")
            try:
                self.client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
            except Exception as e:
                logger.error(f"❌ Failed to initialize Vertex AI Client: {e}")
                self.client = None
        else:
            logger.error("❌ GOOGLE_CLOUD_PROJECT not found. Cannot initialize Vertex AI.")
            self.client = None

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """
        Splits text into overlapping chunks.
        """
        if not text:
            return []
            
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + chunk_size
            
            # If we are not at the end, try to find a sentence break
            if end < text_len:
                # Look for the last period/newline within the chunk
                last_period = text.rfind('.', start, end)
                last_newline = text.rfind('\n', start, end)
                
                break_point = max(last_period, last_newline)
                
                if break_point != -1 and break_point > start + (chunk_size // 2):
                    end = break_point + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap
            
        return chunks

    @with_retry(RetryConfig(max_retries=3, base_delay=1.0))
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generates vector embedding for a text string using Gemini.
        """
        self._initialize_client()
        
        if not self.client:
            raise ValueError("VectorHandler not initialized (Client is None)")
            
        try:
            logger.info(f"🧠 Generating embedding with model: {self.embedding_model}")
            result = self.client.models.embed_content(
                model=self.embedding_model,
                contents=text
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.warning(f"⚠️ Primary model {self.embedding_model} failed: {e}")
            
            # Fallback to gecko
            fallback_model = "text-embedding-gecko"
            if self.embedding_model != fallback_model:
                logger.info(f"🔄 Retrying with fallback model: {fallback_model}")
                try:
                    result = self.client.models.embed_content(
                        model=fallback_model,
                        contents=text
                    )
                    return result.embeddings[0].values
                except Exception as e2:
                    logger.error(f"❌ Fallback model also failed: {e2}")
                    raise e
            else:
                raise e

# Global instance
_vector_handler = VectorHandler()

def get_vector_handler() -> VectorHandler:
    return _vector_handler
