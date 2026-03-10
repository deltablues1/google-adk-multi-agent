# 🧪 KOMPLETNA TEST SUITE - Izvršavanje Svih Testova

Kompletni vodič za pokretanje SVIH testova u pravom redoslijedu.

---

## 🎯 PRIJE TESTIRANJA

### 1. Aktiviraj Virtual Environment

**Windows:**
```bash
cd "C:\Users\Tomislav\Desktop\ai agenti\google github claude\google_claude"
.venv\Scripts\activate
```

**Linux/Mac:**
```bash
cd ~/google_claude
source .venv/bin/activate
```

### 2. Provjeri .env File

```bash
# Provjeri da .env postoji
ls -la .env

# Minimalno potrebno u .env:
# GOOGLE_API_KEY=your-api-key-here
# GEMINI_MODEL_FLASH=gemini-1.5-flash
# GEMINI_MODEL_PRO=gemini-1.5-pro
```

---

## 📊 TEST SUITE - TIER 1: FOUNDATION TESTS

### Test 1.1: Dostupni Gemini Modeli ⭐ ZAPOČNI OVDJE

```bash
python test_available_models.py
```

**Što testira:**
- Koje Gemini modele možeš koristiti s tvojim API keyem
- Lista svih dostupnih modela
- Preporuke za FLASH i PRO modele

**Očekivani rezultat:**
```
✅ gemini-1.5-flash: RADI
✅ gemini-1.5-pro: RADI

PREPORUKA za tvoj sustav:
  FLASH model: gemini-1.5-flash
  PRO model: gemini-1.5-pro
```

**Trajanje:** ~30 sekundi

---

### Test 1.2: Vertex AI & LLM Model Test

```bash
python test_vertex_ai_model.py
```

**Što testira:**
- Google API Key poziv
- Vertex AI poziv (ako je konfiguriran)
- BaseAgent s pravim LLM modelom
- Orchestrator s pravim LLM modelom

**Očekivani rezultat:**
```
✅ PASS: google_api_key
✅ PASS: base_agent
✅ PASS: orchestrator

✅ LLM MODEL RADI!
```

**Trajanje:** ~20 sekundi

---

### Test 1.3: System Integration Test

```bash
python test_real_system.py
```

**Što testira:**
- Environment konfiguracija
- Agent registry (10 agenata)
- Agent inicijalizacija
- Autentifikacija
- Agent availability
- Routing logika

**Očekivani rezultat:**
```
✓ Passed: 6/7
Success rate: 85.7%

✓✓✓ SYSTEM READY FOR USE! ✓✓✓
```

**Trajanje:** ~10 sekundi

---

## 📊 TEST SUITE - TIER 2: ADVANCED FEATURES

### Test 2.1: LLM-Based Routing ⭐ NOVA IMPLEMENTACIJA

```bash
python test_llm_routing.py
```

**Što testira:**
- LLM-based routing decisions (ne keyword matching!)
- 15+ različitih scenarija
- Email, Drive, Docs, Sheets, Calendar, Contacts, Tasks operacije
- Research i Scraping operacije
- General knowledge pitanja
- Multi-step operacije

**Očekivani rezultat:**
```
Total tests: 15
✅ Passed: 13
❌ Failed: 2
Success rate: 86.7%

✅✅✅ LLM-BASED ROUTING WORKS EXCELLENT! ✅✅✅
```

**Trajanje:** ~2 minute (zbog API rate limiting)

**NAPOMENA:** Ovo je KLJUČNI test koji pokazuje da routing sada koristi LLM, ne keyword matching!

---

### Test 2.2: Real API Call Simulation

```bash
python test_real_api_calls.py
```

**Što testira:**
- **Phase 1:** READ operacije (safe)
  - List emails
  - List Drive files
  - List calendar events
  - List contacts
  - List tasks

