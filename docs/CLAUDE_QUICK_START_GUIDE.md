# Claude Quick Start Guide - Lux Tech AI Agent System

**Verzija:** 1.2
**Zadnje ažurirano:** 2026-02-07
**Autor:** Tomislav Golić + Claude

---

## 🎯 Što Je Ovaj Dokument?

Ovo je **tvoj cheat sheet** za brzo vraćanje Claude-a u kontekst projekta kada izgubim memoriju. Sadrži sve ključne informacije, arhitekturu, workflow-e, i best practices za Lux Tech AI agent sustav.

**Kada koristiti:** Na početku svake nove Claude sesije ili kada Claude izgubi context.

---

## 📋 Project Overview

### Firma & Projekt Info

**Tvrtka:** Lux tech d.o.o.
**Adresa:** Leskovački brijeg 2, 10257 Hrvatski Leskovac
**OIB:** 47034854402
**Vlasnik/Developer:** Tomislav Golić
**Email:** tomislav.luxtech@gmail.com
**Mobitel:** +385914575757

**GCP Project:** `lyrical-star-497817-m3`
**Project Name:** AI Business Assistant za fiskalizaciju 2.0
**Status:** Faza 1 COMPLETE (100%) - Full fiscalization pipeline working

### Djelatnost

- **Embedded rješenja** (Raspberry Pi, ESP32)
- **Software development**
- **AI rješenja** (multi-agent sistemi)

### Poslovni Model

**SaaS pretplata** za male obrte u Hrvatskoj (1-5 zaposlenih)
**Kritična značajka:** FINA Fiskalizacija 2.0 (mora raditi od starta)
**Platforme:** Web + Mobile + Telegram
**Cilj:** Nakon testiranja kupiti FINA licencu i prodavati sustav

---

## 🏗️ Arhitektura Sistema

### Tech Stack

```yaml
Backend:
  Framework: Google ADK (Agent Development Kit)
  Language: Python 3.13
  Models: Gemini 2.5 Pro/Flash, Gemini 2.0 Flash Exp
  Environment: PowerShell + .venv

Frontend (Planned):
  Framework: Next.js 14
  Styling: Tailwind CSS + shadcn/ui
  Deployment: Vercel

Infrastructure:
  Cloud: Google Cloud Platform
  Database: Firestore
  Storage: Cloud Storage
  Secrets: Secret Manager (planned)

APIs:
  - Google Workspace (Gmail, Drive, Calendar, Docs, Sheets, Contacts, Tasks)
  - FINA (fiskalizacija 2.0)
  - Vertex AI (LLMs)
  - Custom Search API
```

### Agent Architecture Pattern

**⚠️ CRITICAL: Koristimo AgentTool Pattern (NE sub_agents!)**

```python
# ✅ CORRECT - AgentTool Pattern (Preporučeno od Google)
from google.adk.tools import AgentTool

# Wrap worker agents as tools
agent_tools = [AgentTool(agent=agent) for agent in worker_agents]

orchestrator = create_adk_agent(
    name="smart_orchestrator",
    tools=agent_tools,           # ✅ Worker agenti kao tools
    sub_agents=[validator, ask_user],  # ✅ Samo specijalni agenti
    ...
)

# ❌ WRONG - sub_agents Pattern (Zaustavlja se rano!)
orchestrator = create_adk_agent(
    tools=[],                    # ❌ Prazno
    sub_agents=all_agents,       # ❌ Svi kao sub_agents - stops early!
    ...
)
```

**Zašto AgentTool?**
- ✅ Reliable multi-step workflow completion (izvršava SVE korake)
- ✅ Explicit result passing (svaki agent dobija info od prethodnog)
- ✅ Synchronous execution (čeka rezultat prije nastavka)
- ❌ sub_agents = LLM odlučuje kada stati → često staje prerano!

**Dokumentacija:** https://google.github.io/adk-docs/

---

## 🤖 Agenti u Sistemu

### Smart Orchestrator (Master Coordinator)

**File:** [agents/adk_agents/smart_orchestrator.py](../agents/adk_agents/smart_orchestrator.py)
**Instructions:** [agents/orchestrator/instructions.md](../agents/orchestrator/instructions.md)
**Model:** gemini-2.5-pro
**Pattern:** AgentTool (worker agenti kao tools)

**Odgovornosti:**
- Analizira user request
- Dekomponira u multi-step workflow
- Delegira na worker agente sekvencijalno
- Agregira rezultate
- Vraća complete response

