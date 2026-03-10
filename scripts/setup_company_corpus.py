"""
Setup Company Knowledge RAG Corpus

Creates a Vertex AI RAG Corpus for company information including:
- Policies and procedures
- Product technical specifications
- Pricing lists
- Team information
- Internal documentation

Usage:
    python scripts/setup_company_corpus.py

After running, add the returned CORPUS_ID to your .env file:
    COMPANY_CORPUS_ID=projects/.../ragCorpora/...
"""

import os
import sys
import vertexai
from vertexai.preview import rag
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def setup_corpus():
    """Create Company Knowledge RAG Corpus"""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    # Check VERTEX_AI_LOCATION first, then GOOGLE_CLOUD_LOCATION, then default to us-west1
    # Note: RAG Engine has capacity limits in us-central1, so us-west1 is preferred for new projects
    location = os.getenv("VERTEX_AI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")

    if not project_id:
        print("❌ Error: GOOGLE_CLOUD_PROJECT not set in .env")
        print("   Please add: GOOGLE_CLOUD_PROJECT=your-project-id")
        return

    print(f"🔧 Initializing Vertex AI...")
    print(f"   Project: {project_id}")
    print(f"   Location: {location}")
    vertexai.init(project=project_id, location=location)

    display_name = "Company Knowledge Base"
    description = (
        "Company information knowledge base containing policies, procedures, "
        "product specifications, pricing lists, team information, and internal documentation. "
        "Used by agents to answer questions about company operations and products."
    )

    try:
        print(f"\n📦 Creating RAG Corpus: {display_name}...")
        print(f"   Description: {description}")

        # Create corpus via Vertex AI RAG API
        corpus = rag.create_corpus(
            display_name=display_name,
            description=description
        )

        print(f"\n✅ Success! Company Knowledge Corpus created.")
        print(f"\n📋 Corpus Details:")
        print(f"   Name: {corpus.name}")
        print(f"   Display Name: {display_name}")
        print(f"   Location: {location}")

        print(f"\n🔑 Add this to your .env file:")
        print(f"   COMPANY_CORPUS_ID={corpus.name}")

        print(f"\n📁 Next steps:")
        print(f"   1. Add COMPANY_CORPUS_ID to .env")
        print(f"   2. Upload company documents to Drive folder: ADK_Workspace/Company_Knowledge/")
        print(f"   3. Run ingestion script: python scripts/ingest_company_docs.py")

    except Exception as e:
        print(f"\n⚠️  Corpus creation failed: {e}")

        # Try to find existing corpus
        try:
            print("\n🔍 Searching for existing corpus...")
            corpora = rag.list_corpora()
            found = False

            for c in corpora:
                if c.display_name == display_name:
                    print(f"\n✅ Found existing corpus: {c.display_name}")
                    print(f"   ID: {c.name}")
                    print(f"\n🔑 Use this in your .env file:")
                    print(f"   COMPANY_CORPUS_ID={c.name}")
                    found = True
                    return

            if not found:
                print(f"❌ No existing corpus found with name: {display_name}")
                print(f"\n💡 Troubleshooting:")
                print(f"   - Verify Vertex AI RAG API is enabled in Google Cloud Console")
                print(f"   - Check that location '{location}' supports RAG API")
                print(f"   - Ensure service account has 'Vertex AI User' role")

        except Exception as list_e:
            print(f"❌ Failed to list existing corpora: {list_e}")

if __name__ == "__main__":
    print("=" * 70)
    print("Company Knowledge RAG Corpus Setup")
    print("=" * 70)
    setup_corpus()
    print("=" * 70)
