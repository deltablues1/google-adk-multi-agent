"""
Ingest Philosophy Datasets
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.curator.curator_agent import CuratorAgent

# Load environment variables
load_dotenv()

async def ingest_data():
    corpus_id = os.getenv("PHILOSOPHY_CORPUS_ID")
    if not corpus_id:
        print("❌ Error: PHILOSOPHY_CORPUS_ID is not set in .env")
        print("Please create a RAG Corpus in Vertex AI and add its ID to .env")
        return

    print(f"📚 Initializing Curator Agent for Corpus: {corpus_id}...")
    curator = CuratorAgent()

    # 1. Ingest a sample book from Gutenberg (Plato's Republic)
    # ID 1497 is "The Republic"
    print("\n🏛️ Task 1: Ingesting Plato's Republic from Gutenberg...")
    try:
        response = ""
        async for chunk in curator.run_async(f"Ingest book with ID 1497 (Plato's Republic) from Gutenberg into the RAG corpus '{corpus_id}'. Title it 'Plato - The Republic'."):
            if isinstance(chunk, str):
                response += chunk
            elif hasattr(chunk, 'text'):
                response += chunk.text
        print(f"Curator Response: {response}")
    except Exception as e:
        print(f"❌ Failed to ingest book: {e}")

    # 2. Ingest a sample dataset from Hugging Face (wikitext)
    # We'll take a tiny slice just to prove it works
    print("\n💾 Task 2: Ingesting sample from 'wikitext' dataset...")
    try:
        response = ""
        async for chunk in curator.run_async(f"Ingest the first 100 rows of 'wikitext' dataset (subset 'wikitext-2-v1') into the RAG corpus '{corpus_id}'."):
            if isinstance(chunk, str):
                response += chunk
            elif hasattr(chunk, 'text'):
                response += chunk.text
        print(f"Curator Response: {response}")
    except Exception as e:
        print(f"❌ Failed to ingest dataset: {e}")

if __name__ == "__main__":
    asyncio.run(ingest_data())
