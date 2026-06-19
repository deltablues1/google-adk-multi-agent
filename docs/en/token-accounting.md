# Token Accounting & Cost

> 🇭🇷 Hrvatska verzija: [docs/hr/token-accounting.md](../hr/token-accounting.md)

Per-agent LLM token accounting answers the question *"where do the tokens go?"*
before you decide anything about models or providers. It is provider-agnostic:
the same counters compare Gemini today against Claude/GPT later, apples-to-apples.

Source of truth: [`tools/observability/token_stats.py`](../../tools/observability/token_stats.py).

---

## What it records

Fed from ADK's framework-level `after_model_callback`, so it fires for **every**
model call regardless of provider. Per agent and per model it tracks:

- `calls` — number of model calls
- `in` — prompt (input) tokens
- `out` — output tokens
- `cached` — cache-read input tokens
- `~$` — derived cost estimate (see below)

Storage is pure in-memory and process-local — it survives only for the life of
the running service (perfect for a measurement session).

```bash
TOKEN_STATS_ENABLED=true   # default on; set false to disable
```

---

## Reading the numbers

### Automatic per-turn log

After every request turn, a slice report is written to the logs:

```
[TOKENS]
TOKEN USAGE (turn) user=...
agent             model                 calls       in     out  cached       ~$
analyst           claude-sonnet-4-6         3     8120     740    7600   0.0231
orchestrator      gemini-2.5-flash          1     1450      90       0   0.0007
TOTAL                                       4     9570     830    7600   0.0238
```

### `/tokens` command (Telegram)

Telegram exposes a `/tokens` command for **cumulative** usage since startup:

- `/tokens` — print the cumulative per-agent report
- `/tokens reset` — clear all recorded counts

(In the CLI/web flows the per-turn report is emitted to the logs automatically.)

---

## How cost is estimated

Cost is **derived, not measured**. Token counts are exact; the price table is a
convenience overlay in `token_stats.py` (`PRICES`):

- **Gemini** values are *approximate* — edit them to match your actual Vertex
  pricing.
- **Claude** values are public list price ($/1M tokens).

The cost formula credits cache reads:

```
uncached   = max(prompt - cached, 0)
input_cost = uncached * input_price
           + cached   * input_price * CACHE_READ_RATE   # default 0.1
cost       = (input_cost + output * output_price) / 1e6
```

```bash
CACHE_READ_RATE=0.1   # cache-read tokens bill at ~0.1x base input (Anthropic)
```

> Caveat: the first-call cache-write premium (~1.25×) is not separately tracked,
> so `~$` is a close approximation, not an invoice. If a model has no price-table
> entry, its cost shows as `n/a`.

### Current price table (per 1M tokens: input, output)

| Model substring | Input | Output |
|-----------------|-------|--------|
| `gemini-2.5-flash` / `gemini-3.5-flash` | 0.30 | 2.50 |
| `gemini-3.1-flash-lite` | 0.10 | 0.40 |
| `gemini-2.5-pro` / `gemini-3.x-pro` | 1.25 | 10.00 |
| `claude-opus` | 5.00 | 25.00 |
| `claude-sonnet` | 3.00 | 15.00 |
| `claude-haiku` | 1.00 | 5.00 |

Matching is by substring, so `claude-sonnet-4-6` matches the `claude-sonnet` row.

---

## Why this exists

It was built as the measurement layer for the Gemini → Claude migration: before
swapping providers you can see exactly which agents dominate spend, then use
[per-agent model routing](llm-providers.md#per-agent-overrides) to put the
expensive ones on a cheaper tier.
