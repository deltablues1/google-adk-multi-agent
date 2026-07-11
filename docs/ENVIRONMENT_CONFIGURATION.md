# Environment Variables & Configuration Guide

**Verzija:** 1.0
**Datum:** 02.02.2026
**Autor:** Claude + Tomislav

---

## Pregled

Ovaj dokument opisuje sve environment varijable i konfiguracijske opcije za Google Workspace AI Assistant sistem.

---

## OAuth Konfiguracija

### Google OAuth Credentials

**Lokacija:** `~/.google_workspace_adk/tokens.json`

**Setup:**

```bash
# Inicijalna autentifikacija
python tools/oauth_cli.py --auth

# Provjera postojećih credentials
python tools/oauth_cli.py --check

# Refresh token
python tools/oauth_cli.py --refresh

# Revoke i ponovo autentificiraj
python tools/oauth_cli.py --revoke
python tools/oauth_cli.py --auth
```

**OAuth Scopes:**

Sistem automatski traži pristup sljedećim scopeovima:

- `https://www.googleapis.com/auth/gmail.send` - Slanje emailova
- `https://www.googleapis.com/auth/gmail.readonly` - Čitanje emailova
- `https://www.googleapis.com/auth/drive` - Google Drive pristup
- `https://www.googleapis.com/auth/drive.file` - File upload/download
- `https://www.googleapis.com/auth/spreadsheets` - Google Sheets pristup
- `https://www.googleapis.com/auth/calendar` - Google Calendar pristup
- `https://www.googleapis.com/auth/contacts` - Google Contacts pristup
- `https://www.googleapis.com/auth/tasks` - Google Tasks pristup

**VAŽNO:** Ako dobijete "Permission denied" greške, morate revoke-ati stare tokene i ponovo autentificirati sa svim scopeovima.

---

## Fiskalizacija Environment Variables

### 1. `AUTO_APPROVE_HITL`

**Svrha:** Automatski odobrava HITL (Human-in-the-Loop) konfirmacije tijekom fiskalizacije.

**Vrijednosti:**
- `true` - Automatski odobri sve HITL zahtjeve
- `false` ili nedefinirano - Traži korisničku potvrdu (DEFAULT)

**Korištenje:**

```bash
# Windows CMD
set AUTO_APPROVE_HITL=true
python main.py --agent fiskalizacija --query "Fiskaliziraj račun..."

# Windows PowerShell
$env:AUTO_APPROVE_HITL="true"
python main.py --agent fiskalizacija --query "Fiskaliziraj račun..."

# Linux/Mac
export AUTO_APPROVE_HITL=true
python main.py --agent fiskalizacija --query "Fiskaliziraj račun..."

# Inline (single command)
AUTO_APPROVE_HITL=true python main.py --agent fiskalizacija --query "..."
```

**Preporuke:**
- ✅ **USE for:** Automated testing, integration tests, CI/CD pipelines
- ❌ **NEVER USE for:** Production invoicing, real customer invoices
- ⚠️ **CAUTION:** Ensure invoice data is validated before using auto-approve

**Primjeri:**

```bash
# Testing sa auto-approve
AUTO_APPROVE_HITL=true python test_fiskalizacija_e2e.py

# Production use (HITL required)
python main.py --agent fiskalizacija --query "Fiskaliziraj račun 001/2026..."
# User will see HITL preview and must confirm [Y]es / [N]o / [E]dit
```

---

### 2. `ENABLE_HITL`

**Svrha:** Omogućava ili potpuno onemogućava HITL mehanizam.

**Vrijednosti:**
- `true` - HITL enabled (DEFAULT)
- `false` - HITL completely disabled (NO confirmation prompt)

**Korištenje:**

```bash
# Disable HITL (USE WITH EXTREME CAUTION)
export ENABLE_HITL=false
python main.py --agent fiskalizacija --query "..."
```

**Preporuke:**
- ✅ **USE for:** Fully automated systems with pre-validated data
- ❌ **NEVER USE for:** Manual operation, untested data, production with human operators
- ⚠️ **EXTREME CAUTION:** Invoice will be sent to FINA immediately without ANY review!

**Razlika između `AUTO_APPROVE_HITL` i `ENABLE_HITL`:**

