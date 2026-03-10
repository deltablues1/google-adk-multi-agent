"""
Company Knowledge Tools

ADK-compatible tools for accessing company information via Vertex AI RAG.
Provides access to company policies, procedures, product specifications,
pricing lists, and internal documentation.
"""

import os
from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval

def get_company_knowledge_tool():
    """
    Creates and returns the Vertex AI RAG tool for Company Knowledge Base.

    This tool provides access to:
    - Company policies and procedures
    - Product technical specifications
    - Pricing lists and product catalogs
    - Team information and organizational structure
    - Internal documentation

    Documents are stored in Drive folder: ADK_Workspace/Company_Knowledge/

    Returns:
        VertexAiRagRetrieval: ADK tool for querying company knowledge base

    Usage:
        # In agent factory:
        from tools.company_tools import get_company_knowledge_tool

        company_tool = get_company_knowledge_tool()
        agent = create_adk_agent(
            name="assistant",
            tools=[company_tool, ...],
            ...
        )
    """
    corpus_id = os.getenv("COMPANY_CORPUS_ID")

    # Fallback if not set - warn user
    if not corpus_id:
        print("⚠️  Warning: COMPANY_CORPUS_ID not set in .env")
        print("   Run: python scripts/setup_company_corpus.py")
        print("   Then add the corpus ID to .env file")
        # Return placeholder - will fail gracefully if used
        corpus_id = "projects/YOUR_PROJECT/locations/us-west1/ragCorpora/YOUR_CORPUS_ID"

    return VertexAiRagRetrieval(
        name="CompanyKnowledgeBase",
        description=(
            "Company knowledge base containing policies, procedures, product specifications, "
            "pricing lists, team information, and internal documentation. "
            "Use this to answer questions about company operations, products, policies, "
            "team structure, or any internal company information."
        ),
        rag_corpora=[corpus_id]
    )


# Singleton instance for easy import
_company_knowledge_tool = None

def company_knowledge_tool():
    """
    Get or create singleton instance of company knowledge tool.

    Returns:
        VertexAiRagRetrieval: Singleton tool instance
    """
    global _company_knowledge_tool

    if _company_knowledge_tool is None:
        _company_knowledge_tool = get_company_knowledge_tool()

    return _company_knowledge_tool
