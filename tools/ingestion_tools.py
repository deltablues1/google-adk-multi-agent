"""
Ingestion Tools for Curator Agent
"""

import os
import requests
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
import datasets
from google.cloud import aiplatform

logger = logging.getLogger(__name__)

def fetch_gutenberg_text(book_id: str) -> str:
    """
    Downloads text from Project Gutenberg.
    
    Args:
        book_id: The ID of the book (e.g., '1497' for Plato's Republic).
        
    Returns:
        The text content of the book.
    """
    url = f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt"
    # Fallback to cache/txt if -0 not found
    fallback_url = f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
    
    try:
        response = requests.get(url)
        if response.status_code != 200:
            logger.info(f"Primary URL failed, trying fallback: {fallback_url}")
            response = requests.get(fallback_url)
            response.raise_for_status()
            
        text = response.text
        
        # Basic cleaning of Gutenberg headers/footers
        # This is heuristic and might need adjustment
        start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
        end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"
        
        start_idx = text.find(start_marker)
        end_idx = text.find(end_marker)
        
        if start_idx != -1:
            # Move past the marker line
            start_idx = text.find("\n", start_idx) + 1
            
        if end_idx != -1:
            text = text[:end_idx]
            
        if start_idx != -1:
            text = text[start_idx:]
            
        return text.strip()
        
    except Exception as e:
        logger.error(f"Failed to fetch Gutenberg book {book_id}: {e}")
        raise

def fetch_huggingface_dataset(dataset_name: str, subset: Optional[str] = None, split: str = "train", limit: int = 100) -> str:
    """
    Fetches text from a Hugging Face dataset.
    
    Args:
        dataset_name: Name of the dataset (e.g., 'wikitext').
        subset: Subset name (e.g., 'wikitext-2-v1').
        split: Split to use (default: 'train').
        limit: Number of rows to fetch.
        
    Returns:
        Concatenated text from the dataset.
    """
    try:
        # Load dataset in streaming mode to avoid downloading everything
        ds = datasets.load_dataset(dataset_name, subset, split=split, streaming=True)
        
        texts = []
        count = 0
        for row in ds:
            if count >= limit:
                break
            
            # Try common text column names
            text_content = row.get("text") or row.get("content") or row.get("document")
            if text_content:
                texts.append(text_content)
                count += 1
                
        return "\n\n".join(texts)
        
    except Exception as e:
        logger.error(f"Failed to fetch HF dataset {dataset_name}: {e}")
        raise

def upload_to_rag_corpus(text: str, title: str, corpus_name: str) -> str:
    """
    Uploads text to Vertex AI RAG Corpus.
    
    Args:
        text: The text content.
        title: Title of the document (used for filename).
        corpus_name: Full resource name of the RAG Corpus.
        
    Returns:
        The created RagFile resource name.
    """
    try:
        # Initialize Vertex AI
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        # Check VERTEX_AI_LOCATION first, then GOOGLE_CLOUD_LOCATION, then default to us-central1
        location = os.getenv("VERTEX_AI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        
        # Initialize vertexai (required for rag)
        import vertexai
        from vertexai.preview import rag
        
        vertexai.init(project=project_id, location=location)
        
        # Create a temporary file to upload
        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        file_path = f"{safe_title}.txt"
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
            
        # Import to Corpus using vertexai.preview.rag
        try:
            # Note: rag.RagCorpus constructor takes the resource name
            corpus = rag.RagCorpus(corpus_name)
            
            # import_files takes a list of paths
            rag_file = corpus.import_files(
                paths=[file_path],
                chunk_size=512,
                chunk_overlap=50
            )
            logger.info(f"Successfully imported {file_path} to {corpus_name}")
            
            # Clean up
            os.remove(file_path)
            
            return f"Successfully uploaded {title}."
            
        except Exception as e:
            logger.error(f"RAG import failed: {e}")
            raise
            
    except Exception as e:
        logger.error(f"Failed to upload to RAG: {e}")
        raise
