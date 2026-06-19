# Brojanje tokena i trošak

> 🇬🇧 English version: [docs/en/token-accounting.md](../en/token-accounting.md)

Brojanje LLM tokena po agentu odgovara na pitanje *"kamo odlaze tokeni?"* prije
nego išta odlučiš o modelima ili providerima. Neovisno je o provideru: isti
brojači uspoređuju Gemini danas s Claudeom/GPT-om kasnije, na istim osnovama.

Izvor istine: [`tools/observability/token_stats.py`](../../tools/observability/token_stats.py).

---

## Što bilježi

Hrani se iz ADK callbacka na razini frameworka (`after_model_callback`), pa se
okida za **svaki** poziv modela bez obzira na providera. Po agentu i po modelu
prati:

- `calls` — broj poziva modela
- `in` — ulazni (prompt) tokeni
- `out` — izlazni tokeni
- `cached` — cache-read ulazni tokeni
- `~$` — izvedena procjena troška (vidi dolje)

Pohrana je isključivo u memoriji i lokalna procesu — traje samo dok servis radi
(idealno za mjernu sesiju).

```bash
TOKEN_STATS_ENABLED=true   # zadano uključeno; postavi false za isključenje
```

---

## Čitanje brojeva

### Automatski zapis po potezu (turn)

Nakon svakog poteza zahtjeva, izvještaj za taj isječak upisuje se u logove:

```
[TOKENS]
TOKEN USAGE (turn) user=...
agent             model                 calls       in     out  cached       ~$
analyst           claude-sonnet-4-6         3     8120     740    7600   0.0231
orchestrator      gemini-2.5-flash          1     1450      90       0   0.0007
TOTAL                                       4     9570     830    7600   0.0238
```

### `/tokens` komanda (Telegram)

Telegram nudi `/tokens` komandu za **kumulativnu** potrošnju od pokretanja:

- `/tokens` — ispiši kumulativni izvještaj po agentu
- `/tokens reset` — obriši sve zabilježene brojeve

(U CLI/web tokovima izvještaj po potezu automatski ide u logove.)

---

## Kako se procjenjuje trošak

Trošak je **izveden, ne izmjeren**. Brojevi tokena su točni; tablica cijena je
pomoćni sloj u `token_stats.py` (`PRICES`):

- **Gemini** vrijednosti su *približne* — uredi ih da odgovaraju tvojoj stvarnoj
  Vertex cijeni.
- **Claude** vrijednosti su javna kataloška cijena ($/1M tokena).

Formula troška priznaje cache-read:

```
uncached   = max(prompt - cached, 0)
input_cost = uncached * ulazna_cijena
           + cached   * ulazna_cijena * CACHE_READ_RATE   # zadano 0.1
cost       = (input_cost + output * izlazna_cijena) / 1e6
```

```bash
CACHE_READ_RATE=0.1   # cache-read tokeni ~0.1x osnovne ulazne cijene (Anthropic)
```

> Ograničenje: premija prvog poziva za upis u cache (~1.25×) ne prati se zasebno,
> pa je `~$` bliska aproksimacija, a ne račun. Ako model nema unos u tablici
> cijena, trošak se prikazuje kao `n/a`.

### Trenutna tablica cijena (po 1M tokena: ulaz, izlaz)

| Dio naziva modela | Ulaz | Izlaz |
|-------------------|------|-------|
| `gemini-2.5-flash` / `gemini-3.5-flash` | 0.30 | 2.50 |
| `gemini-3.1-flash-lite` | 0.10 | 0.40 |
| `gemini-2.5-pro` / `gemini-3.x-pro` | 1.25 | 10.00 |
| `claude-opus` | 5.00 | 25.00 |
| `claude-sonnet` | 3.00 | 15.00 |
| `claude-haiku` | 1.00 | 5.00 |

Podudaranje je po dijelu naziva, pa `claude-sonnet-4-6` odgovara retku
`claude-sonnet`.

---

## Zašto ovo postoji

Izgrađeno je kao mjerni sloj za migraciju Gemini → Claude: prije zamjene
providera možeš točno vidjeti koji agenti dominiraju troškom, a zatim
[usmjeravanjem modela po agentu](llm-providers.md#override-po-agentu) staviti
skupe na jeftiniju razinu.
