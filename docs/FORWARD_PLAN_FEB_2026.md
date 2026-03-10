# Forward Plan - Veljača 2026

**Datum:** 31.01.2026
**Status:** Faza 1 - 60% completed (ahead of schedule!)
**Fokus:** Završiti Fazu 1 (Stabilizacija), pripremiti Fazu 2 (REST API)

---

## Trenutno Stanje ✅

### Što je Završeno (Dan 1-3, Tjedan 3)

| Komponenta | Status | Datum | Napomena |
|------------|--------|-------|----------|
| PDF Generiranje | ✅ 100% | 31.01 | ReportLab, 3KB invoices, professional layout |
| Ledger Persistence | ✅ 100% | 31.01 | Firestore (3 collections), idempotency, retry queue |
| QR Code | ✅ 100% | 31.01 | JIR verification, embedded u PDF |
| Firestore Integration | ✅ 100% | 31.01 | Composite index kreiran (CICAgJiUpoMK) |
| Fiskalizacija | ✅ 100% | 29.01 | JIR primanje, FINA XML format, XAdES signing |

**Napomena:** Dan 1-3 planirano za 3 dana, završeno u 1 dan! 🚀

---

## Tjedan 3 - Ostatak (01-05.02.2026)

### Dan 4-5: End-to-End Testing & Validation

**Cilj:** Osigurati da sve radi zajedno - od input podataka do gotovog PDF-a s JIR-om

#### Dan 4 (01.02) - Subota

**Fokus: Comprehensive End-to-End Testing**

```bash
# Test 1: Potpuni fiskalizacijski flow
python test_fiskalizacija_full.py
# Expected: Invoice → ZKI → XML → XAdES → FINA → JIR → PDF → Ledger

# Test 2: PDF generation s različitim invoice podacima
python test_pdf_generation.py
# Test:
#   - Različiti broj stavki (1, 5, 10, 20)
#   - Različite PDV stope (0%, 5%, 13%, 25%)
#   - Dulji opisi (word wrap test)
#   - Special characters u nazivima

# Test 3: Ledger idempotency
python test_ledger.py
# Test:
#   - Dupli poziv za istu fakturu (mora odbiti)
#   - Check prije slanja (exists check)
#   - Retry queue funkcionalnost

# Test 4: QR code scanning
# Manuelno:
#   - Generiraj PDF
#   - Skeniraj QR s mobitelom
#   - Verificiraj da otvara JIR link
```

**Deliverables:**
- [ ] Svi testovi prolaze
- [ ] PDF se otvara bez grešaka
- [ ] QR kod skeniran i verificiran
- [ ] Ledger entries persistent u Firestore
- [ ] Test report dokument

#### Dan 5 (02.02) - Nedjelja

**Fokus: Error Scenarios & Edge Cases**

```bash
# Test 1: Network failures
# Simuliraj:
#   - FINA timeout (mock response delay)
#   - Connection refused
#   - SSL handshake error

# Test 2: FINA error responses
# Test s intentionally broken data:
#   - Missing required fields (s001)
#   - Invalid OIB (s002)
#   - Invalid signature format (s004)

# Test 3: Retry queue behaviour
#   - Dodaj failed invoice u queue
#   - Provjeri next_retry timestamp
#   - Provjeri 48h deadline
#   - Simuliraj retry nakon N minuta

# Test 4: Firestore persistence across restarts
#   - Restart aplikacije
#   - Provjeri da ledger entries ostaju
#   - Provjeri da retry queue nije lost
```

**Deliverables:**
- [ ] Error handling dokumentiran
- [ ] Retry queue testiran
- [ ] Edge cases pokriveni
- [ ] Bugovi logirani (ako ima)

---

## Tjedan 4: Error Handling & Production Prep (06-12.02.2026)

### Cilj
Dovesti Fazu 1 do kraja - 100% production-ready fiskalizacija (na DEMO certifikatu)

### Dan 1-2 (06-07.02): Resilience Improvements