**NIKAD NE:**
- Zaustavljati se nakon prvog/drugog koraka
- Koristiti sub_agents za worker agente
- Hardkodirati instrukcije (uvijek učitavati iz instructions.md)

### Worker Agenti (17 total)

| Agent | Model | Opis | Tools |
|-------|-------|------|-------|
| **researcher** | Flash | Multi-source intelligence gathering | Google Search, Scraping, YouTube |
| **scribe** | Pro | Google Docs creation/editing | Docs API, Markdown conversion |
| **secretary** | Flash | Calendar management | Calendar API, timezone handling |
| **mailer** | Flash | Gmail operations | Gmail API (send, read, search) |
| **rolodex** | Flash | Contacts management | Contacts API |
| **librarian** | Flash | Drive file management | Drive API (upload, search, share) |
| **analyst** | Flash | Sheets data analysis | Sheets API |
| **tracker** | Flash | Task tracking | Tasks API + Sheets |
| **expense** | Flash Exp | Expense tracking + OCR | Vision API, Sheets |
| **scraper** | Flash | Web scraping | BeautifulSoup, Selenium |
| **synthesizer** | Pro | Professional writing | Pure LLM, no tools |
| **marketing** | Flash | Marketing content | Imagen 3, Google Ads |
| **socrates** | Pro Preview | Philosophical dialogue | RAG knowledge base |
| **fiskalni_pripremac** | Flash | Prepare invoice data | Data validation |
| **fiskalni_validator** | Flash | Validate before send | XML/ZKI validation |
| **fiskalni_executor** | Pro | Execute FINA fiscalization | SOAP, XAdES signing |
| **fiskalizacija** | Flash | Complete fiscalization flow | execute_fiscalization, validate_oib, search_kpd, validate_kpd, calculate_tax |

### Special Agents (meta-agents, sub_agents pattern)

| Agent | Model | Opis |
|-------|-------|------|
| **decision_validator** | Flash | Conditional logic validation |
| **ask_user** | Flash | User interaction fallback |

---

## 🔐 Credentials & Authentication

### Lokalni Files (root directory)

```
google_claude/
├── service_account_key.json          # GCP service account
├── oauth_client_credentials.json     # OAuth 2.0 credentials
├── 47034854402.F1.1.p12              # FINA DEMO certifikat
├── demo2014_root_ca.pem              # FINA root CA
├── demo2020_sub_ca.pem               # FINA sub CA
├── client_cert.pem                   # mTLS client cert
├── client_key.pem                    # mTLS client key
└── .env                              # Environment variables
```

### OAuth Token Location

```
C:\Users\Tomislav\.google_workspace_adk\tokens.json
```

**⚠️ PRIJE SVAKOG RADA:**
```bash
python scripts/force_oauth_login.py
```

### Environment Variables (.env)

```bash
# Google Cloud
PROJECT_ID=lyrical-star-497817-m3
LOCATION=europe-west1

# Service Account (za Vertex AI)
GOOGLE_APPLICATION_CREDENTIALS=service_account_key.json

# OAuth (za Google Workspace APIs)
GOOGLE_OAUTH_CLIENT_CREDENTIALS=oauth_client_credentials.json

# FINA Fiskalizacija (DEMO)
FINA_CERT_PATH=47034854402.F1.1.p12
FINA_CERT_PASSWORD=NinuPiL1903
FINA_SANDBOX=true

# Human-in-the-Loop Confirmation
ENABLE_HITL=true
AUTO_APPROVE_HITL=false  # Set true for automated testing
```

### Google Cloud Services & Permissions

**Omogućeno:**
- ✅ Vertex AI (Gemini modeli)
- ✅ Firestore (database)
- ✅ Cloud Storage (PDFs)
- ✅ Cloud Logging (metrics)
- ✅ Secret Manager (planned)

**OAuth Scopes (10 total):**
- `gmail.readonly`, `gmail.send`, `gmail.modify`
- `drive`, `documents`, `spreadsheets`
- `calendar`, `contacts`, `tasks`
- `cloud-platform`

---

## 🗄️ Firestore Database

### Collections

#### 1. `fiscalization_ledger` (Index: CICAgJiUpoMK)

**Svrha:** Persistence svih fiskaliziranih računa

