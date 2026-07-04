"""Ingestion tools for dataset and RAG import workflows."""

import logging
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import sleep
from typing import Any, Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _init_vertex_rag():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("VERTEX_AI_LOCATION") or os.getenv(
        "GOOGLE_CLOUD_LOCATION", "us-central1"
    )

    import vertexai
    from vertexai.preview import rag

    vertexai.init(project=project_id, location=location)
    return rag


def _safe_title(title: str) -> str:
    return "".join(
        [c for c in title if c.isalnum() or c in (" ", "-", "_")]
    ).strip().replace(" ", "_")

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
        import datasets

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

def _build_transformation_config(chunk_size: Optional[int], chunk_overlap: Optional[int]):
    """Builds a Vertex AI RAG TransformationConfig, or None to use API defaults."""
    if not chunk_size:
        return None

    rag = _init_vertex_rag()
    return rag.TransformationConfig(
        chunking_config=rag.ChunkingConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap or 0,
        )
    )


def upload_to_rag_corpus(
    text: str,
    title: str,
    corpus_name: str,
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> str:
    """
    Uploads text to Vertex AI RAG Corpus.

    Args:
        text: The text content.
        title: Title of the document (used for filename).
        corpus_name: Full resource name of the RAG Corpus.
        chunk_size: Chunk size in tokens for Vertex's own chunking. If not
            given, the RAG Engine's API default is used.
        chunk_overlap: Chunk overlap in tokens, paired with chunk_size.

    Returns:
        The created RagFile resource name.
    """
    file_path = None
    try:
        rag = _init_vertex_rag()
        transformation_config = _build_transformation_config(chunk_size, chunk_overlap)

        # Create a temporary file to upload
        safe_title = _safe_title(title)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            prefix=f"{safe_title[:40]}_",
            delete=False,
        ) as f:
            f.write(text)
            file_path = f.name

        try:
            rag.upload_file(
                corpus_name=corpus_name,
                path=file_path,
                display_name=f"{safe_title}.txt",
                transformation_config=transformation_config,
            )
            logger.info(f"Successfully imported {file_path} to {corpus_name}")

            return f"Successfully uploaded {title}."
            
        except Exception as e:
            logger.error(f"RAG import failed: {e}")
            raise
            
    except Exception as e:
        logger.error(f"Failed to upload to RAG: {e}")
        raise
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                logger.warning(f"Failed to remove temp file: {file_path}")


def _upload_file_with_retry(
    rag,
    *,
    corpus_name: str,
    path: str,
    display_name: str,
    transformation_config,
    max_attempts: int = 6,
    base_delay: float = 5.0,
):
    """rag.upload_file wrapped with backoff for the RAG Engine's tight
    per-minute request quota (observed to 429 even on plain list calls).

    rag.upload_file() makes a raw HTTP call (not the GAPIC client) and
    unconditionally calls response.json() on whatever comes back; a 429/5xx
    from the quota limiter can return a non-JSON body, which surfaces as
    requests' JSONDecodeError rather than a google.api_core exception. Both
    are treated as transient here.
    """
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
    from requests.exceptions import JSONDecodeError, RequestException

    for attempt in range(1, max_attempts + 1):
        try:
            return rag.upload_file(
                corpus_name=corpus_name,
                path=path,
                display_name=display_name,
                transformation_config=transformation_config,
            )
        except (
            ResourceExhausted,
            ServiceUnavailable,
            JSONDecodeError,
            RequestException,
        ) as exc:
            if attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "RAG upload throttled (attempt %s/%s) for %s, backing off %.0fs: %s",
                attempt,
                max_attempts,
                display_name,
                delay,
                exc,
            )
            sleep(delay)


def upload_many_to_rag_corpus(
    documents: Iterable[dict[str, str]],
    corpus_name: str,
    *,
    batch_size: int = 1,
    max_workers: int = 1,
    pause_seconds: float = 2.5,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> dict[str, int]:
    """Bulk-upload normalized text documents into a Vertex RAG corpus.

    chunk_size/chunk_overlap are in tokens and are forwarded to Vertex's own
    chunker via TransformationConfig; without them the RAG Engine falls back
    to its own default chunking regardless of source text_type.
    """
    rag = _init_vertex_rag()
    transformation_config = _build_transformation_config(chunk_size, chunk_overlap)
    temp_dir = Path(tempfile.mkdtemp(prefix="christian_rag_"))
    uploaded = 0
    batches = 0

    try:
        paths: list[str] = []
        for index, document in enumerate(documents):
            safe_title = _safe_title(document["title"]) or f"document_{index:05d}"
            file_path = temp_dir / f"{index:05d}_{safe_title[:80]}.txt"
            file_path.write_text(document["text"], encoding="utf-8")
            paths.append(str(file_path))

        if not paths:
            return {"documents": 0, "batches": 0}

        for start in range(0, len(paths), batch_size):
            batch = paths[start : start + batch_size]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        _upload_file_with_retry,
                        rag,
                        corpus_name=corpus_name,
                        path=path,
                        display_name=Path(path).name,
                        transformation_config=transformation_config,
                    )
                    for path in batch
                ]
                for future in as_completed(futures):
                    future.result()
            batches += 1
            uploaded += len(batch)
            logger.info(
                "Imported %s/%s files into %s",
                uploaded,
                len(paths),
                corpus_name,
            )
            if uploaded < len(paths):
                sleep(pause_seconds)

        return {"documents": uploaded, "batches": batches}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