- **Phase 2:** Complex multi-agent scenarios
  - Find contact + compose email
  - Search emails + check Drive
  - Calendar summary → Doc

- **Phase 3:** WRITE operacije (careful!)
  - Send email
  - Create Google Doc
  - Update contact

**Očekivani rezultat:**
```
PHASE 1: Simple Read Operations
  ✅ List Emails - Routing successful
  ✅ List Drive Files - Routing successful
  ...

Success Rate: 100%

✅ SYSTEM ROUTING WORKS PERFECTLY!
```

**Trajanje:** ~1 minut

**NAPOMENA:** Ovaj test sada koristi STVARNI LLM routing i IZVRŠAVA agent.run() metode!

---

## 📊 TEST SUITE - TIER 3: INTEGRATION & E2E

### Test 3.1: Pytest Integration Tests

```bash
# Svi integration testovi
pytest tests/integration/ -v

# Samo test_real_agents.py (provjerava sve agente)
pytest tests/integration/test_real_agents.py -v

# Unit testovi
pytest tests/unit/ -v
```

**Što testira:**
- Sve agent klase
- Instruction files
- Tool assignments
- Registry validation
- Auth managere
- Monitoring

**Očekivani rezultat:**
```
tests/integration/test_real_agents.py::TestBaseAgent::test_base_agent_initialization PASSED
tests/integration/test_real_agents.py::TestOrchestratorAgent::test_orchestrator_initialization PASSED
...

====== 50 passed in 10.23s ======
```

**Trajanje:** ~10-15 sekundi

---

### Test 3.2: E2E User Workflows

```bash
pytest tests/e2e/test_real_user_workflows.py -v
```

**Što testira:**
- Puni user journey
- Real-world scenariji
- Multi-step workflows

**Trajanje:** ~20 sekundi

---

## 🎮 INTERAKTIVNI MOD - Manual Testing

```bash
python main.py
```

**Testni upiti:**

### 1. General Knowledge (Orchestrator sam odgovara)
```
You: Što je Python programski jezik?
```

**Očekivani routing:** `agent: self`

### 2. Email Operacija (→ Mailer)
```
You: Pošalji email tgolic555@gmail.com s naslovom 'Test'
```

**Očekivani routing:** `agent: mailer`

### 3. Drive Operacija (→ Librarian)
```
You: Pronađi sve PDF datoteke u mom Google Drive
```

**Očekivani routing:** `agent: librarian`

### 4. Calendar Operacija (→ Secretary)
```
You: Prikaži moje događaje za danas
```

**Očekivani routing:** `agent: secretary`

### 5. Složeni Multi-Step
```
You: Pronađi emailove od prošlog tjedna i kreiraj summary dokument
```

**Očekivani routing:** LLM će odlučiti (može biti `mailer`, `scribe`, ili `self`)

---

## 📈 KOMPLETNI TEST PROTOKOL

```bash
# 1. Foundation tests (5 minuta)
python test_available_models.py
python test_vertex_ai_model.py
python test_real_system.py

# 2. Advanced features (3 minute)
python test_llm_routing.py
python test_real_api_calls.py

# 3. Integration tests (15 sekundi)
pytest tests/integration/ -v

# 4. E2E tests (20 sekundi)
pytest tests/e2e/ -v

# 5. Manual testing
python main.py
```

**Ukupno vrijeme:** ~10 minuta

---

## ✅ SUCCESS CRITERIA

### Tier 1: FOUNDATION (Must Pass)
- ✅ test_available_models.py: Pronađe barem 2 modela (flash i pro)
- ✅ test_vertex_ai_model.py: Svi testovi pass (osim Vertex AI ako nije konfiguriran)
- ✅ test_real_system.py: Success rate >= 80%

### Tier 2: ADVANCED (Must Pass)
- ✅ test_llm_routing.py: Success rate >= 75% ⭐ KEY TEST
- ✅ test_real_api_calls.py: Success rate >= 90%

