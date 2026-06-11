"""
Ingest starter philosophy sources into the configured Vertex AI RAG corpus.

This script uploads:
- Plato's Republic from Project Gutenberg
- a small sample from the Hugging Face `wikitext` dataset
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.ingestion_tools import (  # noqa: E402
    fetch_gutenberg_text,
    fetch_huggingface_dataset,
    upload_to_rag_corpus,
)


def ingest_data() -> int:
    load_dotenv()

    corpus_id = os.getenv("PHILOSOPHY_CORPUS_ID")
    if not corpus_id:
        print("Error: PHILOSOPHY_CORPUS_ID is not set in .env")
        print("Please create a RAG corpus and add its ID to .env")
        return 1

    print(f"Initializing philosophy ingest for corpus: {corpus_id}")

    # 1. Plato's Republic from Gutenberg.
    print("\nTask 1: Ingesting Plato's Republic from Gutenberg...")
    try:
        republic_text = fetch_gutenberg_text("1497")
        upload_to_rag_corpus(
            republic_text,
            title="Plato - The Republic",
            corpus_name=corpus_id,
        )
        print("Uploaded: Plato - The Republic")
    except Exception as exc:
        print(f"Failed to ingest Plato's Republic: {exc}")

    # 2. Small general-purpose text sample.
    print("\nTask 2: Ingesting sample from Hugging Face dataset 'wikitext'...")
    try:
        wikitext_sample = fetch_huggingface_dataset(
            "wikitext",
            subset="wikitext-2-v1",
            limit=100,
        )
        upload_to_rag_corpus(
            wikitext_sample,
            title="Wikitext Sample",
            corpus_name=corpus_id,
        )
        print("Uploaded: Wikitext Sample")
    except Exception as exc:
        print(f"Failed to ingest wikitext sample: {exc}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(ingest_data())