```javascript
{
  invoice_id: "INV-2026-001",
  oib: "47034854402",
  jir: "94450703-8e84-4c4f-94f6-4586a025ed7b",
  zki: "abc123...",
  amount: 1875.00,
  timestamp: "2026-01-29T14:30:00Z",
  pdf_path: "gs://bucket/invoices/INV-2026-001.pdf",
  status: "success"
}
```

#### 2. `fiscalization_retry_queue` (Index: CICAgJiUpoMK)

**Svrha:** Retry queue za failed fiscalization attempts

```javascript
{
  invoice_id: "INV-2026-002",
  attempt: 3,
  last_error: "s007 - Timeout",
  next_retry: "2026-01-29T15:00:00Z",
  status: "pending"
}
```

#### 3. `knowledge_base` (Index: CICAgOjXh4EK)

**Svrha:** RAG knowledge base za agente

```javascript
{
  document_id: "company-info",
  content: "Lux tech d.o.o. informacije...",
  embedding: [0.123, 0.456, ...],
  metadata: {
    type: "company_info",
    updated: "2026-01-15"
  }
}
```

---

## 📁 Project Structure

```
google_claude/
├── agents/
│   ├── adk_agents/                    # ADK agent implementations
│   │   ├── smart_orchestrator.py      # ✅ Master coordinator (AgentTool pattern)
│   │   ├── researcher_adk.py
│   │   ├── scribe_adk.py
│   │   ├── mailer_adk.py
│   │   ├── librarian_adk.py
│   │   ├── fiskalizacija_adk.py       # Complete fiscalization wrapper
│   │   ├── fiskalni_pripremac_adk.py  # Step 1: Prepare
│   │   ├── fiskalni_validator_adk.py  # Step 2: Validate
│   │   ├── fiskalni_executor_adk.py   # Step 3: Execute
│   │   └── ...                        # Other agents
│   ├── orchestrator/
│   │   └── instructions.md            # ✅ Orchestrator instructions (AgentTool pattern)
│   ├── fiskalizacija/                 # Fiskalizacija agent instructions
│   ├── researcher/
│   │   └── instructions.md
│   └── ...                            # Other agent instructions
├── tools/
│   ├── adk_tools/                     # ADK-wrapped tools
│   │   ├── gmail_adk_tools.py         # Gmail (send, search, draft, labels, attachment)
│   │   ├── drive_adk_tools.py         # Drive (upload, search, share)
│   │   ├── fiskalizacija_adk_tools.py # Fiscalization (execute, validate_oib, search_kpd, calculate_tax)
│   │   └── ...
│   └── api_implementations/           # Real API implementations
│       ├── gmail_api.py               # Gmail API (with PDF attachment support)
│       ├── drive_api.py
│       ├── fina_soap_client.py        # FINA SOAP communication
│       ├── fina_xml_builder.py        # FINA RacunZahtjev XML
│       ├── xades_signer.py            # XAdES-BES digital signing
│       ├── fiskalizacija_ledger.py    # Firestore persistence + invoice counter
│       ├── hitl_confirmation.py       # Human-in-the-Loop confirmation
│       └── ...
├── config/
│   ├── agent_registry.py              # Central agent registry (20 agents)
│   └── company_config.py              # Lux tech company info
├── data/
│   ├── kpd_2025/                      # KPD classification data
│   │   ├── kpd_catalog.json           # 5828 KPD codes (built from Excel)
│   │   ├── KPD_2025_struktura.xlsx    # Source Excel
│   │   ├── NKD_2025.json              # NKD codes
│   │   └── NKD_2025.csv
│   └── reference/                     # Reference documents
│       ├── Popis_djelatnosti.pdf
│       └── Testiranje_opis_Fiskalizacija2.0.pdf
├── docs/
│   ├── CLAUDE_QUICK_START_GUIDE.md    # ✅ THIS FILE
│   ├── DEVELOPMENT_ROADMAP.md         # ✅ Main project roadmap
│   ├── ENVIRONMENT_CONFIGURATION.md   # Environment setup guide
│   ├── CLI_WORKFLOW_GUIDE.md          # CLI usage
│   ├── FORWARD_PLAN_FEB_2026.md       # Current plan
│   └── archive/                       # Historical docs (migration reports, etc.)
├── scripts/
│   ├── force_oauth_login.py           # ✅ OAuth re-authentication
│   ├── build_kpd_catalog.py           # Build KPD JSON from Excel
│   ├── telegram_bot.py                # Telegram bot
│   └── ...
├── tests/
│   ├── fiskalizacija/                 # Fiskalizacija-specific tests
│   ├── unit/                          # Unit tests
│   ├── integration/                   # Integration tests
│   └── e2e/                           # End-to-end tests
├── main.py                            # ✅ Main CLI interface
├── requirements.txt
└── .env                               # Environment variables (NOT in git)
```