**Fokus: Circuit Breaker Persistence + Advanced Error Recovery**

#### Zadatak 1: Circuit Breaker u Firestore

**Problem:** Circuit breaker trenutno koristi in-memory state (gubi se nakon restarta)

**Rješenje:**
```python
# Firestore collection: circuit_breaker_states
{
  "service": "fina_soap",
  "state": "OPEN",  # CLOSED, OPEN, HALF_OPEN
  "failure_count": 5,
  "last_failure": "2026-02-06T14:30:00Z",
  "next_retry": "2026-02-06T14:35:00Z",
  "total_failures_24h": 12
}
```

**Implementation:**
```bash
1. [ ] Kreiraj Firestore collection za circuit breaker
2. [ ] Update CircuitBreaker class (tools/resilience/circuit_breaker.py)
3. [ ] Add persistence methods (save_state, load_state)
4. [ ] Test circuit opening/closing across restarts
5. [ ] Add monitoring dashboard query
```

#### Zadatak 2: Gemini API Timeout Handling

**Problem:** Gemini pozivi mogu timeoutati (rijetko, ali može se desiti)

**Rješenje:**
```python
# Wrapper oko Google ADK poziva
async def safe_gemini_call(prompt, timeout=30):
    try:
        response = await asyncio.wait_for(
            agent.run(prompt),
            timeout=timeout
        )
        return response
    except asyncio.TimeoutError:
        # Fallback ili retry
        return await retry_with_backoff(prompt)
```

**Implementation:**
```bash
6. [ ] Add timeout wrapper za Gemini pozive
7. [ ] Test timeout behaviour
8. [ ] Add fallback logic (retry 2x, then fail gracefully)
9. [ ] Log sve timeouts za monitoring
```

#### Zadatak 3: FINA Error Recovery Strategy

**Update error handling matrix:**

| Error Code | Type | Current Action | New Action |
|------------|------|----------------|------------|
| s001-s003 | Validation | Reject | Reject + detailed user message |
| s004 | Signature | Log | Retry 1x with re-signing |
| s006 | System | ✅ RIJEŠENO | N/A |
| s007 | Timeout | Log | Add to retry queue (3 attempts) |
| s008 | Duplicate JIR | Log | Check ledger, return existing JIR |
| HTTP 500 | Server | Retry | Exponential backoff, circuit breaker |
| HTTP 503 | Unavailable | Retry | Add to retry queue, notify user |

**Implementation:**
```bash
10. [ ] Update fina_soap_client.py error mapping
11. [ ] Implement retry logic za s007
12. [ ] Add duplicate detection za s008
13. [ ] Test svaki error code path
```

**Deliverables:**
- [ ] Circuit breaker persistent
- [ ] Gemini timeouts handled
- [ ] FINA error recovery tested
- [ ] Error handling dokumentacija

### Dan 3-4 (08-09.02): Comprehensive Test Suite

**Fokus: Unit + Integration + Load Testing**

#### Unit Tests (pytest)

```bash
# Create test files:
tests/unit/test_zki_calculation.py
tests/unit/test_xml_builder.py
tests/unit/test_xades_signer.py
tests/unit/test_pdf_generator.py
tests/unit/test_qr_generator.py
tests/unit/test_ledger.py
```

**Coverage target: 90%+**

```bash
1. [ ] Write unit tests za sve core functions
2. [ ] Run pytest --cov
3. [ ] Identify gaps, add missing tests
4. [ ] Setup CI/CD (optional - GitHub Actions)
```

#### Integration Tests

```bash
tests/integration/test_end_to_end.py
tests/integration/test_firestore_integration.py
tests/integration/test_fina_communication.py
tests/integration/test_agent_coordination.py
```

**Test scenarios:**
```bash
5. [ ] Test 1: Full flow (input → PDF + JIR)
6. [ ] Test 2: Idempotency (duplicate invoice rejection)
7. [ ] Test 3: Retry queue (failed → retry → success)
8. [ ] Test 4: Multi-invoice batch (5 invoices sequentially)
```

