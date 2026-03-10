# CLI Workflow Guide - Google Workspace AI Assistants

**Verzija:** 1.0
**Datum:** 02.02.2026
**Autor:** Claude + Tomislav

---

## Pregled

Ovo je vodič za korištenje Google Workspace AI Assistant sistema preko CLI interfacea. Sistem trenutno podržava 21 specijaliziranih AI agenata koji automatiziraju zadatke u Google Workspace ekosustavu.

---

## Instalacija i Setup

### 1. Preduvjeti

```bash
# Python 3.11+
python --version

# Virtual environment (preporučeno)
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 2. Instalacija dependencies

```bash
pip install -r requirements.txt
```

### 3. Google OAuth Autentifikacija

**VAŽNO:** Prije prvog korištenja morate autentificirati svoj Google Account.

```bash
# Pokrenite OAuth authentication flow
python tools/oauth_cli.py --auth

# Pratite upute u browseru:
# 1. Login na Google Account
# 2. Odobrite pristup svim traženim scopeovima
# 3. Zatvorite browser kad vidite "Authentication successful!"
```

Credentials se spremaju u: `~/.google_workspace_adk/tokens.json`

### 4. Provjera setup-a

```bash
# Testiraj autentifikaciju
python tools/oauth_cli.py --check

# Expected output:
# [OK] OAuth credentials valid
# Scopes: gmail.send, drive, sheets, calendar, contacts, tasks...
```

---

## Osnovni CLI Workflow

### Interaktivni Mod

```bash
# Pokretanje glavnog CLI interfacea
python main.py

# CLI će vam ponuditi:
# 1. Izbor agenta (Smart Orchestrator, Analyst, Mailer, itd.)
# 2. Unos vašeg upita/zahtjeva
# 3. Real-time izvršavanje s prikaz progresa
# 4. Rezultat sa svim relevantnim informacijama
```

### Single-Command Mod

```bash
# Direktno izvršavanje jednog zahtjeva
python main.py --agent smart_orchestrator --query "Kreiraj tablicu s mjesečnim prihodima"

# S automatskim HITL odobravanjem (za fiskalizaciju)
AUTO_APPROVE_HITL=true python main.py --agent fiskalizacija --query "Fiskaliziraj račun..."
```

---

## Agent Capabilities

### 1. **Smart Orchestrator** (Primarni agent za kompleksne zadatke)

**Što radi:**
- Koordinira više agenata za multi-step workflowe
- Automatski identificira potrebne agente
- Delegira zadatke i agregira rezultate

**Primjeri upita:**

```bash
# Multi-agent koordinacija
"Kreiraj Google Sheet 'Q1 Sales', dodaj testne podatke, uploadaj na Drive u folder 'Reports'"

# Gmail + Calendar koordinacija
"Pošalji email Tomislavu s pozivom na sastanak sutra u 10h"

