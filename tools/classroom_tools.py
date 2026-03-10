"""
Philosophy Classroom Tools
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_philosophy_rag_tool():
    """
    Creates and returns the Vertex AI RAG tool for the Philosophy Classroom.
    Returns None if PHILOSOPHY_CORPUS_ID is not configured.
    """
    corpus_id = os.getenv("PHILOSOPHY_CORPUS_ID")

    if not corpus_id:
        logger.warning("PHILOSOPHY_CORPUS_ID not set. Socrates will work without RAG knowledge base.")
        return None

    try:
        from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval
        return VertexAiRagRetrieval(
            name="PhilosophyKnowledgeBase",
            description="A knowledge base containing philosophical texts (Plato, etc.). Use this to answer questions about philosophy.",
            rag_corpora=[corpus_id]
        )
    except Exception as e:
        logger.warning(f"Failed to create Philosophy RAG tool: {e}. Socrates will work without RAG.")
        return None
