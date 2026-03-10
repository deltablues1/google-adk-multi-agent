# Company Knowledge Base Setup Guide

This guide explains how to set up and use the company knowledge base system with Vertex AI RAG.

## Overview

The company knowledge base allows agents to access company information including:
- Policies and procedures
- Product technical specifications
- Pricing lists and product catalogs
- Team information and organizational structure
- Internal documentation

## Architecture

```
ADK_Workspace/Company_Knowledge/  ← Upload company docs here (Drive)
         ↓
    [Ingestion Script]
         ↓
   Vertex AI RAG Corpus  ← Stores embeddings and indexes
         ↓
   [CompanyKnowledgeBase Tool]  ← Agents query via this tool
         ↓
    Agent Responses  ← Answers based on company docs
```

## Setup Steps

### 1. Create the RAG Corpus

First, create a Vertex AI RAG Corpus to store company knowledge:

```bash
python scripts/setup_company_corpus.py
```

**Output:**
```
✅ Success! Company Knowledge Corpus created.

📋 Corpus Details:
   Name: projects/YOUR_PROJECT/locations/us-west1/ragCorpora/CORPUS_ID
   Display Name: Company Knowledge Base
   Location: us-west1

🔑 Add this to your .env file:
   COMPANY_CORPUS_ID=projects/YOUR_PROJECT/locations/us-west1/ragCorpora/CORPUS_ID
```

### 2. Add Corpus ID to .env

Copy the corpus ID from the output and add it to your `.env` file:

```bash
COMPANY_CORPUS_ID=projects/YOUR_PROJECT/locations/us-west1/ragCorpora/CORPUS_ID
```

### 3. Create Drive Folder

The `Company_Knowledge` folder should already be defined in `config/drive_map.yaml`:

```yaml
- name: "Company_Knowledge"
  alias: "company"
  description: "Company information, policies, procedures (RAG ingestion)"
```

The DriveNavigator will create this folder automatically when needed, or you can create it manually:
- Navigate to your Drive
- Go to `ADK_Workspace/`
- Create folder: `Company_Knowledge/`

### 4. Upload Company Documents

Upload your company documents to the `Company_Knowledge` folder:

**Supported file types:**
- PDF documents (`.pdf`)
- Text files (`.txt`)
- Markdown files (`.md`)
- Google Docs (will be exported as PDF)

**Example documents to upload:**
- Company handbook
- Product specifications
- Pricing lists
- Team directory
- Process documentation
- FAQ documents

### 5. Run Ingestion Script

Import all documents into the RAG Corpus:

```bash
python scripts/ingest_company_docs.py
```

**Output:**
```
🔍 Scanning Company_Knowledge folder...
✅ Found 5 documents in Company_Knowledge folder
   - Company Handbook.pdf (application/pdf)
   - Product Catalog.pdf (application/pdf)
   - Team Directory (application/vnd.google-apps.document)
   - Pricing 2025.pdf (application/pdf)
   - FAQ.txt (text/plain)

📥 Downloading 5 documents...
   Downloading: Company Handbook.pdf
   ✅ Downloaded to: /tmp/company_doc_abc123.pdf
   ...

📦 Importing 5 files to RAG Corpus...
   [1/5] Importing: Company Handbook.pdf
   ✅ Imported: Company Handbook.pdf
   ...

✅ Company knowledge base ingestion complete!
```

### 6. Add Tool to Agents

Now you can add the company knowledge tool to your agents:

```python
from tools.company_tools import get_company_knowledge_tool

# Create the tool
company_tool = get_company_knowledge_tool()

# Add to agent
from agents.adk_agents.adk_agent_factory import create_adk_agent

agent = create_adk_agent(
    name="assistant",
    model="gemini-2.5-pro",
    description="General assistant with company knowledge",
    tools=[company_tool, ...],
    instruction="You are a helpful assistant with access to company information...",
)
```

### 7. Test the Knowledge Base

Test that the knowledge base works:

```python
import asyncio
from agents.adk_agents.secretary_adk import create_secretary_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

async def test():
    # Create agent with company knowledge
    agent = create_secretary_agent()  # If you added the tool

    runner = Runner(
        agent=agent,
        app_name="test",
        session_service=InMemorySessionService()
    )

    # Test query
    response = await runner.run_async(
        new_message="What are our company's core products?",
        session_id="test-123",
        user_id="test-user"
    )

    print(response)

asyncio.run(test())
```

## Updating the Knowledge Base

When you add new documents or update existing ones:

1. Upload/update documents in `Company_Knowledge` folder
2. Re-run ingestion script:
   ```bash
   python scripts/ingest_company_docs.py
   ```

The script will detect changes and update the corpus.

## Adding Company Knowledge to Existing Agents

### Option 1: Add to Individual Agents

Edit agent factory files to include company tool:

**Example: Secretary Agent** (`agents/adk_agents/secretary_adk.py`)