| Feature | `AUTO_APPROVE_HITL=true` | `ENABLE_HITL=false` |
|---------|--------------------------|---------------------|
| Shows HITL preview | ✅ Yes | ❌ No |
| Waits for confirmation | ❌ Auto-confirms | ❌ No wait |
| Logs invoice details | ✅ Yes | ✅ Yes |
| User can review data | ✅ Yes (briefly) | ❌ No |
| Safe for testing | ✅ Yes | ⚠️ Use carefully |
| Safe for production | ❌ No | ❌ Absolutely not |

**Best Practice za testiranje:**

```bash
# Preferred for testing - shows preview, auto-confirms
AUTO_APPROVE_HITL=true python test_fiskalizacija_full.py

# Only for fully automated systems
ENABLE_HITL=false python automated_invoice_processor.py
```

---

### 3. Fiskalizacija Certificate Paths

**Svrha:** Putanje do certifikata za FINA SOAP API.

**Konfigurirano u:** `config/company_config.py`

```python
COMPANY_CONFIG = {
    "cert_path": "path/to/certificate.pem",      # Client certificate
    "key_path": "path/to/private_key.pem",       # Private key
    "ca_bundle_path": "path/to/ca_bundle.pem",   # CA certificates
    # ...
}
```

**Demo certifikati (FINA sandbox):**
- `client_cert.pem` - Demo client certificate
- `client_key.pem` - Demo private key
- `fina_demo_ca_bundle.pem` - Demo CA bundle

**Production certifikati:**
- Morate nabaviti od FINA nakon registracije
- Format: P12 ili PEM
- Konverzija P12 -> PEM:

```bash
# Extract certificate
openssl pkcs12 -in certificate.p12 -clcerts -nokeys -out client_cert.pem

# Extract private key
openssl pkcs12 -in certificate.p12 -nocerts -nodes -out client_key.pem
```

---

### 4. Fiskalizacija Sandbox Mode

**Svrha:** Kontrolira da li se koristi FINA sandbox ili production API.

**Konfigurirano u:** `config/company_config.py`

```python
COMPANY_CONFIG = {
    "use_sandbox": True,  # True = Demo FINA API, False = Production FINA API
    # ...
}
```

**Endpoints:**
- **Sandbox:** `https://cistest.apis.hr/...` (demo environment)
- **Production:** `https://cis.porezna-uprava.hr/...` (real FINA API)

**Preporuke:**
- ✅ **ALWAYS test on sandbox first**
- ✅ Switch to production only after thorough testing
- ⚠️ Production invoices are LEGALLY BINDING and reported to Porezna Uprava

**Workflow:**

```python
# Development / Testing
use_sandbox=True  # Safe, can test unlimited invoices

# Staging (final validation)
use_sandbox=True  # Still sandbox, but with production-like data

# Production
use_sandbox=False  # Real invoices, real legal consequences
```

---

## Google API Configuration

### API Rate Limiting

**Konfigurirano u:** `tools/resilience/retry_handler.py`

```python
@retry_with_backoff(
    max_retries=3,           # Max number of retries
    initial_delay=1.0,       # Initial delay (seconds)
    exponential_base=2.0,    # Backoff multiplier
    max_delay=60.0           # Maximum delay (seconds)
)
async def my_api_call():
    # Your API call
```

**Google API Quotas (per project):**

- **Gmail API:** 250 emails/day (default), 1 billion requests/day
- **Drive API:** 1 billion requests/day
- **Sheets API:** 500 requests/100 seconds per user
- **Calendar API:** 1 million requests/day
- **Contacts API:** 600 requests/minute

**Kada dostignete limit:**
- `429 Too Many Requests` error
- Retry handler automatski čeka i pokušava ponovno
- Exponential backoff: 1s → 2s → 4s → 8s → ...

---

### Circuit Breaker Pattern

**Svrha:** Sprječava preopterećenje API-ja nakon uzastopnih grešaka.

**Konfigurirano u:** `tools/resilience/circuit_breaker.py`

```python
circuit_breaker = CircuitBreaker(
    failure_threshold=5,      # Max failures before opening circuit
    recovery_timeout=60,      # Seconds to wait before trying again
    expected_exception=Exception
)
```

