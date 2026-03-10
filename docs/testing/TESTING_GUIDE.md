# Testing Guide - Multi-Agent System

## Automatski Testovi

Napravio sam **2 verzije test skripti** za testiranje multi-agent sistema:

### 1. **test_runner_simple.py** - PREPORUČENO za brzo testiranje ⚡

**Što testira:**
- 13 core testova
- Single-agent operacije (Mailer, Secretary, Rolodex, Tracker, Librarian, Researcher)
- Multi-agent workflows (2 agenta)
- Complex workflows (3 agenta: Research → Document → Email)
- Croatian language support
- Error handling
- **Vrijeme izvršavanja: ~5-10 minuta**

**Kako pokrenuti:**
```bash
cd "C:\Users\Tomislav\Desktop\ai agenti\1\google_claude"
python test_runner_simple.py
```

---

### 2. **test_runner.py** - Kompletno testiranje 🔍

**Što testira:**
- ~30 detaljnih testova
- Sve kategorije workflowa
- Edge cases
- Conditional logic
- Duplicate detection
- Croatian date formats
- **Vrijeme izvršavanja: ~15-30 minuta**
- **Sprema rezultate u JSON i LOG file**

**Kako pokrenuti:**
```bash
cd "C:\Users\Tomislav\Desktop\ai agenti\1\google_claude"
python test_runner.py
```

**Output fajlovi:**
- `test_results_YYYYMMDD_HHMMSS.log` - Detaljan log svih testova
- `test_results_YYYYMMDD_HHMMSS.json` - JSON summary sa rezultatima

---

## Test Podaci

Svi testovi koriste **stvarne podatke** koje si dao:

### Postojeći Korisnik:
- **Ime:** Tomislav Golić
- **Email:** tgolic555@gmail.com

### Novi Kontakt (za dodavanje):
- **Ime:** Davor Golić
- **Email:** davor_golic@hotmail.com
- **Telefon:** 0915584072

---

## Kako Čitati Rezultate

### Console Output

**Uspješan test:**
```
🧪 TEST: Single-Agent: Mailer - Get Recent Emails
Query: Pokaži mi zadnjih 5 emailova
────────────────────────────────────────────────────────────────
⏳ Executing...

[Agent output...]

✅ SUCCESS
Response: [Agent response...]
```

**Neuspješan test:**
```
🧪 TEST: Error Handling: Invalid Email Detection
Query: Pošalji email na 'invalid_bez_at' sa porukom 'test'
────────────────────────────────────────────────────────────────
⏳ Executing...

❌ FAILED: Invalid email format
```

---

### JSON Output (samo test_runner.py)

```json
{
  "summary": {
    "total": 30,
    "passed": 28,
    "failed": 2,
    "skipped": 0,
    "success_rate": "93.3%"
  },
  "results": [
    {
      "test_name": "Mailer: Get last 5 emails",
      "query": "Pokaži mi zadnjih 5 emailova",
      "success": true,
      "agent_used": "Mailer",
      "response": "..."
    },
    ...
  ]
}
```

---

## Što Testovi Pokrivaju

### ✅ Single-Agent Operacije
- Mailer: email retrieval, search, sending
- Secretary: calendar events, meeting scheduling
- Rolodex: contact search, add, update
- Tracker: task creation, listing, status updates
- Librarian: Drive file search, folder operations
- Analyst: Google Sheets data analysis
- Researcher: web search, information gathering

### ✅ Multi-Agent Workflows (2 agenta)
- Research → Email
- Contact → Email
- Calendar → Tasks
- Email → Tasks

### ✅ Complex Workflows (3+ agenta)
- Research → Document → Email
- Meeting Notes → Tasks → Email
- Calendar → Tasks → Email

### ✅ Edge Cases
- Invalid email format detection
- Duplicate contact detection
- Missing information handling (agent asks for clarification)
- Croatian date format conversion (DD.MM.YYYY → ISO 8601)
- Croatian character preservation (č, ć, đ, š, ž)

### ✅ Conditional Logic
- IF-THEN workflows
- Date-based conditional execution

---

## Prije Pokretanja Testova

### 1. Provjeri Environment
```bash
# Provjeri da li su sve dependencies instalirane
pip install -r requirements.txt

# Provjeri da li su environment varijable postavljene
# (.env file sa Google API credentials)
```

### 2. Provjeri Google API Access
- Gmail API enabled
- Google Calendar API enabled
- Google Drive API enabled
- Google Sheets API enabled
- Firestore setup

### 3. Test Connection (opcionalno)
```bash
# Ručni test jednog upita
python main.py
# Upiši: "Pokaži mi zadnjih 5 emailova"
```

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'google_adk'"
**Rješenje:**
```bash
pip install google-adk
# ili
pip install -r requirements.txt
```

### Problem: "Authentication error"
**Rješenje:**
- Provjeri `.env` file
- Provjeri Google Cloud credentials
- Rerun OAuth flow ako treba

### Problem: "Rate limit exceeded"
**Rješenje:**
- Pričekaj 1-2 minute između testova
- Koristi `test_runner_simple.py` sa manjim brojem testova

### Problem: "Firestore permission denied"
**Rješenje:**
- Provjeri Firestore rules
- Provjeri service account permissions

---

## Prilagodba Testova

### Dodaj Svoje Testove

Otvori `test_runner_simple.py` i dodaj:

```python
await run_query(
    query="Tvoj custom upit ovdje",
    description="Opis što test radi"
)
```

### Promijeni Test Podatke

Promijeni konstante na vrhu filea:

```python
USER_EMAIL = "tvoj@email.com"
USER_NAME = "Tvoje Ime"
NEW_CONTACT_NAME = "Novi Kontakt"
NEW_CONTACT_EMAIL = "novi@email.com"
NEW_CONTACT_PHONE = "123456789"
```

---

## Očekivani Rezultati

### test_runner_simple.py
- **Trajanje:** 5-10 minuta
- **Testova:** 13
- **Očekivani pass rate:** >85%
- **Ispis:** Real-time console output

### test_runner.py
- **Trajanje:** 15-30 minuta
- **Testova:** ~30
- **Očekivani pass rate:** >80%
- **Ispis:** Console + LOG file + JSON summary

---

## Analiza Rezultata

Nakon testiranja, provjeri:

1. **Success Rate**: Koliko % testova je prošlo?
2. **Failed Tests**: Koji testovi nisu prošli i zašto?
3. **Agent Selection**: Jesu li odabrani pravi agenti za svaki zadatak?
4. **Error Messages**: Jesu li error poruke jasne i korisne?
5. **Croatian Support**: Jesu li zadržani special characteri (č, ć, đ, š, ž)?
6. **Multi-Agent Flows**: Prolaze li rezultati ispravno između agenata?

---

## Sljedeći Koraci

Nakon što testovi prođu:

1. **Analiziraj logove** za edge case scenarije
2. **Prilagodi agent instructions** gdje treba
3. **Dodaj nove testove** za specifične use case-ove
4. **Testiraj production scenarios** sa stvarnim podacima

---

## Reference Fajlovi

- `test_queries.md` - 170 test primjera (manualnih)
- `test_runner_simple.py` - Brzi automated testovi
- `test_runner.py` - Kompletni automated testovi
- `main.py` - Glavni entry point za sistem

---

**Happy Testing!** 🚀
