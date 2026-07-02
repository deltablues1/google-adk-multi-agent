# LLM Providers: Gemini & Claude

> 🇭🇷 Hrvatska verzija: [docs/hr/llm-providers.md](../hr/llm-providers.md)

The system runs on **Gemini via Vertex AI by default**, but agents can be routed
to **Anthropic Claude** through [LiteLLM](https://docs.litellm.ai/) with a single
environment switch. Provider selection is per-agent and fully configurable.

Source of truth: [`agents/adk_agents/adk_agent_factory.py`](../../agents/adk_agents/adk_agent_factory.py)
and the `.env.example` `LLM provider routing` block.

---

## Quick switch

```bash
# Default — everything on Gemini (Vertex AI)
LLM_PROVIDER=gemini

# Route eligible agents to Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Requirements for Claude: `pip install litellm` and a valid `ANTHROPIC_API_KEY`.
If LiteLLM or the key is unavailable at runtime, the factory **logs a warning and
falls back to Gemini** for that agent — it does not crash.

---

## How an agent's model is chosen

When `LLM_PROVIDER=anthropic`, each agent resolves its Claude model in this
priority order (`_claude_model_for`):

1. **Per-agent override** — `CLAUDE_AGENT_MODELS` (wins over everything).
2. **Content/reasoning workers** → `CLAUDE_PRO_MODEL`. These are the agents that
   produce substantial output (analyst, mailer, researcher, scribe, marketing,
   synthesizer, expense).
3. **Glue / routing agents** → cheap tier map below (orchestrator, planner,
   summarizer, secretary, tracker, rolodex, librarian, scraper, voice_qa, ...).

### Gemini tier → Claude tier mapping

| Env var | Default | Used for |
|---------|---------|----------|
| `CLAUDE_PRO_MODEL` | `claude-sonnet-5` | Content/reasoning workers, Pro-tier agents |
| `CLAUDE_FLASH_MODEL` | `claude-sonnet-5` | Flash-tier (default speed) agents |
| `CLAUDE_LITE_MODEL` | `claude-sonnet-5` | Lite-tier agents |

> **Sonnet 5 notes:** adaptive thinking is on by default (we leave it on for
> answer quality). Sonnet 5 rejects non-default sampling params, so the agent
> factory drops `temperature` and raises small `max_output_tokens` caps to
> 4096 (thinking tokens count against the cap). Roll back any time with
> `CLAUDE_*_MODEL=claude-sonnet-4-6`.

### Per-agent overrides

```bash
# Comma-separated agent=model pairs; this beats every default above
CLAUDE_AGENT_MODELS=mailer=claude-opus-4-8,researcher=claude-sonnet-4-6
```

> Model IDs (latest Claude): Opus 4.8 `claude-opus-4-8`, Sonnet 5
> `claude-sonnet-5`, Sonnet 4.6 `claude-sonnet-4-6`, Haiku 4.5
> `claude-haiku-4-5`. Fable 5 `claude-fable-5`.

---

## Agents pinned to Gemini

Some agents depend on Vertex-only features (e.g. Vertex AI RAG corpora) and stay
on Gemini regardless of `LLM_PROVIDER`:

- **Always pinned:** `socrates`, `christian_guide`.
- **Add your own:** `CLAUDE_GEMINI_ONLY_AGENTS=researcher,scraper`

---

## Prompt caching (Anthropic)

The large, static agent instruction blocks are cached so repeated calls do not
re-send (and re-bill) the full system prompt at the base input rate.

```bash
CLAUDE_PROMPT_CACHE=true   # default on
```

Implementation notes (from the migration commits):

- The patch normalizes the system role and is **async-aware** and
  **arity-agnostic** — this was the actual fix for `cached=0`.
- Cache-read input tokens bill at roughly **0.1×** the base input price. The
  cost estimate credits this (see [Token Accounting](token-accounting.md)).
- First-call cache-write premium (~1.25×) is not separately tracked, so the cost
  figure is a close approximation, not exact billing.

---

## Retries

Anthropic 429 (rate limit) and 5xx errors are retried with exponential backoff
via LiteLLM's `num_retries`:

```bash
CLAUDE_RETRY_ATTEMPTS=4   # default
```

This helps with burst rate-limits during multi-agent runs. (Gemini/Vertex 429s
are handled separately by the resilience retry layer.)

---

## Environment reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `gemini` | `gemini` or `anthropic` |
| `ANTHROPIC_API_KEY` | — | Required when `anthropic` |
| `CLAUDE_PRO_MODEL` | `claude-sonnet-5` | Pro/content tier |
| `CLAUDE_FLASH_MODEL` | `claude-sonnet-5` | Flash tier |
| `CLAUDE_LITE_MODEL` | `claude-sonnet-5` | Lite tier |
| `CLAUDE_AGENT_MODELS` | — | Per-agent overrides |
| `CLAUDE_GEMINI_ONLY_AGENTS` | — | Extra agents pinned to Gemini |
| `CLAUDE_PROMPT_CACHE` | `true` | Cache static instructions |
| `CLAUDE_RETRY_ATTEMPTS` | `4` | LiteLLM `num_retries` |

See also: [Token Accounting & Cost](token-accounting.md) for comparing Gemini vs
Claude spend apples-to-apples.
