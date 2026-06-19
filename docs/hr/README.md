# Dokumentacija (hrvatski)

> 🇬🇧 English version: [docs/en/README.md](../en/README.md)

Dvojezična dokumentacija za Google ADK višeagentni sustav. Ova `hr/` mapa
sadrži hrvatske verzije; zrcalne datoteke nalaze se u `docs/en/`.

---

## Što se nedavno promijenilo

Ove značajke dodane su u kod, ali dosad nisu bile dokumentirane. Počni ovdje
ako pratiš zadnje izmjene:

| Tema | Opis |
|------|------|
| [LLM provideri (Gemini / Claude)](llm-providers.md) | `LLM_PROVIDER` prekidač, usmjeravanje agenata na Claude preko LiteLLM-a, prompt caching, ponovni pokušaji |
| [Brojanje tokena i trošak](token-accounting.md) | Statistika tokena po agentu, `/tokens` komanda, procjena troška s priznavanjem cache-read tokena |
| [Glas (Gemini i OpenAI)](voice.md) | STT/TTS motori, prebacivanje na OpenAI glas, ugađanje glasovnog runtimea |

---

## Glavni vodiči (postojeći, engleski)

Ovi postojeći dokumenti i dalje vrijede te su povezani odavde dok se ne
prebace u dvojezičnu strukturu:

| Vodič | Opis |
|-------|------|
| [Glavni README](../../README.md) | Pregled projekta i brzi početak |
| [Setup Guide](../guides/SETUP_GUIDE.md) | Početno postavljanje i konfiguracija |
| [Environment Configuration](../ENVIRONMENT_CONFIGURATION.md) | Referenca varijabli okruženja |
| [Deployment Guide](../guides/DEPLOYMENT_GUIDE.md) | Produkcijski deployment |
| [System Architecture 2.0](../architecture/SYSTEM_ARCHITECTURE_2.0.md) | Tehnička arhitektura |
| [Resilience Stack](../implementation/COMPLETE_RESILIENCE_STACK_SUMMARY.md) | Circuit breaker, rate limit, retry, cache |
| [Multi-Agent Workflows](../multi_agent_workflows.md) | Primjeri složenih tokova rada |
| [ADK Reference](../ADK_REFERENCE.md) | Google ADK obrasci |
| [Potpuni indeks dokumentacije](../README.md) | Cijeli (postojeći) indeks |

---

## Status migracije

Dvojezična podjela (`docs/en/` + `docs/hr/`) uvodi se postupno. Nove i nedavno
izmijenjene značajke pišu se prvo dvojezično; stariji vodiči iznad još su
jednojezični (engleski) i bit će prebačeni s vremenom. Ako tema ovdje
nedostaje, pogledaj [postojeći indeks](../README.md).