#### Load Testing

**Goal:** Verificirati da sustav podnosi realistično opterećenje

```bash
# Scenario: Mali obrt = ~10-30 računa dnevno
# Test: 100 invoices u 1 sat

tests/load/test_100_invoices.py
```

**Metrics:**
```bash
9. [ ] Average response time < 3s
10. [ ] P95 response time < 5s
11. [ ] 0% failure rate
12. [ ] Firestore write throughput
13. [ ] FINA API rate limiting check
```

**Deliverables:**
- [ ] 90%+ test coverage
- [ ] Integration tests pass
- [ ] Load test results documented
- [ ] Performance baseline established

### Dan 5 (10.02): Security Audit & Secret Manager Prep

**Fokus: Pripremiti za production (Secret Manager integration)**

#### Security Checklist

```bash
# 1. Secrets Audit
[ ] Provjeri .env za hardcoded secrets
[ ] Provjeri code za hardcoded passwords/keys
[ ] List svi secrets koje treba premjestiti

# 2. Secret Manager Setup (GCP)
[ ] Enable Secret Manager API
[ ] Create secrets:
    - fina-demo-certificate (p12 file)
    - fina-certificate-password
    - google-oauth-client-secret
    - telegram-bot-token (optional)

# 3. Update Code
[ ] Add secret fetching functions
[ ] Replace hardcoded secrets s Secret Manager calls
[ ] Test da sve radi s Secret Manager

# 4. Certificate Validation
[ ] Add certificate expiry check
[ ] Add issuer validation
[ ] Add certificate chain verification
[ ] Alert ako certifikat istječe za < 30 dana
```

#### Code Updates

**Before (hardcoded):**
```python
cert_path = "./47034854402.F1.1.p12"
cert_password = "hardcoded_password"
```

**After (Secret Manager):**
```python
from google.cloud import secretmanager

def get_certificate():
    client = secretmanager.SecretManagerServiceClient()
    cert_name = f"projects/{project_id}/secrets/fina-demo-certificate/versions/latest"
    response = client.access_secret_version(request={"name": cert_name})
    return response.payload.data

def get_cert_password():
    client = secretmanager.SecretManagerServiceClient()
    pwd_name = f"projects/{project_id}/secrets/fina-certificate-password/versions/latest"
    response = client.access_secret_version(request={"name": pwd_name})
    return response.payload.data.decode('UTF-8')
```

**Implementation:**
```bash
1. [ ] Create tools/security/secret_manager.py
2. [ ] Add get_secret() helper function
3. [ ] Update fina_soap_client.py
4. [ ] Update xades_signer.py
5. [ ] Test s Secret Manager secrets
6. [ ] Remove hardcoded secrets iz .env (backup first!)
```

**Deliverables:**
- [ ] Secret Manager enabled
- [ ] All secrets migrated
- [ ] Certificate validation implemented
- [ ] Zero hardcoded secrets u code

---

## End of Week 4 Deliverables (12.02.2026)

### Faza 1 - 100% Complete! 🎉

**Functional Checklist:**
- [x] Fiskalizacija funkcionalna (JIR primanje)
- [x] PDF generation s QR kodom
- [x] Ledger persistence (Firestore)
- [x] Idempotency check
- [ ] Error handling comprehensive (**Tjedan 4**)
- [ ] Circuit breaker persistent (**Tjedan 4**)
- [ ] 90%+ test coverage (**Tjedan 4**)
- [ ] Secret Manager integration (**Tjedan 4**)

**Production Readiness (DEMO certifikat):**
- [ ] 100% success rate na DEMO fiskalizaciji
- [ ] PDF generation < 2s
- [ ] All errors handled gracefully
- [ ] Monitoring setup (Cloud Logging queries)
- [ ] Documentation complete

