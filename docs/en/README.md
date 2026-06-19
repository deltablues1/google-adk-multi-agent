# Documentation (English)

> 🇭🇷 Hrvatska verzija: [docs/hr/README.md](../hr/README.md)

Bilingual documentation for the Google ADK Multi-Agent System. This `en/`
folder holds the English versions; mirror files live under `docs/hr/`.

---

## What changed recently

These features were added in code but were previously undocumented. Start here
if you are catching up on the latest changes:

| Topic | Description |
|-------|-------------|
| [LLM Providers (Gemini / Claude)](llm-providers.md) | `LLM_PROVIDER` switch, per-agent Claude routing via LiteLLM, prompt caching, retries |
| [Token Accounting & Cost](token-accounting.md) | Per-agent token stats, `/tokens` command, cost estimate with cache-read credit |
| [Voice (Gemini & OpenAI)](voice.md) | STT/TTS engines, OpenAI voice toggle, voice runtime tuning |

---

## Core guides (legacy English docs)

These existing documents remain valid and are linked from here until they are
migrated into the bilingual structure:

| Guide | Description |
|-------|-------------|
| [Main README](../../README.md) | Project overview and quick start |
| [Setup Guide](../guides/SETUP_GUIDE.md) | Initial setup and configuration |
| [Environment Configuration](../ENVIRONMENT_CONFIGURATION.md) | Environment variables reference |
| [Deployment Guide](../guides/DEPLOYMENT_GUIDE.md) | Production deployment |
| [System Architecture 2.0](../architecture/SYSTEM_ARCHITECTURE_2.0.md) | Technical architecture |
| [Resilience Stack](../implementation/COMPLETE_RESILIENCE_STACK_SUMMARY.md) | Circuit breaker, rate limit, retry, cache |
| [Multi-Agent Workflows](../multi_agent_workflows.md) | Complex workflow examples |
| [ADK Reference](../ADK_REFERENCE.md) | Google ADK patterns |
| [Full documentation index](../README.md) | Complete legacy doc index |

---

## Migration status

The bilingual split (`docs/en/` + `docs/hr/`) is being introduced
incrementally. New and recently-changed features are written bilingually first;
the older guides above are still single-language English and will be migrated
over time. If a topic is missing here, check the [legacy index](../README.md).