---

## 🚀 Quick Start Commands

### Prije Svakog Rada

```bash
# 1. Aktiviraj venv (ako već nije)
.venv\Scripts\activate

# 2. OAuth login (OBAVEZNO!)
python scripts/force_oauth_login.py

# 3. Pokreni sustav
python main.py
```

### Najčešći Workflow-i

#### 1. Istraživanje + Dokument + Email

```
User: "Istraži FINA fiskalizaciju 2.0, napravi dokument, pošalji na email Tomislav Golić"

Očekivani flow:
✅ Step 1: researcher(query="FINA fiskalizacija 2.0")
✅ Step 2: scribe(action="create", content=<research>)
✅ Step 3: librarian(action="save", folder="Istraživanja")
✅ Step 4: rolodex(query="Tomislav Golić")
✅ Step 5: mailer(to=<email>, body=<doc link>)
```

#### 2. Fiskalizacija Računa

```
User: "Fiskaliziraj račun za klijent XYZ, iznos 1875 EUR"

Očekivani flow:
✅ Step 1: fiskalizacija(invoice_data=...)
  - HITL confirmation (CLI preview)
  - Pripremac: Prepare data
  - Validator: Validate ZKI/XML
  - Executor: Sign + Send to FINA
  - JIR received (~400ms)
  - PDF generated with QR code
✅ Step 2: librarian(action="upload", file=<pdf>)
  - Upload to Drive
  - Return shareable link

Result: JIR + ZKI + PDF link + Drive link
```

#### 3. Kalendar + Email Reminder

```
User: "Zakaži sastanak sa klijentom sutra u 14:00, pošalji potvrdu"

Očekivani flow:
✅ Step 1: secretary(action="create_event", date="tomorrow 14:00")
✅ Step 2: mailer(action="send", to=<client>, body=<event details>)
```

---

## 🔧 Development Workflow

### Agent Development Best Practices

#### 1. Uvijek Koristi instructions.md

```python
# ✅ CORRECT - Učitavanje iz file
instruction_file = os.path.join(
    os.path.dirname(__file__),
    "..",
    "agent_name",
    "instructions.md"
)
with open(instruction_file, 'r', encoding='utf-8') as f:
    instruction = f.read()

agent = create_adk_agent(
    name="agent_name",
    instruction=instruction,
    load_instruction_from_file=False  # Already loaded above
)

# ❌ WRONG - Hardcoded instructions
agent = create_adk_agent(
    name="agent_name",
    instruction="Do something...",  # ❌ Ne hardkodirati!
)
```

#### 2. AgentTool Pattern za Orchestrator

```python
# ✅ CORRECT - Worker agenti kao tools
from google.adk.tools import AgentTool

agent_tools = []
for agent in worker_agents:
    agent_tool = AgentTool(agent=agent)
    agent_tools.append(agent_tool)

orchestrator = create_adk_agent(
    name="orchestrator",
    tools=agent_tools,  # ✅ Tools
    sub_agents=[]       # ✅ Prazno za worker agente
)

# ❌ WRONG - Svi kao sub_agents
orchestrator = create_adk_agent(
    name="orchestrator",
    tools=[],                    # ❌ Prazno
    sub_agents=all_agents        # ❌ Zaustavlja se rano!
)
```

#### 3. Datetime Context Injection

```python
from agents.adk_agents.datetime_context import inject_datetime_context

instruction = inject_datetime_context(
    instruction,
    user_timezone="Europe/Zagreb"
)
```

#### 4. Error Handling - Resilience Patterns

```python
from tools.resilience.circuit_breaker import CircuitBreaker
from tools.resilience.retry_handler import RetryHandler
from tools.resilience.rate_limiter import RateLimiter

# Circuit breaker
circuit_breaker = CircuitBreaker(service_name="fina")

# Retry with exponential backoff
@retry_handler.retry(max_attempts=3, backoff_factor=2)
def send_to_fina(xml):
    ...

# Rate limiting
rate_limiter.check("drive", cost=1)
```

---

## 🧪 Testing

