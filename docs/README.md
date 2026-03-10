# Documentation Index

Welcome to the Google ADK Multi-Agent System documentation.

---

## Quick Links

- [Main README](../README.md) - Project overview and quick start
- [System Architecture](architecture/SYSTEM_ARCHITECTURE_2.0.md) - Technical architecture

---

## Guides

| Guide | Description |
|-------|-------------|
| [Setup Guide](guides/SETUP_GUIDE.md) | Initial setup and configuration |
| [Deployment Guide](guides/DEPLOYMENT_GUIDE.md) | Production deployment |
| [Production Setup](guides/PRODUCTION_SETUP.md) | Production environment configuration |
| [Firestore Quickstart](guides/FIRESTORE_QUICKSTART.md) | Database setup |
| [Monitoring Quickstart](guides/MONITORING_QUICKSTART.md) | Observability setup |
| [Rate Limiting Guide](guides/RATE_LIMITING_GUIDE.md) | API rate limiting configuration |
| [Environment Configuration](ENVIRONMENT_CONFIGURATION.md) | Environment variables reference |
| [Error Handling Guide](ERROR_HANDLING_GUIDE.md) | Error handling patterns |

---

## Features

| Feature | Description |
|---------|-------------|
| [Invoice System](features/README_INVOICE_SYSTEM.md) | OCR invoice processing with Gemini Vision |
| [Multi-Agent Workflows](multi_agent_workflows.md) | Complex workflow examples |
| [Orchestrator Workflows](orchestrator_workflow_examples.md) | Orchestrator routing patterns |
| [Firestore Database](firestore_database_setup.md) | Database schema and setup |
| [Knowledge Base](knowledge_base_setup.md) | RAG knowledge base setup |

---

## Architecture

| Document | Description |
|----------|-------------|
| [System Architecture 2.0](architecture/SYSTEM_ARCHITECTURE_2.0.md) | Current system design |
| [ADK Compliance Analysis](architecture/ADK_COMPLIANCE_ANALYSIS_AND_ROADMAP.md) | Google ADK alignment |

---

## Implementation Details

Technical implementation summaries for core features.

| Component | Description |
|-----------|-------------|
| [Complete Resilience Stack](implementation/COMPLETE_RESILIENCE_STACK_SUMMARY.md) | Full resilience layer overview |
| [Caching](implementation/CACHING_IMPLEMENTATION_SUMMARY.md) | Response caching (40-50% API reduction) |
| [Rate Limiting](implementation/RATE_LIMIT_IMPLEMENTATION_SUMMARY.md) | API rate limiting |
| [Circuit Breaker](implementation/CIRCUIT_BREAKER_SUMMARY.md) | Fault tolerance |
| [Retry Handler](implementation/RETRY_HANDLER_SUMMARY.md) | Automatic retries |
| [Monitoring](implementation/MONITORING_IMPLEMENTATION_COMPLETE.md) | Cloud Logging & metrics |
| [Deep Research Agent](implementation/DEEP_RESEARCH_AGENT_IMPLEMENTATION.md) | Research agent implementation |
| [OCR Expense Processing](implementation/OCR_EXPENSE_IMPLEMENTATION_PLAN.md) | Receipt OCR pipeline |

---

## Testing

| Document | Description |
|----------|-------------|
| [Testing Guide](testing/TESTING_GUIDE.md) | How to run tests |
| [Test Queries](testing/test_queries.md) | 170+ test scenarios for all agents |
| [Quick Start Testing](guides/QUICK_START_TESTING.md) | Quick testing reference |
| [Run All Tests](guides/RUN_ALL_TESTS.md) | Full test suite execution |

---

## Agent Instructions

Each agent has its own instruction file that defines its behavior:

| Agent | Instructions | Specialization |
|-------|--------------|----------------|
| Orchestrator | [instructions.md](../agents/orchestrator/instructions.md) | Request routing & delegation |
| Analyst | [instructions.md](../agents/analyst/instructions.md) | Google Sheets analysis |
| Expense | [instructions.md](../agents/expense/instructions.md) | Receipt OCR |
| Fiskalizacija | [fiskalizacija.md](../agents/fiskalizacija.md) | Croatian e-invoicing |
| Librarian | [instructions.md](../agents/librarian/instructions.md) | Google Drive |
| Mailer | [instructions.md](../agents/mailer/instructions.md) | Gmail operations |
| Marketing | [instructions.md](../agents/marketing/instructions.md) | Visual assets & ads |
| Philosophy (Socrates) | [instructions.md](../agents/philosophy/instructions.md) | Philosophical dialogue & RAG |
| Researcher | [instructions.md](../agents/researcher/instructions.md) | Web research |
| Rolodex | [instructions.md](../agents/rolodex/instructions.md) | Google Contacts |
| Scheduler | [instructions.md](../agents/scheduler/instructions.md) | Recurring tasks |
| Scraper | [instructions.md](../agents/scraper/instructions.md) | Data extraction |
| Scribe | [instructions.md](../agents/scribe/instructions.md) | Google Docs |
| Secretary | [instructions.md](../agents/secretary/instructions.md) | Google Calendar |
| Synthesizer | [instructions.md](../agents/synthesizer/instructions.md) | Content synthesis |
| Tracker | [instructions.md](../agents/tracker/instructions.md) | Google Tasks |

---

## Development Resources

| Resource | Description |
|----------|-------------|
| [ADK Reference](ADK_REFERENCE.md) | Google ADK patterns and concepts |
| [Agent Instruction Template](agent_instruction_template.md) | Template for creating new agents |
| [CLI Workflow Guide](CLI_WORKFLOW_GUIDE.md) | CLI workflow patterns |
| [Forward Plan](FORWARD_PLAN_FEB_2026.md) | Development roadmap |
