# Google ADK Multi-Agent System

Enterprise multi-agent system built with [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) for intelligent Google Workspace automation, Croatian fiscal compliance (Fiskalizacija 2.0), and business process orchestration.

## Features

- **15 Specialized Agents** with Smart Orchestrator routing via `transfer_to_agent`
- **3-Tier Model Strategy** - Gemini 3.1 Pro (orchestration), 2.5 Pro (precision), 3 Flash (speed)
- **Web Dashboard** - FastAPI + Alpine.js with SSE streaming
- **Task Scheduler** - APScheduler with cron, interval, and date triggers
- **Croatian Fiskalizacija 2.0** - B2C (CIS/JIR), B2B (UBL 2.1), B2G (Peppol), EU, International
- **Firestore Persistence** - Conversations, invoices, audit logs, agent learning
- **Resilience Stack** - Circuit breakers, rate limiting, retry handling, response caching
- **Human-in-the-Loop** - Approval workflows for destructive/expensive operations
- **Telegram Bot** - Alternative chat interface

---

## Architecture

```
                         ┌──────────────────┐
                         │   USER REQUEST   │
                         │  CLI / Web / TG  │
                         └────────┬─────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │      SMART ORCHESTRATOR      │
                    │    gemini-3.1-pro-preview     │
                    │                               │
                    │  - Analyzes complex requests   │
                    │  - Plans multi-step workflows  │
                    │  - Delegates to worker agents  │
                    └──────────────┬────────────────┘
                                   │
          ┌────────────┬───────────┼───────────┬────────────┐
          ▼            ▼           ▼           ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │  Mailer  │ │Secretary │ │ Analyst  │ │Marketing │ │Scheduler │
    │  (Gmail) │ │(Calendar)│ │ (Sheets) │ │(Ads/Img) │ │  (Cron)  │
    └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
          ... + 10 more specialized agents
```

---

## Agents

### Google Workspace Agents

| Agent | Model | Specialization |
|-------|-------|----------------|
| **Mailer** | gemini-3-flash | Gmail - send, read, search, drafts |
| **Secretary** | gemini-3-flash | Calendar - events, scheduling, availability |
| **Librarian** | gemini-3-flash | Drive - files, folders, search, sharing |
| **Analyst** | gemini-2.5-pro | Sheets - read, write, analyze, formulas |
| **Scribe** | gemini-3-flash | Docs - create, edit, format |
| **Rolodex** | gemini-3-flash | Contacts - search, create, update |
| **Tracker** | gemini-3-flash | Tasks - create, list, complete |

### Research & Content Agents

| Agent | Model | Specialization |
|-------|-------|----------------|
| **Researcher** | gemini-3-flash | Web research with Vertex AI grounding |
| **Scraper** | gemini-3-flash | Web scraping and data extraction |
| **Synthesizer** | gemini-3-flash | Content synthesis and report generation |

### Business & Finance Agents

| Agent | Model | Specialization |
|-------|-------|----------------|
| **Fiskalizacija** | gemini-3-flash | Croatian e-invoicing pipeline (B2C/B2B/B2G/EU/INT) |
| **Expense** | gemini-3-flash | Receipt OCR with Gemini Vision |
| **Marketing** | gemini-3-flash | Google Ads, Imagen 3, Veo video generation |
| **Scheduler** | gemini-3-flash | Recurring tasks with APScheduler |

### Fiskalizacija Pipeline (SequentialAgent)

The fiscalization system uses a 3-stage sequential pipeline:

| Stage | Agent | Model | Role |
|-------|-------|-------|------|
| 1 | **Fiskalni Pripremac** | gemini-3-flash | Data preparation, OIB validation, KPD lookup |
| 2 | **Fiskalni Validator** | gemini-2.5-pro | Zero-tolerance validation with thinking mode |
| 3 | **Fiskalni Executor** | gemini-2.5-pro | XML signing, FINA CIS submission, JIR retrieval |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud project with billing enabled
- OAuth 2.0 credentials (Desktop app type)

### Installation

```bash
# Clone repository
git clone https://github.com/deltablues1/google-adk-multi-agent.git
cd google-adk-multi-agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Google Cloud project ID and OAuth credentials
```

### Enable Google APIs

```bash
gcloud services enable \
  gmail.googleapis.com \
  drive.googleapis.com \
  docs.googleapis.com \
  sheets.googleapis.com \
  calendar-json.googleapis.com \
  people.googleapis.com \
  tasks.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com
```

### Authentication

```bash
# Application Default Credentials (for Vertex AI)
gcloud auth application-default login

# OAuth 2.0 (for Google Workspace APIs)
python scripts/force_oauth_login.py
```

### Run

Three ways to use the system:

```bash
# 1. CLI Interface (interactive terminal)
python main.py

# 2. Web Dashboard (FastAPI + Alpine.js)
python run_web.py --host 127.0.0.1 --port 8000

# 3. Scheduler (recurring tasks)
python run_scheduler.py
```

---

## Usage Examples

```
You: Show me the last 5 emails
→ Orchestrator → Mailer agent reads Gmail

You: Research AI trends and email a summary to marko@example.com
→ Orchestrator → Researcher → Synthesizer → Mailer

You: IF calendar is free at 2pm, schedule a meeting; ELSE suggest alternatives
→ Orchestrator → Decision Validator → Secretary

You: Create a B2C invoice for customer OIB 12345678901
→ Orchestrator → Fiskalizacija → Pripremac → Validator → Executor → CIS

You: Every Monday at 9am, send me a weekly report
→ Orchestrator → Scheduler (creates recurring cron job)
```

---

## Project Structure