```python
from tools.company_tools import get_company_knowledge_tool

def create_secretary_agent(model: str = "gemini-2.5-flash", credentials=None):
    # Import calendar tools
    from tools.adk_tools.calendar_adk_tools import ...

    # Add company knowledge tool
    from tools.company_tools import get_company_knowledge_tool

    tools = [
        # Calendar tools
        list_events,
        create_event,
        ...
        # Company knowledge
        get_company_knowledge_tool(),
    ]

    agent = create_adk_agent(
        name="secretary",
        model=model,
        tools=tools,
        ...
    )
    return agent
```

### Option 2: Create Dedicated CompanyInfo Agent

Create a specialized agent for company queries:

**File:** `agents/adk_agents/company_info_adk.py`

```python
from google.adk.agents import LlmAgent
from tools.company_tools import get_company_knowledge_tool
from agents.adk_agents.adk_agent_factory import create_adk_agent

def create_company_info_agent(
    model: str = "gemini-2.5-flash",
    credentials=None
) -> LlmAgent:
    """
    Create CompanyInfo agent for answering questions about company.
    """
    company_tool = get_company_knowledge_tool()

    agent = create_adk_agent(
        name="company_info",
        model=model,
        description="Company information specialist. Answers questions about company policies, products, team, and procedures.",
        tools=[company_tool],
        instruction="""
        You are the CompanyInfo agent, specializing in company knowledge.

        Use the CompanyKnowledgeBase tool to answer questions about:
        - Company policies and procedures
        - Product specifications and catalogs
        - Pricing information
        - Team structure and contacts
        - Internal processes

        Always cite the source document when providing information.
        If information is not in the knowledge base, say so clearly.
        """,
        config={
            "temperature": 0.3,  # Lower temperature for factual accuracy
            "max_tokens": 2048,
        }
    )

    return agent
```

Then register in `config/agent_registry.py`:

```python
"company_info": AgentConfig(
    name="company_info",
    module="agents.adk_agents.company_info_adk",
    class_name="create_company_info_agent",
    model="gemini-2.5-flash",
    description="Company information specialist. Answers questions about policies, products, team.",
    tools=["company_knowledge"],
    config={"temperature": 0.3},
    use_adk=True,
    adk_factory_func="create_company_info_agent"
),
```

And add routing rule in `agents/orchestrator/instructions.md`:

```markdown
#### Company Information → **CompanyInfo Agent**
- Questions about company policies
- Product specifications
- Pricing information
- Team structure
- Internal procedures
```

## Troubleshooting

### Error: "COMPANY_CORPUS_ID not set"

**Solution:**
1. Run `python scripts/setup_company_corpus.py`
2. Copy the corpus ID to `.env`
3. Restart your application

### Error: "Company_Knowledge folder not found"

**Solution:**
1. Check `config/drive_map.yaml` has the folder defined
2. Create folder manually in Drive: `ADK_Workspace/Company_Knowledge/`
3. Or run DriveNavigator to auto-create folders

### Error: "No documents found"

**Solution:**
1. Upload documents to `Company_Knowledge` folder
2. Verify documents are not in trash
3. Check file types are supported (PDF, TXT, MD, Google Docs)

### Error: "Import failed"

**Solution:**
1. Verify Vertex AI RAG API is enabled in Google Cloud Console
2. Check service account has "Vertex AI User" role
3. Verify location (us-west1) supports RAG API
4. Check COMPANY_CORPUS_ID is correct

## File Reference

### New Files Created

- `config/drive_map.yaml` - Updated with Company_Knowledge folder
- `scripts/setup_company_corpus.py` - Creates Vertex AI RAG Corpus
- `tools/company_tools.py` - RAG tool for querying company knowledge
- `scripts/ingest_company_docs.py` - Imports documents into corpus
- `docs/knowledge_base_setup.md` - This guide

### Environment Variables

```bash
# Required
COMPANY_CORPUS_ID=projects/PROJECT/locations/LOCATION/ragCorpora/CORPUS_ID

# Already configured
GOOGLE_CLOUD_PROJECT=your-project-id
VERTEX_AI_LOCATION=us-west1  # Or your preferred location
```

## Next Steps

After setting up the company knowledge base:

1. **Add to relevant agents** - Secretary, Mailer, Researcher can benefit from company context
2. **Test with real queries** - Try asking agents about company products, policies, etc.
3. **Expand content** - Add more documents as needed
4. **Monitor usage** - Check Vertex AI console for RAG query usage
5. **Consider Phase 3** - Implement Firestore for structured data (customers, quotes)

## See Also

- [Philosophy RAG Setup](../agents/philosophy/README.md) - Example of RAG implementation
- [Vertex AI RAG Documentation](https://cloud.google.com/vertex-ai/docs/generative-ai/model-reference/rag-api)
- [Drive Navigator](../tools/drive_navigator.py) - Folder management
- [Agent Registry](../config/agent_registry.py) - Agent configuration