### Test Commands

```bash
# Run all tests
pytest tests/

# Fiskalizacija tests only
pytest tests/fiskalizacija/

# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/
```

### Test Best Practices

1. **Prije testiranja:** `python scripts/force_oauth_login.py`
2. **Provjeri credentials:** `service_account_key.json`, `oauth_client_credentials.json`
3. **Provjeri FINA certifikat:** `47034854402.F1.1.p12`
4. **Log level:** `logging.INFO` (za debug: `logging.DEBUG`)

---

## 🐛 Common Issues & Troubleshooting

### Issue 1: "ModuleNotFoundError: No module named 'agents.adk_agents.orchestrator_adk'"

**Uzrok:** `__init__.py` pokušava importirati obrisani file

**Fix:**
```python
# Obriši iz agents/adk_agents/__init__.py:
# from .orchestrator_adk import create_orchestrator_agent  # ❌ Delete
```

### Issue 2: Multi-step workflow stops early (samo 1-2 koraka)

**Uzrok:** Koristiš sub_agents pattern umjesto AgentTool

**Fix:** Refaktoriraj na AgentTool pattern (vidi [ORCHESTRATOR_REFACTORING_COMPLETE.md](archive/ORCHESTRATOR_REFACTORING_COMPLETE.md))

### Issue 3: "The credentials do not contain the necessary fields to refresh"

**Uzrok:** Istekli OAuth tokens

**Fix:**
```bash
python scripts/force_oauth_login.py
```

### Issue 4: FINA "s006 Sistemska pogreška"

**Uzrok:** Krivi XML format (UBL 2.1 umjesto FINA RacunZahtjev)

**Fix:** Koristi `fina_xml_builder.py` (već implementirano)

### Issue 5: "429 RESOURCE_EXHAUSTED" (Google API rate limit)

**Uzrok:** Prekoračen quota

**Fix:**
- Pričekaj 5-10 minuta
- Koristi Custom Search fallback (automatski)
- Provjeri quotas u GCP Console

### Issue 6: PDF ne otvara se ili je prazan

**Uzrok:** Base64 encoding problem

**Fix:** Koristi `base64.b64decode()` prije uploada (već implementirano)

### Issue 7: KPD Search Returns Wrong Code (e.g., 95.31.11 instead of 62.10.11)

**Uzrok:** Substring matching bug - "IT" u query matchao "redov**IT**og" u 95.31.11

**Fix (06.02.2026):**
- Changed from substring to whole-word matching
- Added IT keyword boosting for IT-related queries
- Added penalty for non-IT codes when query is clearly about IT

**If User Provides KPD Code:**
```
User: "KPD kod 62.10.11 za IT usluge"
→ Use validate_kpd_code("62.10.11") FIRST (NOT search_kpd_code!)
```

### Issue 8: Fiskalizacija Not Working Through main.py Orchestrator

**Uzrok:** Fiskalizacija agent was excluded from worker agents + had no tools

**Fix (06.02.2026):**
1. Included "fiskalizacija" in worker agents (removed from exclusion list)
2. Added `execute_fiscalization` tool to fiskalizacija agent
3. Agent now has 7 tools: execute_fiscalization, get_supplier_data, generate_invoice_number, validate_oib, search_kpd_code, validate_kpd_code, calculate_tax

### Issue 9: HITL Auto-Approve Bypass (SECURITY FIX)

**Uzrok:** LLM agent (Gemini) was calling `execute_fiscalization(auto_approve_hitl=True)`, bypassing mandatory user confirmation.

**Fix (07.02.2026):**
- Removed `auto_approve_hitl` parameter from `execute_fiscalization` function signature
- HITL now ONLY checks `AUTO_APPROVE_HITL` env var (set by test scripts only)
- LLM has NO way to bypass user confirmation

### Issue 10: KPD Low Confidence Not Triggering User Confirmation

**Uzrok:** Agent found wrong KPD code (43.22, confidence 0.32) and used it without asking user.

**Fix (07.02.2026):**
- Added `user_confirmation_required` flag when confidence < 0.5
- Added `low_confidence_warning` message in tool output
- Agent now MUST present top matches to user and ask for confirmation

### Issue 11: FINA Invoice Number Format Error

**Uzrok:** Using "TEST001/1/1" instead of "1/1/1" - BrOznRac must be numeric