**Circuit States:**

1. **CLOSED** - Normalan rad, sve prolazi
2. **OPEN** - Previše grešaka, blokira sve zahtjeve
3. **HALF_OPEN** - Test period, provjerava da li se API oporavio

**Primjer:**

```python
# Circuit je CLOSED, normalan rad
result = await api_call()  # ✅ Success

# 5 consecutive failures
result = await api_call()  # ❌ Error
result = await api_call()  # ❌ Error
result = await api_call()  # ❌ Error
result = await api_call()  # ❌ Error
result = await api_call()  # ❌ Error

# Circuit je sad OPEN
result = await api_call()  # ⛔ Immediately fails, no API call

# Nakon 60 sekundi -> HALF_OPEN
result = await api_call()  # 🔄 Test call
# Ako uspije -> CLOSED, inače -> OPEN again
```

---

## Logging Configuration

### Log Files

**Lokacija:** `logs/` directory

```
logs/
├── app.log                 # Main application log
├── fiskalizacija.log       # Fiskalizacija operations log
└── agent_execution.log     # Agent execution traces
```

**Log Levels:**

```python
import logging

# Set log level
logging.basicConfig(level=logging.INFO)  # INFO, DEBUG, WARNING, ERROR, CRITICAL
```

**Log Rotation:**

Logs se automatski rotiraju kada dosegnu 10MB.

**Real-time log viewing:**

```bash
# Linux/Mac
tail -f logs/app.log
tail -f logs/fiskalizacija.log

# Windows PowerShell
Get-Content logs/app.log -Wait -Tail 50
```

---

## Agent-Specific Configuration

### Smart Orchestrator

**Konfigurirano u:** `agents/adk_agents/smart_orchestrator.py`

```python
# Max number of parallel agent executions
MAX_PARALLEL_AGENTS = 5

# Timeout for agent execution (seconds)
AGENT_TIMEOUT = 300  # 5 minutes
```

---

### Mailer Agent (Gmail)

**Email Sending Limits:**

```python
# Daily limit (Google default for free accounts)
DAILY_EMAIL_LIMIT = 250

# Per-minute limit (to avoid spam detection)
EMAILS_PER_MINUTE = 5
```

**VAŽNO:** Gmail može privremeno blokirati slanje ako pošaljete previše emailova odjednom.

**Test Mode:**

```python
# In test mode, emails are logged but NOT sent
TEST_MODE = True  # Set to False for production
```

---

### Fiskalizacija Agent

**Konfigurirano u:** `config/company_config.py`

```python
COMPANY_CONFIG = {
    # Company info
    "oib": "12345678901",
    "company_name": "LUX TECH d.o.o.",
    "address": "Testna ulica 123",
    "city": "Zagreb",
    "zip_code": "10000",

    # Invoice settings
    "invoice_prefix": "DEMO",
    "vat_rate": 25.0,  # PDV stopa (%)
    "payment_method": "G",  # G = Gotovina, K = Kartice, T = Transakcijski

    # API settings
    "use_sandbox": True,
    "cert_path": "client_cert.pem",
    "key_path": "client_key.pem",
    "ca_bundle_path": "fina_demo_ca_bundle.pem",

    # Business location (Poslovni prostor)
    "business_location_id": "POS1",
    "device_id": "DEV1",
}
```

**NKD (Nacionalna klasifikacija djelatnosti):**

NKD kodovi učitavaju se iz `NKD_2025.csv` file.

Primjeri:
- `62.01` - Computer programming activities
- `62.02` - Computer consultancy activities
- `62.09` - Other IT services

---

## Firestore Configuration

**Svrha:** Idempotency ledger za fiskalizaciju (prevents duplicate submissions).

**Environment Variable:**

```bash
# Path to Firestore service account JSON
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/serviceAccountKey.json"
```

**Firestore Collection:**

- **Collection:** `fiskalizacija_ledger`
- **Document ID:** `{invoice_number}_{oib}`
- **Fields:** `invoice_number`, `jir`, `zki`, `timestamp`, `status`

**Provjera duplikata:**

```python
# Prije fiskalizacije, provjeravamo ledger
existing = ledger.get_invoice(invoice_number)
if existing and existing.get('jir'):
    # Invoice već fiskaliziran, vrati postojeći JIR
    return existing
```