**Ready for Faza 2:**
- [ ] Svi core features stable
- [ ] Test suite comprehensive
- [ ] Security best practices implemented
- [ ] Code ready za multi-tenant

---

## Faza 2 Preview: REST API + Multi-Tenant (Tjedan 5-6)

### Priprema (Početak Tjedna 5)

**Arhitektura brainstorming:**
```
1. [ ] Odlučiti: FastAPI vs Flask?
2. [ ] Dizajnirati endpoint strukturu
3. [ ] Dizajnirati auth flow (JWT vs session)
4. [ ] Dizajnirati user model (Firestore schema)
5. [ ] Plan deployment na Cloud Run
```

**Tech Stack Decisions:**
```python
# Option A: FastAPI (preporučeno)
- Modern, async, fast
- Auto OpenAPI docs
- Type hints native
- Great for AI/LLM integration

# Option B: Flask
- Simpler, more traditional
- Više resources/tutorials
- Lakše za debuggiranje
```

**Multi-Tenant Planning:**
```
# Kako ćemo odvojiti korisnike?
Option 1: Firestore collections s user_id prefix
  /users/{user_id}/invoices/{invoice_id}

Option 2: Shared collections s user_id field
  /invoices/{invoice_id} (field: user_id)

# Authentication
- Google OAuth (already have infrastructure)
- JWT tokens za API
- Rate limiting per user (Firestore counters)
```

---

## Success Metrics

### Tjedan 3-4 (Faza 1)

**Technical:**
- 100% fiscalization success rate (DEMO)
- PDF generation < 2s (avg)
- Test coverage > 90%
- Zero hardcoded secrets
- Circuit breaker working across restarts

**Functional:**
- E2E flow funkcionalan
- All error scenarios handled
- Retry queue tested
- QR kod skeniran i verificiran

### Faza 2 Target (End of Tjedan 6)

**API:**
- 10+ endpoints implemented
- < 500ms response time (p95)
- JWT authentication working
- OpenAPI docs generated

**Multi-Tenant:**
- 2-3 test users setup
- User isolation verified
- Rate limiting functional

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Firestore quota limits | Medium | Monitor usage, implement caching |
| FINA demo API downtime | Low | Retry queue handles temporary outages |
| Test coverage gaps | Medium | Prioritize critical paths first |
| Secret Manager setup issues | Low | Fallback to env vars for development |
| Burnout (previše brzim tempom) | Medium | Realistic planning, breaks between phases |

---

## Notes & Decisions

### 31.01.2026
- ✅ Odlučeno: ReportLab umjesto WeasyPrint (Windows kompatibilnost)
- ✅ Firestore composite index kreiran - pending_retries query
- ✅ Dan 1-3 completed u 1 dan - ahead of schedule!
- 🎯 Next focus: End-to-end testing + error handling
- 🎯 Week 4 cilj: 100% Faza 1 completion

---

## Quick Reference

**Testovi za pokrenuti:**
```bash
# Ledger
python test_ledger.py

# PDF
python test_pdf_generation.py

# E2E
python test_fiskalizacija_full.py

# Firestore
python test_ledger_firestore.py
```

**Firestore Collections:**
```
fiscalization_ledger       - Successful fiscalizations
fiscalization_retry_queue  - Failed invoices awaiting retry
fiscalization_audit        - Audit log
circuit_breaker_states     - Circuit breaker persistence (TODO)
```

**Key Files:**
```
tools/api_implementations/fiskalizacija_ledger.py    - Ledger logic
tools/api_implementations/fina_soap_client.py        - FINA communication
tools/api_implementations/fina_xml_builder.py        - XML generation
tools/adk_tools/fiskalizacija_adk_tools.py           - ADK tool wrappers
agents/adk_agents/fiskalni_executor_adk.py           - Main executor
templates/invoice_template.html                      - PDF template (unused)
```

---

*Dokument kreiran: 31.01.2026*
*Plan za: Veljača 2026*
*Status: ACTIVE - Tjedan 3-4 u tijeku*