**Fix:** Use numeric invoice numbers: `"1/1/1"`, `"2/1/1"`, etc.
- Format: `{broj_racuna}/{oznaka_poslovnog_prostora}/{oznaka_naplatnog_uredaja}`
- All parts must be positive integers

---

## 📊 Project Status (Iz DEVELOPMENT_ROADMAP.md)

### Faze Razvoja

```
Faza 0: ████████████████████ 100% ✅ (COMPLETED 29.01.2026)
Faza 1: ████████████████████ 100% ✅ (COMPLETED 07.02.2026)
Faza 2: ░░░░░░░░░░░░░░░░░░░░   0% ⏸️ (REST API + Multi-tenant)
Faza 3: ░░░░░░░░░░░░░░░░░░░░   0% ⏸️ (Web MVP)
Faza 4: ░░░░░░░░░░░░░░░░░░░░   0% ⏸️ (Mobile App)
```

### Faza 1 Checklist (100% Complete)

- [x] JIR successfully received (✅ 29.01)
- [x] PDF generation working (✅ 31.01 - ReportLab)
- [x] QR code in PDF (✅ 31.01)
- [x] Ledger persistence to Firestore (✅ 31.01)
- [x] Idempotency check functional (✅ 31.01)
- [x] HITL confirmation integration (✅ 01.02)
- [x] Multi-agent orchestration (✅ 01.02)
- [x] Drive upload integration (✅ 01.02)
- [x] PDF quality verified (✅ 01.02)
- [x] Integration tests passing (✅ 01.02 - 3/3 PASSED)
- [x] AgentTool pattern refactoring (✅ 02.02)
- [x] KPD search + whole-word matching (✅ 06.02)
- [x] Fiskalizacija agent in orchestrator routing (✅ 06.02)
- [x] HITL mandatory enforcement - auto_approve removed from LLM control (✅ 07.02)
- [x] KPD low-confidence user confirmation (✅ 07.02)
- [x] Gmail PDF attachment support (✅ 07.02)
- [x] Invoice number auto-increment - Firestore counter (✅ 07.02)
- [x] PDV/VAT NETO-by-default rule (✅ 07.02)
- [x] Project cleanup & reorganization (✅ 07.02)

### Ključni Milestones

- ✅ 29.01.2026 - Prva uspješna fiskalizacija (JIR primljen)
- ✅ 31.01.2026 - PDF + QR + Ledger persistence
- ✅ 01.02.2026 - Multi-agent orchestration + Drive upload
- ✅ 02.02.2026 - AgentTool pattern refactoring complete
- ✅ 06.02.2026 - KPD fix + Fiskalizacija in orchestrator routing
- ✅ 07.02.2026 - HITL hardening, email attachments, invoice counter, PDV rules, cleanup
- 🎯 26.02.2026 - Target: Faza 2 complete (REST API)
- 🎯 26.03.2026 - Target: Faza 3 complete (Web MVP beta)

---

## 🎯 Current Focus (Faza 2 - REST API + Multi-tenant)

### Next Steps

**Faza 1 is COMPLETE.** Full fiscalization pipeline is working end-to-end:
- Invoice creation -> HITL confirmation -> FINA submission -> JIR -> PDF -> Drive upload -> Email with PDF attachment

**Faza 2 priorities:**
1. **REST API** - FastAPI endpoints for all agent operations
2. **Multi-tenant** - User model, JWT auth, per-user FINA certificates
3. **Cloud Run deployment** - Deploy to GCP
4. **Secret Manager** - Move certificates and credentials out of local files

---

## 🔒 Security & Compliance

### Trenutno Stanje

**✅ Implementirano:**
- OAuth 2.0 authentication
- Service account credentials
- XAdES-BES digital signing (FINA)
- mTLS (mutual TLS) za FINA komunikaciju
- Cloud Logging za audit trail

**⏸️ Planned:**
- Secret Manager za certifikate (umjesto local files)
- Certificate expiry monitoring
- Penetration testing
- GDPR compliance audit

### FINA Certifikat Status

**DEMO Certifikat (Trenutno):**
- File: `47034854402.F1.1.p12`
- Password: `NinuPiL1903` (u .env)
- URL: `https://cistest.apis-it.hr:8449/FiskalizacijaService`
- Trajanje: Do kraja Web MVP-a

**Production Certifikat (Planned):**
- Kupit će se nakon Web MVP beta testiranja
- URL: `https://cis.porezna-uprava.hr:8449/FiskalizacijaService`
- Test URL: https://sso.porezna-uprava.hr/auth/realms/ext/protocol/openid-connect/auth?client_id=f2-portal-ct-direct