### Tier 3: INTEGRATION (Should Pass)
- ✅ pytest tests/integration/: >= 90% pass rate
- ✅ pytest tests/e2e/: >= 80% pass rate

### Manual Testing (Validation)
- ✅ main.py se pokreće bez errora
- ✅ Orchestrator učitava sve agente (10 total)
- ✅ LLM odgovara na upite
- ✅ Routing radi korektno

---

## 🔧 TROUBLESHOOTING

### Problem: "ImportError: No module named X"

```bash
pip install -r requirements.txt
```

### Problem: "GOOGLE_API_KEY not found"

1. Provjeri .env:
   ```bash
   cat .env | grep GOOGLE_API_KEY
   ```

2. Dodaj key:
   ```bash
   echo "GOOGLE_API_KEY=tvoj-key" >> .env
   ```

### Problem: Test timeout

- Gemini API može biti spor
- Povećaj timeout u testu
- Provjeri internet konekciju

### Problem: LLM routing vraća krivi agent

- To je OK ako je < 20% testova
- LLM može imati different interpretation
- Važno je da routing KORISTI LLM, ne keywords

---

## 📊 TRENUTNO STANJE - ŠTO JE IMPLEMENTIRANO

### ✅ IMPLEMENTIRANO I RADI

1. **LLM-Based Routing** (agents/orchestrator/orchestrator.py:135-276)
   - ✅ Koristi Gemini model za routing odluke
   - ✅ Fallback na keyword-based routing
   - ✅ JSON parsing i validacija
   - ✅ Agent existence check

2. **Tool Calling Execution Loop** (agents/base_agent.py:134-265)
   - ✅ Multi-turn conversation history
   - ✅ Tool execution loop (max 5 iterations)
   - ✅ Function call detection
   - ✅ Function response handling
   - ✅ Error handling za tool failures

3. **Test Suite**
   - ✅ test_available_models.py - Provjera dostupnih modela
   - ✅ test_vertex_ai_model.py - LLM model test
   - ✅ test_real_system.py - System integration
   - ✅ test_llm_routing.py - LLM routing validation
   - ✅ test_real_api_calls.py - Updated za async routing

### ⚠️ DJELOMIČNO IMPLEMENTIRANO

1. **Tool Execution** (_execute_tool metoda)
   - ⚠️ Placeholder implementacija
   - ⚠️ Vraća mock result
   - 📋 TODO: Implementirati stvarne tool pozive

2. **MCP Tool Integration**
   - ⚠️ MCP toolsets definirani
   - ⚠️ Nisu povezani s _execute_tool metodom
   - 📋 TODO: Dynamic tool registry

### ❌ NIJE IMPLEMENTIRANO

1. **OAuth Flow za API Pozive**
   - ❌ OAuth authentication flow
   - ❌ Token storage i refresh
   - 📋 TODO: Implementirati u auth modulu

2. **Stvarni Google API Pozivi**
   - ❌ Gmail API pozivi
   - ❌ Drive API pozivi
   - ❌ Calendar API pozivi
   - 📋 TODO: Nakon OAuth implementacije

---

## 🎯 SLJEDEĆI KORACI

Nakon što svi Tier 1 i Tier 2 testovi prođu:

1. **Implementirati Tool Execution**
   - Povezati MCP toolsets s _execute_tool metodom
   - Dynamic tool registry
   - Tool validation

2. **Implementirati OAuth Flow**
   - OAuth 2.0 authentication
   - Token storage
   - Token refresh

3. **Testirati s Pravim API Pozivima**
   - Configure OAuth credentials
   - Test Gmail API
   - Test Drive API
   - Test Calendar API

4. **Production Deployment**
   - Vertex AI integration
   - Error handling improvements
   - Monitoring i logging
   - Rate limiting

---

**Kreirao:** Claude Code
**Datum:** 2025-11-25
**Verzija:** 2.0 (s LLM routing i tool calling)