---

## Performance Tuning

### Async Concurrency

```python
# Maximum concurrent tasks
MAX_CONCURRENT_TASKS = 10

# Semaphore for rate limiting
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
```

### Timeout Settings

```python
# HTTP request timeout (seconds)
HTTP_TIMEOUT = 30

# Agent execution timeout (seconds)
AGENT_TIMEOUT = 300  # 5 minutes

# SOAP API timeout (seconds)
SOAP_TIMEOUT = 60
```

---

## Security Best Practices

### 1. Never Commit Secrets

**NEVER commit to git:**
- ❌ `tokens.json` (OAuth tokens)
- ❌ `*.p12`, `*.pem` (Certificates and private keys)
- ❌ `.env` files with secrets
- ❌ `serviceAccountKey.json` (Firestore credentials)

**Use `.gitignore`:**

```
# OAuth tokens
tokens.json
.google_workspace_adk/

# Certificates
*.p12
*.pem
client_cert.pem
client_key.pem

# Firestore
serviceAccountKey.json

# Environment files
.env
.env.local
```

---

### 2. Rotate Credentials Regularly

```bash
# Revoke old OAuth tokens
python tools/oauth_cli.py --revoke

# Generate new tokens
python tools/oauth_cli.py --auth
```

**Frequency:**
- OAuth tokens: Every 6 months or when compromised
- FINA certificates: Before expiration (usually 1-2 years)

---

### 3. Use Sandbox for Testing

```python
# ALWAYS test on sandbox first
use_sandbox = True

# Only switch to production after thorough testing
# use_sandbox = False  # Uncomment when ready
```

---

## Troubleshooting Environment Issues

### Problem: "No OAuth credentials found"

**Rješenje:**

```bash
python tools/oauth_cli.py --auth
```

---

### Problem: "Token expired or invalid"

**Rješenje:**

```bash
# Try refresh first
python tools/oauth_cli.py --refresh

# If that fails, re-authenticate
python tools/oauth_cli.py --revoke
python tools/oauth_cli.py --auth
```

---

### Problem: "Certificate verification failed"

**Uzroci:**
- Wrong certificate path
- Certificate expired
- Missing CA bundle

**Rješenje:**

```bash
# Check certificate validity
openssl x509 -in client_cert.pem -text -noout

# Check expiration date
openssl x509 -in client_cert.pem -noout -dates

# Verify certificate chain
openssl verify -CAfile fina_demo_ca_bundle.pem client_cert.pem
```

---

### Problem: "Rate limit exceeded"

**Rješenje:**

```python
# Increase retry delays
@retry_with_backoff(
    max_retries=5,
    initial_delay=2.0,
    exponential_base=2.0,
    max_delay=120.0
)
```

Or wait until rate limit resets (usually 1 minute for Google APIs).

---

### Problem: "Circuit breaker OPEN"

**Uzrok:** Previše uzastopnih API grešaka.

**Rješenje:**

1. Check API status: https://status.cloud.google.com/
2. Check your credentials
3. Wait for recovery timeout (default 60s)
4. Investigate root cause of failures

```bash
# Check logs for error patterns
grep "ERROR" logs/app.log | tail -20
```

---

## Environment Variable Quick Reference

| Variable | Purpose | Values | Default |
|----------|---------|--------|---------|
| `AUTO_APPROVE_HITL` | Auto-approve HITL | `true`, `false` | `false` |
| `ENABLE_HITL` | Enable/disable HITL | `true`, `false` | `true` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Firestore credentials | Path to JSON file | None |
| `TEST_MODE` | Enable test mode | `true`, `false` | `false` |

---

## Configuration File Quick Reference

| File | Purpose | Location |
|------|---------|----------|
| `tokens.json` | OAuth tokens | `~/.google_workspace_adk/` |
| `company_config.py` | Company & fiskalizacija settings | `config/` |
| `agent_registry.py` | Agent registration | `config/` |
| `client_cert.pem` | FINA client certificate | Project root |
| `client_key.pem` | FINA private key | Project root |
| `fina_demo_ca_bundle.pem` | CA certificates | Project root |
| `NKD_2025.csv` | NKD business codes | Project root |