```
google-adk-multi-agent/
├── main.py                        # CLI entry point
├── run_web.py                     # Web dashboard entry point
├── run_scheduler.py               # Scheduler entry point
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment template
│
├── agents/
│   ├── adk_agents/                # ADK agent implementations
│   │   ├── smart_orchestrator.py  # Central routing agent
│   │   ├── mailer_adk.py          # Gmail operations
│   │   ├── secretary_adk.py       # Calendar management
│   │   ├── analyst_adk.py         # Sheets analysis
│   │   ├── librarian_adk.py       # Drive management
│   │   ├── scribe_adk.py          # Docs creation
│   │   ├── rolodex_adk.py         # Contacts lookup
│   │   ├── tracker_adk.py         # Tasks management
│   │   ├── researcher_adk.py      # Web research
│   │   ├── scraper_adk.py         # Data extraction
│   │   ├── synthesizer_adk.py     # Content synthesis
│   │   ├── marketing_adk.py       # Ads & visual generation
│   │   ├── expense_adk.py         # Receipt OCR
│   │   ├── scheduler_adk.py       # Task scheduling
│   │   ├── fiskalizacija_adk.py   # Fiscal pipeline wrapper
│   │   ├── fiskalni_pripremac_adk.py  # Fiscal data prep
│   │   ├── fiskalni_validator_adk.py  # Fiscal validation
│   │   ├── fiskalni_executor_adk.py   # CIS submission
│   │   └── adk_agent_factory.py   # Agent factory
│   └── */instructions.md          # Per-agent instruction files
│
├── tools/
│   ├── adk_tools/                 # ADK-compatible tool wrappers
│   ├── api_implementations/       # Raw Google API integrations
│   └── resilience/                # Circuit breaker, rate limiter, retry, cache
│
├── config/
│   ├── agent_registry.py          # Agent registration & model tiers
│   └── scheduler_config.py        # Scheduler job models
│
├── interfaces/
│   ├── base_interface.py          # Abstract base interface
│   ├── web_interface.py           # FastAPI web interface
│   ├── scheduler_interface.py     # Scheduler orchestration
│   └── telegram_interface.py      # Telegram bot
│
├── web/
│   ├── app.py                     # FastAPI application
│   ├── models.py                  # Pydantic request/response models
│   └── static/                    # Alpine.js SPA dashboard
│
├── services/
│   └── firestore_persistence.py   # Async Firestore write-through
│
├── auth/                          # OAuth 2.0 management
├── monitoring/                    # Cloud Logging & metrics
├── data/seed/                     # Seed data (company, customers, products)
├── scripts/                       # Setup & utility scripts
├── tests/                         # Test suite
└── docs/                          # Documentation
```

---

## Configuration

### Model Tiers

| Tier | Model | Agents | Use Case |
|------|-------|--------|----------|
| **Tier 1** | `gemini-3.1-pro-preview` | Orchestrator | Complex reasoning, 2M+ context |
| **Tier 2** | `gemini-2.5-pro` | Analyst, Validator, Executor, Socrates | Thinking mode, precision |
| **Tier 3** | `gemini-3-flash-preview` | 12+ agents | Speed (180+ tok/s), low latency |

### Environment Variables

See [.env.example](.env.example) for all configuration options including:
- Google Cloud project & OAuth credentials
- Gemini model selection (Vertex AI or Google AI API)
- Session storage (memory, database, Firestore)
- Croatian fiscalization certificates
- Telegram bot token
- Human-in-the-loop settings

---

## Firestore Database

14 collections for persistent storage:

| Collection | Purpose |
|------------|---------|
| `conversations` | Chat session history |
| `invoices_b2c/b2b/b2g/eu/int` | Invoice records by type |
| `products` | Product/service catalog |
| `customers` | Customer master data |
| `quotes` | Price quotes |
| `expense_records` | OCR-processed receipts |
| `scheduled_jobs` | Scheduler job definitions |
| `agent_learning` | Agent improvement data |
| `audit_log` | System audit trail |

Setup: `python scripts/setup_firestore.py`
Seed data: `python scripts/seed_data.py`

---

## Testing

```bash
# Run test batch (25 agent scenarios)
python test_batch.py

# Resume from specific test
python test_batch.py --start_from 10
```

See [Testing Guide](docs/testing/TESTING_GUIDE.md) and [Test Queries](docs/testing/test_queries.md) for 170+ test scenarios.

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Setup Guide](docs/guides/SETUP_GUIDE.md) | Initial system setup |
| [Firestore Quickstart](docs/guides/FIRESTORE_QUICKSTART.md) | Database setup |
| [Deployment Guide](docs/guides/DEPLOYMENT_GUIDE.md) | Production deployment |
| [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE_2.0.md) | Technical architecture |
| [Resilience Stack](docs/implementation/COMPLETE_RESILIENCE_STACK_SUMMARY.md) | Error handling patterns |
| [Multi-Agent Workflows](docs/multi_agent_workflows.md) | Complex workflow examples |
| [ADK Reference](docs/ADK_REFERENCE.md) | Google ADK patterns |

---

## Tech Stack

- **AI Framework**: [Google ADK](https://google.github.io/adk-docs/) (Agent Development Kit)
- **LLM**: Gemini 3.1 Pro / 2.5 Pro / 3 Flash via Vertex AI
- **Backend**: FastAPI, uvicorn, SSE streaming
- **Frontend**: Alpine.js SPA
- **Database**: Google Cloud Firestore (Native Mode)
- **Scheduling**: APScheduler
- **Auth**: OAuth 2.0 + Application Default Credentials
- **Monitoring**: Google Cloud Logging & Monitoring