# Sheets + Tasks koordinacija
"Analiziraj podatke u 'Q1 Sales' tablici i kreiraj task za svaki red gdje je amount > 1000 EUR"
```

**Kdy koristiti:** Za SVE kompleksne zahtjeve koji zahtijevaju više od jednog API-ja.

---

### 2. **Analyst Agent** (Google Sheets)

**Capabilities:**
- ✅ Read/write Sheets data
- ✅ Search i filter podataka
- ✅ Calculate totals, averages, formulas
- ✅ Create new spreadsheets
- ✅ Update ranges

**Primjeri upita:**

```bash
"Pronađi sve redove u 'Sales Data' gdje je Product = 'IT Consulting'"
"Izračunaj total svih iznosa u koloni E"
"Kreiraj novu tablicu 'Q2 Report' s kolonama Date, Client, Amount"
"Update cell B5 u 'Budget' tablici na 5000"
```

---

### 3. **Librarian Agent** (Google Drive)

**Capabilities:**
- ✅ Search files i folderi
- ✅ Upload files (PDF, images, documents)
- ✅ Create folder strukture
- ✅ Share files (permissions)
- ✅ Move/organize files

**Primjeri upita:**

```bash
"Uploadaj 'invoice_001.pdf' na Drive u folder 'Invoices/2026'"
"Kreiraj folder 'Q1 Reports' i podfolders 'Jan', 'Feb', 'Mar'"
"Pronađi sve PDF-ove modificirane prošli tjedan"
"Share file 'Budget_2026.xlsx' s anyone with link"
```

---

### 4. **Secretary Agent** (Google Calendar)

**Capabilities:**
- ✅ List upcoming events
- ✅ Create new events
- ✅ Update/cancel events
- ✅ Add attendees i reminders

**Primjeri upita:**

```bash
"Kreiraj event 'Team Meeting' sutra u 14h, duration 1h, attendees: tomislav@example.com"
"Pokaži sve evente za sljedeći tjedan"
"Update event 'Client Call' - promijeni vrijeme na 15h"
"Obriši sve evente za danas"
```

---

### 5. **Rolodex Agent** (Google Contacts)

**Capabilities:**
- ✅ Search contacts by name/email
- ✅ Create new contacts
- ✅ Update contact info
- ✅ List all contacts

**Primjeri upita:**

```bash
"Pronađi kontakt 'Tomislav Golić'"
"Kreiraj novi kontakt: Ivan Horvat, ivan@example.com, +385 91 123 4567"
"Update phone number za 'Ana Marić' na +385 91 999 8888"
"Pokaži sve kontakte iz 'LUX TECH' organizacije"
```

---

### 6. **Tracker Agent** (Google Tasks)

**Capabilities:**
- ✅ List tasks
- ✅ Create new tasks s due dates
- ✅ Complete tasks
- ✅ Update task details

**Primjeri upita:**

```bash
"Kreiraj task 'Finish Q1 report' s due date sutra"
"Pokaži sve incomplete tasks"
"Complete task 'Send invoice to client'"
"Update task 'Review contract' - dodaj notes 'Check legal clauses'"
```

---

### 7. **Mailer Agent** (Gmail)

**Capabilities:**
- ✅ Send emails
- ✅ Read recent emails
- ✅ Search inbox
- ✅ Draft emails

**Primjeri upita:**

```bash
"Pošalji email tomislavu@example.com subject 'Meeting reminder' body 'Don't forget our meeting tomorrow!'"
"Pokaži zadnjih 10 emailova"
"Pronađi sve emailove od 'client@example.com' prošli tjedan"
```

**NAPOMENA:** Mailer agent zahtijeva pažljivu upotrebu - emailovi se šalju STVARNO!

---

### 8. **Fiskalizacija Agent** (Croatian Fiscalization)

**Capabilities:**
- ✅ Fiscalize invoices via FINA 2.0 API
- ✅ Generate PDF with JIR, ZKI, QR code
- ✅ HITL confirmation (Human-in-the-Loop)
- ✅ Idempotency via Firestore ledger
- ✅ Auto-upload PDF to Drive

**Primjeri upita:**

```bash
"Fiskaliziraj račun 001/DEMO/1 za Test Kupac, iznos 1875 EUR, IT usluge"
```

**HITL Workflow:**
1. Agent priprema invoice data
2. Prikazuje preview s svim detaljima
3. Traži korisničku potvrdu: `[Y]es / [N]o / [E]dit`
4. Nakon potvrde: sign XML → SOAP call → JIR → PDF → Drive upload

**Environment Variables:**

```bash
# Auto-approve HITL (za testiranje)
export AUTO_APPROVE_HITL=true

# Disable HITL (za automatizaciju - USE WITH CAUTION!)
export ENABLE_HITL=false
```

**VAŽNO:** UVIJEK pregledajte podatke u HITL previewu prije potvrde!

---

## Multi-Agent Workflows

### Primjer 1: Research → Document → Share

```bash
Query: "Analiziraj podatke u 'Sales Q1', kreiraj summary document, uploadaj na Drive i share s team@example.com"

Execution flow:
1. Smart Orchestrator → Analyst (read Sheets data)
2. Smart Orchestrator → Scribe (create Docs summary)
3. Smart Orchestrator → Librarian (upload + share)
4. Return: Document URL + Share link
```

### Primjer 2: Invoice → Fiscalization → Drive

```bash
Query: "Fiskaliziraj račun za Test Client, 2500 EUR, IT Consulting, uploadaj PDF na Drive"