---

## Sigurnost i pouzdanost (srpanj 2026)

### Korisnički kontekst

| Varijabla | Default | Opis |
|-----------|---------|------|
| `DEFAULT_USER_ID` | `tomislav` | Identitet jedinog korisnika (config/user_context.py) |
| `DEFAULT_USER_TIMEZONE` | `Europe/Zagreb` | Timezone za Calendar evente, briefing i termine |
| `DEFAULT_USER_LANGUAGE` | `hr` | Jezik korisničkog sučelja |

### Smart home — potvrda stvarnog stanja (MQTT confirm)

| Varijabla | Default | Opis |
|-----------|---------|------|
| `MQTT_CONFIRM_ENABLED` | `true` | Čekaj da uređaj potvrdi novo stanje na `.../state` topicu; `false` vraća fire-and-forget |
| `MQTT_CONFIRM_TIMEOUT` | `3.0` | Sekunde čekanja na potvrdu stanja |
| `MQTT_TLS` | (isključeno) | `true` uključuje TLS prema MQTT brokeru (tools + HA bridge) |
| `HA_BRIDGE_RETAIN_TRANSCRIPTS` | `false` | Retain zadnjeg transkripta/odgovora u brokeru (privatnost: default isključeno) |
| `VOICE_SMART_HOME_RESPONSE_MODE` | `ok` | `ok` = "U redu.", `none` = tiho (SAMO za uspjehe — neuspjesi se uvijek izgovaraju), ostalo = puni opis |

Zaštićene radnje traže `confirm=True` u `mqtt_switch_control`: gašenje frižidera,
gašenje bojlera, paljenje pećnice.

### Telegram

| Varijabla | Default | Opis |
|-----------|---------|------|
| `TELEGRAM_WEBHOOK_SECRET` | (prazno) | Secret token za webhook — bez njega se lažni POST ne može odbiti; postavi u webhook modu |
| `TELEGRAM_MAX_INPUT_TEXT_LENGTH` | `4000` | Limit duljine tekstualne poruke |
| `TELEGRAM_MAX_PHOTO_BYTES` | `10485760` | Limit veličine fotografije (provjera PRIJE downloada) |

### Gmail

| Varijabla | Default | Opis |
|-----------|---------|------|
| `GMAIL_ATTACHMENT_DIRS` | `output,uploads,temp` | Sandbox: privitci smiju dolaziti samo iz ovih direktorija projekta |

### Dnevni briefing

| Varijabla | Default | Opis |
|-----------|---------|------|
| `BRIEFING_LLM_SUMMARY` | `true` | LLM sažetak briefinga; `false` = samo deterministički hrvatski template |
| `BRIEFING_SUMMARY_MODEL` | `gemini-3.5-flash` | Model za sažetak |

Pozivanje: glasovno ("dnevni pregled", "što me čeka danas"), Telegram `/pregled`,
ili scheduler job s `action_type: "briefing"`. Primjer jobsa (07:00 svaki dan,
isporuka na autorizirani Telegram chat):

```json
{
  "jobs": [
    {
      "id": "morning-briefing",
      "name": "Jutarnji pregled",
      "agent_request": "",
      "action_type": "briefing",
      "trigger": {"type": "cron", "cron_expression": "0 7 * * *", "timezone": "Europe/Zagreb"}
    }
  ]
}
```

### Zakazivanje sastanaka (secretary)

Novi alati: `calendar_check_freebusy`, `calendar_propose_meeting_slots`
(radno vrijeme 9–17, radni dani, do 3 prijedloga), `calendar_create_meeting`
(Google Meet link + pozivnice preko `sendUpdates=all`). Follow-up email ide
isključivo kao Gmail draft. Kontakti s više pogodaka vraćaju `ambiguous` i
traže izbor korisnika.

---

## Additional Resources

- **Google API Documentation:** https://developers.google.com/workspace
- **FINA Fiskalizacija 2.0 Spec:** https://www.fina.hr/fiskalizacija
- **OAuth 2.0 Guide:** https://developers.google.com/identity/protocols/oauth2

---

**Zadnje ažurirano:** 11.07.2026
**Verzija:** 1.1
**Status:** Production-ready