---

## 💡 Best Practices & Lessons Learned

### DO ✅

1. **Uvijek učitavaj instructions.md** - Ne hardkodiraj instrukcije
2. **AgentTool pattern za orchestration** - Garantira complete workflows
3. **Run OAuth login prije rada** - `python scripts/force_oauth_login.py`
4. **Provjeri DEVELOPMENT_ROADMAP.md** - Za current status i priorities
5. **Test lokalno prije deploy-a** - Koristi demo certifikat
6. **Inject datetime context** - Za temporalne operacije (calendar, deadlines)
7. **Use resilience patterns** - Circuit breaker, retry, rate limiting
8. **Log sve FINA operacije** - Audit trail je kritičan

### DON'T ❌

1. **Nikad hardkodiraj credentials** - Koristi .env ili Secret Manager
2. **Nikad koristi sub_agents za worker agente** - Zaustavlja se rano!
3. **Ne commitaj .env ili credentials** - .gitignore ih!
4. **Ne skipaj OAuth login** - Stari tokens ne rade
5. **Ne deployaj bez testiranja** - Demo certifikat je tu za to
6. **Ne ignoriraj API rate limits** - 429 errors = pričekaj
7. **Ne mijenjaj agent_registry bez razloga** - Centralno mjesto za sve agente

---

## 📞 Contact & Support

**Developer:** Tomislav Golić
**Email:** tomislav.luxtech@gmail.com
**Mobitel:** +385914575757
**Firma:** Lux tech d.o.o.

**Dokumentacija:**
- Google ADK: https://google.github.io/adk-docs/
- FINA Fiskalizacija: https://www.fina.hr/fiskalizacija
- GCP Project: lyrical-star-497817-m3

---

## 🔄 Version History

**v1.2 (07.02.2026) - Faza 1 Complete + Security Hardening:**
- **HITL Mandatory Enforcement:** Removed `auto_approve_hitl` param from LLM control
- **KPD Low-Confidence Check:** Agent must ask user when confidence < 0.5
- **Gmail PDF Attachment:** `gmail_send_message` now supports `attachment_path` for attaching PDFs
- **Invoice Number Auto-Increment:** Firestore atomic counter per supplier/business_unit/device/year
- **PDV/VAT NETO Default Rule:** User amounts always treated as NETO unless explicitly stated bruto
- **QR Code Fix:** Proper JIR-based verification URL in PDF
- **Gmail Threading Fix:** Reply threading works correctly
- **Project Cleanup:** Reorganized folder structure, moved data files, archived old docs
- **Faza 1 marked 100% COMPLETE**

**v1.1 (06.02.2026) - KPD & Orchestrator Fixes:**
- KPD Search Bug Fixed: Changed from substring matching to whole-word matching
- New Tool: `validate_kpd_code()` - For user-provided KPD codes
- Fiskalizacija in Worker Agents: Now included in smart_orchestrator routing
- New Tool: `execute_fiscalization()` - Main entry point for complete fiscalization
- FINA Certificate in .env: Added `FINA_CERT_PATH`, `FINA_CERT_PASSWORD`, `FINA_SANDBOX`

**v1.0 (02.02.2026):**
- Initial version
- AgentTool pattern refactoring documented
- Faza 1 status (90% complete)

---

## 📚 Related Documents

| Dokument | Svrha |
|----------|-------|
| [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) | Main project roadmap, faze razvoja |
| [FORWARD_PLAN_FEB_2026.md](FORWARD_PLAN_FEB_2026.md) | Current forward plan |
| [ENVIRONMENT_CONFIGURATION.md](ENVIRONMENT_CONFIGURATION.md) | Environment setup guide |
| [multi_agent_workflows.md](multi_agent_workflows.md) | Complete guide za multi-agent patterns |
| [orchestrator_workflow_examples.md](orchestrator_workflow_examples.md) | Orchestrator workflow examples |
| [agents/orchestrator/instructions.md](../agents/orchestrator/instructions.md) | Orchestrator instrukcije (AgentTool pattern) |

---

**🎯 Koristi ovaj dokument svaki put kada Claude izgubi context ili počinješ novu sesiju!**

**Zadnje ažurirano:** 2026-02-07 (Faza 1 complete, project cleanup, security hardening)