Execution flow:
1. Smart Orchestrator → Fiskalizacija (HITL → JIR + PDF)
2. Smart Orchestrator → Librarian (upload PDF to Drive)
3. Return: JIR + ZKI + Drive link
```

### Primjer 3: Email → Task → Reminder

```bash
Query: "Pošalji email klijentu s ponudom, kreiraj task 'Follow up' za 3 dana, dodaj reminder u Calendar"

Execution flow:
1. Smart Orchestrator → Mailer (send email)
2. Smart Orchestrator → Tracker (create task)
3. Smart Orchestrator → Secretary (create calendar reminder)
4. Return: Email sent + Task created + Event added
```

---

## Troubleshooting

### Problem: "No OAuth credentials found"

**Rješenje:**
```bash
python tools/oauth_cli.py --auth
```

### Problem: "Token expired or invalid"

**Rješenje:**
```bash
# Refresh token automatski
python tools/oauth_cli.py --refresh

# Ili potpuno novi login
python tools/oauth_cli.py --revoke
python tools/oauth_cli.py --auth
```

### Problem: "Permission denied" za Google API

**Rješenje:**
- Provjerite da ste odobrili sve tražene scopeove tijekom OAuth flowa
- Revokeirajte i ponovite autentifikaciju:
```bash
python tools/oauth_cli.py --revoke
python tools/oauth_cli.py --auth
```

### Problem: Fiskalizacija HITL ne prikazuje invoice items

**Rješenje:**
- Ova greška je fixana u verziji 1.2+
- Update na najnoviju verziju: `git pull origin main`

### Problem: Windows console encoding errors

**Rješenje:**
- Koristite PowerShell umjesto CMD
- Ili postavite encoding: `chcp 65001` prije pokretanja

---

## Best Practices

### 1. **Koristite Smart Orchestrator za kompleksne zahtjeve**

```bash
# GOOD - Let orchestrator coordinate
"Kreiraj tablicu, uploadaj na Drive, pošalji link emailom"

# BAD - Trying to do manually
# Step 1: python main.py --agent analyst...
# Step 2: python main.py --agent librarian...
# Step 3: python main.py --agent mailer...
```

### 2. **Budite specifični u upitima**

```bash
# GOOD - Specific request
"Kreiraj Google Sheet 'Q1 Sales 2026' s kolonama: Date, Client, Amount, Status"

# BAD - Vague request
"Napravi neku tablicu"
```

### 3. **Provjerite HITL preview prije fiskalizacije**

```bash
# ALWAYS review:
# - Invoice number
# - Total amount
# - Customer OIB
# - Payment method
# - All line items

# NEVER use AUTO_APPROVE_HITL in production!
```

### 4. **Testirajte na sandbox okruženju prvo**

```bash
# Fiskalizacija sandbox (default)
use_sandbox=True  # ✅ Safe for testing

# Production (samo kad ste sigurni!)
use_sandbox=False  # ⚠️ Real FINA API!
```

### 5. **Pratite log outpute**

```bash
# Logs su u:
# - logs/app.log (main application log)
# - logs/fiskalizacija.log (fiscalization details)

# Real-time log viewing:
tail -f logs/app.log
```

---

## Advanced Usage

### Custom Agent Development

Za dodavanje novog agenta, pogledajte `agents/adk_agents/` folder i pratite ADK pattern.

### MCP Server Integration

Sistem podržava MCP (Model Context Protocol) servere za proširenje funkcionalnosti.

### Telegram Bot Interface

```bash
# Start Telegram bot (polling mode)
python main.py --telegram

# Webhook mode (za production)
python main.py --telegram --webhook --webhook-url https://your-domain.com/webhook
```

---

## Performance Tips

- **Parallel Agent Execution:** Smart Orchestrator automatski izvršava nezavisne operacije u paraleli
- **Caching:** Circuit breaker pattern smanjuje API calls za iste podatke
- **Rate Limiting:** Automatski retry s exponential backoff za API limit errors

---

## Support & Feedback

- **Issues:** https://github.com/yourusername/google-workspace-adk/issues
- **Documentation:** `docs/` folder
- **Test Examples:** `test_real_api_agents.py`, `test_fiskalizacija_*.py`

---

**Zadnje ažurirano:** 02.02.2026
**Verzija:** 1.0
**Status:** Production-ready (Faza 1 complete)
