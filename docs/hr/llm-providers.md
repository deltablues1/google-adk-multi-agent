# LLM provideri: Gemini i Claude

> 🇬🇧 English version: [docs/en/llm-providers.md](../en/llm-providers.md)

Sustav po zadanome radi na **Geminiju preko Vertex AI-a**, ali agenti se mogu
usmjeriti na **Anthropic Claude** preko [LiteLLM-a](https://docs.litellm.ai/)
jednim prekidačem u okruženju. Odabir providera je po agentu i potpuno
podesiv.

Izvor istine: [`agents/adk_agents/adk_agent_factory.py`](../../agents/adk_agents/adk_agent_factory.py)
i `LLM provider routing` blok u `.env.example`.

---

## Brzo prebacivanje

```bash
# Zadano — sve na Geminiju (Vertex AI)
LLM_PROVIDER=gemini

# Usmjeri prihvatljive agente na Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Preduvjeti za Claude: `pip install litellm` i valjan `ANTHROPIC_API_KEY`. Ako
LiteLLM ili ključ nisu dostupni u radu, tvornica (factory) **zapiše upozorenje i
vrati se na Gemini** za taj agent — ne ruši se.

---

## Kako se bira model agenta

Kad je `LLM_PROVIDER=anthropic`, svaki agent razrješava svoj Claude model ovim
redoslijedom prioriteta (`_claude_model_for`):

1. **Override po agentu** — `CLAUDE_AGENT_MODELS` (jači od svega).
2. **Sadržajni / rezonirajući radnici** → `CLAUDE_PRO_MODEL`. To su agenti koji
   proizvode opsežniji izlaz (analyst, mailer, researcher, scribe, marketing,
   synthesizer, expense).
3. **Vezivni / usmjeravajući agenti** → jeftina mapa razina ispod (orchestrator,
   planner, summarizer, secretary, tracker, rolodex, librarian, scraper,
   voice_qa, ...).

### Mapiranje Gemini razina → Claude razina

| Env varijabla | Zadano | Koristi se za |
|---------------|--------|---------------|
| `CLAUDE_PRO_MODEL` | `claude-sonnet-4-6` | Sadržajni radnici, agenti Pro razine |
| `CLAUDE_FLASH_MODEL` | `claude-haiku-4-5` | Agenti Flash razine (zadana brzina) |
| `CLAUDE_LITE_MODEL` | `claude-haiku-4-5` | Agenti Lite razine |

### Override po agentu

```bash
# Parovi agent=model odvojeni zarezom; jači od svih zadanih vrijednosti gore
CLAUDE_AGENT_MODELS=mailer=claude-opus-4-8,researcher=claude-sonnet-4-6
```

> ID-ovi modela (najnoviji Claude): Opus 4.8 `claude-opus-4-8`, Sonnet 4.6
> `claude-sonnet-4-6`, Haiku 4.5 `claude-haiku-4-5`. Fable 5 `claude-fable-5`.

---

## Agenti zakovani na Gemini

Neki agenti ovise o značajkama dostupnim samo na Vertexu (npr. Vertex AI RAG
korpusi) pa ostaju na Geminiju bez obzira na `LLM_PROVIDER`:

- **Uvijek zakovani:** `socrates`, `christian_guide`.
- **Dodaj svoje:** `CLAUDE_GEMINI_ONLY_AGENTS=researcher,scraper`

---

## Prompt caching (Anthropic)

Veliki, statični blokovi uputa agenata spremaju se u cache pa ponovljeni pozivi
ne šalju (i ne naplaćuju) cijeli sistemski prompt po osnovnoj ulaznoj cijeni.

```bash
CLAUDE_PROMPT_CACHE=true   # zadano uključeno
```

Napomene o implementaciji (iz commitova migracije):

- Patch normalizira system ulogu te je **async-aware** i **neovisan o broju
  argumenata (arity-agnostic)** — to je bio stvarni popravak za `cached=0`.
- Cache-read ulazni tokeni naplaćuju se otprilike **0.1×** osnovne ulazne cijene.
  Procjena troška to priznaje (vidi [Brojanje tokena](token-accounting.md)).
- Premija prvog poziva za upis u cache (~1.25×) ne prati se zasebno, pa je iznos
  troška bliska aproksimacija, a ne točna naplata.

---

## Ponovni pokušaji (retries)

Anthropic 429 (rate limit) i 5xx greške ponovno se pokušavaju s eksponencijalnim
povećanjem razmaka preko LiteLLM-ovog `num_retries`:

```bash
CLAUDE_RETRY_ATTEMPTS=4   # zadano
```

Pomaže kod naglih rate-limita tijekom višeagentnih izvođenja. (Gemini/Vertex
429-ice rješava zasebno resilience retry sloj.)

---

## Referenca okruženja

| Varijabla | Zadano | Svrha |
|-----------|--------|-------|
| `LLM_PROVIDER` | `gemini` | `gemini` ili `anthropic` |
| `ANTHROPIC_API_KEY` | — | Obavezno kad je `anthropic` |
| `CLAUDE_PRO_MODEL` | `claude-sonnet-4-6` | Pro/sadržajna razina |
| `CLAUDE_FLASH_MODEL` | `claude-haiku-4-5` | Flash razina |
| `CLAUDE_LITE_MODEL` | `claude-haiku-4-5` | Lite razina |
| `CLAUDE_AGENT_MODELS` | — | Overrideovi po agentu |
| `CLAUDE_GEMINI_ONLY_AGENTS` | — | Dodatni agenti zakovani na Gemini |
| `CLAUDE_PROMPT_CACHE` | `true` | Cache statičnih uputa |
| `CLAUDE_RETRY_ATTEMPTS` | `4` | LiteLLM `num_retries` |

Vidi i: [Brojanje tokena i trošak](token-accounting.md) za usporedbu potrošnje
Gemini vs Claude na istim osnovama.
