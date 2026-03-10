# Error Handling & Troubleshooting Guide

**Verzija:** 1.0
**Datum:** 02.02.2026
**Autor:** Claude + Tomislav

---

## Pregled

Ovaj dokument pokriva sve tipove grešaka koje se mogu dogoditi u Google Workspace AI Assistant sistemu, kako ih identificirati, i kako ih riješiti.

---

## Kategorije Grešaka

### 1. Authentication Errors (OAuth)
### 2. Google API Errors
### 3. Fiskalizacija Errors
### 4. Network & Timeout Errors
### 5. Data Validation Errors
### 6. Agent Execution Errors
### 7. File System Errors

---

# 1. Authentication Errors (OAuth)

## Error: "No OAuth credentials found"

**Uzrok:** OAuth tokens ne postoje ili nisu dostupni.

**Poruka:**
```
[ERROR] No OAuth credentials found!
Please authenticate: python tools/oauth_cli.py --auth
```

**Rješenje:**

```bash
# Run OAuth authentication flow
python tools/oauth_cli.py --auth

# Follow browser prompts:
# 1. Login to Google Account
# 2. Grant all requested permissions
# 3. Close browser when you see "Authentication successful!"
```

**Provjera:**

```bash
# Verify credentials exist
python tools/oauth_cli.py --check

# Expected output:
# [OK] OAuth credentials valid
# Scopes: gmail.send, drive, sheets, calendar, contacts, tasks...
```

---

## Error: "Token expired or invalid"

**Uzrok:** OAuth access token je istekao i refresh nije uspio.

**Poruka:**
```
[ERROR] Token expired or invalid
The credentials do not contain the necessary fields need to refresh the access token
```

**Rješenje:**

```bash
# Option 1: Try refresh first (usually works)
python tools/oauth_cli.py --refresh

# Option 2: If refresh fails, re-authenticate
python tools/oauth_cli.py --revoke
python tools/oauth_cli.py --auth
```

**Prevencija:**
- OAuth tokens automatski se refreshaju tijekom korištenja
- Credentials store provjerava expiry i refresha prije svake API operacije
- Ako ne koristite sistem duže vrijeme (7+ dana), možda će trebati re-auth

---

## Error: "Insufficient permissions" / "Access denied"

**Uzrok:** OAuth token nema potrebne scopeove.

**Poruka:**
```
[ERROR] Insufficient authentication scopes.
Required: https://www.googleapis.com/auth/drive
Current scopes: gmail.send, sheets
```

**Rješenje:**

```bash
# Revoke existing credentials
python tools/oauth_cli.py --revoke

# Re-authenticate and grant ALL permissions
python tools/oauth_cli.py --auth
```

**VAŽNO:** Tijekom OAuth flowa, morate odobriti SVE tražene scopeove. Ako odbijete bilo koji scope, taj API neće raditi.

**Required Scopes:**
- Gmail: `gmail.send`, `gmail.readonly`
- Drive: `drive`, `drive.file`
- Sheets: `spreadsheets`
- Calendar: `calendar`
- Contacts: `contacts`
- Tasks: `tasks`

---

# 2. Google API Errors

## Error: "404 Not Found" (Sheets, Drive)

**Uzrok:** Spreadsheet ID ili File ID ne postoji ili korisnik nema pristup.

**Poruka:**
```
[ERROR] Requested entity was not found.
Spreadsheet ID: 1ABC...XYZ not found
```

**Rješenje:**

1. **Provjerite ID:**
   - Sheets ID je iz URL-a: `https://docs.google.com/spreadsheets/d/{ID}/edit`
   - Drive ID je iz URL-a: `https://drive.google.com/file/d/{ID}/view`

2. **Provjerite pristup:**
   - Je li file shared s Google Accountom koji koristite?
   - Imate li read/write permissions?

3. **Provjerite da file nije obrisan:**
   - Check Google Drive trash
   - Restore if needed

**Debug:**

```bash
# List all spreadsheets to find correct ID
python main.py --agent analyst --query "List all my spreadsheets"

# Search Drive for file by name
python main.py --agent librarian --query "Search for file named 'Q1 Sales'"
```

---

## Error: "429 Too Many Requests" (Rate Limiting)

**Uzrok:** Prekoračili ste Google API rate limit.

**Poruka:**
```
[ERROR] Rate limit exceeded.
Quota exceeded for quota metric 'Read requests' and limit 'Read requests per user per 100 seconds'
```

**Google API Limits:**
- **Sheets:** 500 requests / 100 seconds / user
- **Gmail:** 250 emails / day (free account)
- **Drive:** 1 billion requests / day (rarely hit)

**Automatski Retry:**

Sistem automatski koristi exponential backoff retry:

```
Attempt 1: Wait 1s, retry
Attempt 2: Wait 2s, retry
Attempt 3: Wait 4s, retry
Attempt 4: Wait 8s, retry
Max: 60s wait
```

**Rješenje:**

1. **Wait it out** - Retry handler će automatski čekati
2. **Reduce request frequency** - Batch operations umjesto pojedinačnih
3. **Check quota usage:**
   - https://console.cloud.google.com/apis/dashboard
   - Project → APIs & Services → Dashboard
   - View quotas and usage

**Prevencija:**

```python
# Instead of this (100 individual writes):
for row in data:
    await sheets_update_values(spreadsheet_id, f"A{i}", [[row]])

# Do this (1 batch write):
await sheets_update_values(spreadsheet_id, "A1:Z100", all_data)
```

---

## Error: "403 Forbidden" (Permission Denied)

**Uzrok:** Korisnik nema permission za requested operaciju.

**Poruka:**
```
[ERROR] The caller does not have permission
Request had insufficient authentication scopes.
```

**Rješenje:**

1. **Re-authenticate with all scopes:**
   ```bash
   python tools/oauth_cli.py --revoke
   python tools/oauth_cli.py --auth
   ```

2. **Check file sharing settings:**
   - File mora biti shared s vašim Google Account
   - Potreban read/write access (not just view)

3. **Domain restrictions:**
   - Ako koristite Google Workspace (poslovni account), admin može ograničiti pristup external aplikacijama
   - Kontaktirajte IT admina

---

## Error: "Invalid request" (Malformed Data)

**Uzrok:** Request payload je neispavan ili ima pogrešan format.

**Poruka:**
```
[ERROR] Invalid request
Unable to parse range: 'Sheet1!A1:Z'
```

**Primjeri pogrešnih formata:**

```python
# ❌ WRONG - Missing end column
range = "Sheet1!A1:Z"

# ✅ CORRECT
range = "Sheet1!A1:Z100"

# ❌ WRONG - Invalid datetime format
start_time = "2026-02-02 10:00:00"

# ✅ CORRECT - RFC3339 format
start_time = "2026-02-02T10:00:00"

# ❌ WRONG - Email as string
attendees = "user@example.com"

# ✅ CORRECT - Email as list
attendees = ["user@example.com"]
```

**Debugging:**

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Inspect request payload before sending
print(f"Request data: {request_payload}")
```

---

# 3. Fiskalizacija Errors

## Error: "Certificate verification failed"

**Uzrok:** Problem s FINA client certifikatom.

**Poruka:**
```
[ERROR] Certificate verification failed
SSL: CERTIFICATE_VERIFY_FAILED
```

**Mogući uzroci:**
1. Certificate path je pogrešan
2. Certificate je expired
3. CA bundle ne sadrži FINA root certificate
4. Certificate nije u PEM formatu

**Rješenje:**

```bash
# 1. Check certificate validity
openssl x509 -in client_cert.pem -text -noout

# 2. Check expiration date
openssl x509 -in client_cert.pem -noout -dates
# notBefore=Jan  1 00:00:00 2024 GMT
# notAfter=Dec 31 23:59:59 2026 GMT

# 3. Verify certificate chain
openssl verify -CAfile fina_demo_ca_bundle.pem client_cert.pem
# client_cert.pem: OK

# 4. Check if files exist
ls -la client_cert.pem client_key.pem fina_demo_ca_bundle.pem
```

**Ako koristite P12 format:**

```bash
# Convert P12 to PEM
openssl pkcs12 -in certificate.p12 -clcerts -nokeys -out client_cert.pem
openssl pkcs12 -in certificate.p12 -nocerts -nodes -out client_key.pem
```

---

## Error: "Invalid OIB"

**Uzrok:** OIB broj ima pogrešan format ili checksum.

**Poruka:**
```
[ERROR] Invalid OIB: 12345
OIB must be exactly 11 digits
```

**OIB Validacija:**
- Mora biti **točno 11 znamenki**
- Mora proći ISO 7064 checksum algoritam
- Ne smije biti sve nule: `00000000000`

**Primjeri:**

```python
# ❌ WRONG - Too short
oib = "12345"

# ❌ WRONG - Contains letters
oib = "1234567890A"

# ❌ WRONG - All zeros
oib = "00000000000"

# ✅ CORRECT - 11 digits, valid checksum
oib = "12345678901"
```

**Test OIB brojevi (FINA sandbox):**
- `47814789716` - Test company OIB
- `12345678901` - Generic test OIB

---

## Error: "SOAP Fault" (FINA API Error)

**Uzrok:** FINA API je vratio grešku.

**Poruka:**
```
[ERROR] SOAP Fault from FINA API
s:gr1: Greška - račun već fiskaliziran
```

**Tipične FINA greške:**

| Greška | Uzrok | Rješenje |
|--------|-------|----------|
| `Greška - račun već fiskaliziran` | Invoice broj već postoji | Koristite novi invoice number |
| `Greška - neispravan OIB` | OIB checksum ne prolazi | Provjerite OIB validation |
| `Greška - neispravna PDV stopa` | VAT rate nije 25%, 13%, 5%, ili 0% | Koristite valjan VAT rate |
| `Greška - neispravna oznaka načina plaćanja` | Payment method nije G/K/T/O/C | Koristite valid payment method |
| `Greška - poslovno mjesto nepoznato` | Business location nije registriran | Provjerite business_location_id |

**Debugging:**

```bash
# Check logs for full SOAP request/response
cat logs/fiskalizacija.log | grep "SOAP"

# Look for FINA error codes
cat logs/fiskalizacija.log | grep "Greška"
```

**Rješenje:**

1. **Check FINA Fiskalizacija 2.0 spec** - https://www.fina.hr/fiskalizacija
2. **Validate all invoice fields** before submission
3. **Use HITL confirmation** to review data before sending
4. **Check sandbox vs production** settings

---

## Error: "Duplicate invoice prevented by ledger"

**Uzrok:** Idempotency check je pronašao da je invoice već fiskaliziran.

**Poruka:**
```
[INFO] Invoice 001/DEMO/1 already fiscalized
Existing JIR: a1b2c3d4-e5f6-7890-abcd-ef1234567890
Returning existing fiscalization data
```

**Rješenje:**

Ovo **NIJE greška** - sistem radi kako treba! Sprječava duplicate submissions.

**Ako stvarno trebate ponovno fiskalizirati:**

1. Koristite **novi invoice number**
2. Ili **obrišite ledger entry** (SAMO za testiranje):

```python
from tools.api_implementations.fiskalizacija_ledger import FiskalizacijaLedger

ledger = FiskalizacijaLedger()
await ledger.delete_invoice("001/DEMO/1")  # USE WITH CAUTION
```

**NIKAD ne brišite production ledger entries!**

---

## Error: "Missing required field"

**Uzrok:** Invoice podatak nedostaje.

**Poruka:**
```
[ERROR] Missing required field: customer_name
Invoice must include customer name for fiscalization
```

**Required Fields za fiskalizaciju:**

```python
required = [
    "invoice_number",      # e.g., "001/DEMO/1"
    "customer_name",       # e.g., "Test Kupac"
    "total_amount",        # e.g., 1875.00 (float)
    "payment_method",      # "G", "K", "T", "O", "C"
    "items"                # List of invoice items (min 1)
]

# Each item must have:
item_required = [
    "description",         # e.g., "IT Consulting"
    "quantity",            # e.g., 10 (float)
    "unit_price",          # e.g., 150.00 (float)
    "vat_rate"             # e.g., 25.0 (float)
]
```

**Rješenje:**

```python
# ❌ WRONG - Missing fields
invoice = {
    "invoice_number": "001/DEMO/1",
    "total_amount": 1875.00
}

# ✅ CORRECT - All required fields
invoice = {
    "invoice_number": "001/DEMO/1",
    "customer_name": "Test Kupac",
    "total_amount": 1875.00,
    "payment_method": "G",
    "items": [
        {
            "description": "IT Consulting",
            "quantity": 10,
            "unit_price": 150.00,
            "vat_rate": 25.0
        }
    ]
}
```

---

# 4. Network & Timeout Errors

## Error: "Connection timeout"

**Uzrok:** Network request je trajao predugo.

**Poruka:**
```
[ERROR] Request timeout after 30 seconds
Failed to connect to https://sheets.googleapis.com
```

**Uzroci:**
1. Slow internet connection
2. Google API temporarily unavailable
3. Firewall blocking request
4. Timeout threshold previše nizak

**Rješenje:**

```python
# Increase timeout (in tool implementation)
HTTP_TIMEOUT = 60  # Increase from 30 to 60 seconds

# Or retry manually
python main.py --agent analyst --query "..."
```

**Check Google API status:**
- https://status.cloud.google.com/

---

## Error: "Connection refused" / "Network unreachable"

**Uzrok:** Ne može se spojiti na API endpoint.

**Poruka:**
```
[ERROR] Connection refused
Failed to connect to cistest.apis.hr:443
```

**Mogući uzroci:**
1. No internet connection
2. Firewall blokira outgoing connections
3. Corporate proxy settings
4. VPN interference
5. API endpoint temporarily down

**Rješenje:**

```bash
# 1. Check internet connection
ping google.com

# 2. Check if endpoint is reachable
curl -I https://sheets.googleapis.com

# 3. Check proxy settings (if behind corporate firewall)
echo $HTTP_PROXY
echo $HTTPS_PROXY

# 4. Try with different network (mobile hotspot, etc.)
```

**For corporate networks:**

```python
# Configure proxy in requests
proxies = {
    'http': 'http://proxy.company.com:8080',
    'https': 'http://proxy.company.com:8080',
}

response = requests.get(url, proxies=proxies)
```

---

## Error: "Circuit breaker OPEN"

**Uzrok:** Previše uzastopnih grešaka, circuit breaker je blokirao daljnje zahtjeve.

**Poruka:**
```
[ERROR] Circuit breaker is OPEN
Too many consecutive failures (5/5)
Recovery timeout: 60 seconds
```

**Automatski Recovery:**

Circuit breaker automatski prelazi u HALF_OPEN state nakon 60 sekundi i testira da li je API dostupan.

**Rješenje:**

1. **Wait** - Circuit će se automatski zatvoriti nakon recovery timeouta
2. **Check logs** - Identifikuj root cause grešaka
3. **Fix underlying issue** - Network, credentials, API quota, etc.

```bash
# Check what caused circuit to open
grep "ERROR" logs/app.log | tail -20

# Wait for recovery
sleep 60

# Retry operation
python main.py --agent analyst --query "..."
```

**Prevencija:**
- Ensure stable network connection
- Validate credentials before mass operations
- Monitor API quotas

---

# 5. Data Validation Errors

## Error: "Invalid date format"

**Uzrok:** Datum nije u ispravnom formatu.

**Poruka:**
```
[ERROR] Invalid datetime format
Expected RFC3339: '2026-02-02T10:00:00' or '2026-02-02T10:00:00Z'
Received: '2026-02-02 10:00:00'
```

**Ispravni formati:**

```python
# ✅ CORRECT - ISO 8601 / RFC3339
"2026-02-02T10:00:00"           # Local time
"2026-02-02T10:00:00Z"          # UTC time
"2026-02-02T10:00:00+01:00"     # With timezone

# ❌ WRONG - Space instead of T
"2026-02-02 10:00:00"

# ❌ WRONG - Missing time
"2026-02-02"

# ❌ WRONG - US format
"02/02/2026"
```

**Konverzija:**

```python
from datetime import datetime

# Convert to RFC3339
dt = datetime.now()
rfc3339 = dt.isoformat()  # "2026-02-02T14:30:00"

# Parse from string
dt = datetime.fromisoformat("2026-02-02T10:00:00")
```

---

## Error: "Invalid email format"

**Uzrok:** Email adresa nije u validnom formatu.

**Poruka:**
```
[ERROR] Invalid email address: 'user@'
Must match format: user@domain.com
```

**Validacija:**

```python
import re

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# ✅ Valid
is_valid_email("user@example.com")        # True
is_valid_email("test.user@domain.co.uk")  # True

# ❌ Invalid
is_valid_email("user@")                   # False
is_valid_email("@domain.com")             # False
is_valid_email("user domain.com")         # False
```

---

## Error: "Amount must be positive"

**Uzrok:** Negativan iznos gdje se očekuje pozitivan.

**Poruka:**
```
[ERROR] Invalid amount: -100.00
Invoice amounts must be positive numbers
```

**Validacija:**

```python
# ✅ CORRECT
amount = 1500.00
if amount > 0:
    proceed()

# ❌ WRONG - Allows negative or zero
amount = -50.00
```

---

# 6. Agent Execution Errors

## Error: "Agent not found"

**Uzrok:** Traženi agent nije registriran.

**Poruka:**
```
[ERROR] Agent 'unknown_agent' not found
Available agents: smart_orchestrator, analyst, librarian, secretary, ...
```

**Rješenje:**

```bash
# List available agents
python main.py --list-agents

# Use correct agent name
python main.py --agent analyst --query "..."
```

**Available Agents:**
- `smart_orchestrator` - Multi-agent coordination
- `analyst` - Google Sheets operations
- `librarian` - Google Drive operations
- `secretary` - Google Calendar operations
- `rolodex` - Google Contacts operations
- `tracker` - Google Tasks operations
- `mailer` - Gmail operations
- `fiskalizacija` - Croatian fiscalization

---

## Error: "Agent execution timeout"

**Uzrok:** Agent je trajao predugo.

**Poruka:**
```
[ERROR] Agent execution timeout after 300 seconds
Agent: analyst
Query: Complex calculation on large dataset
```

**Rješenje:**

1. **Simplify query** - Break into smaller tasks
2. **Increase timeout:**

```python
# In agent configuration
AGENT_TIMEOUT = 600  # Increase from 300 to 600 seconds
```

3. **Optimize operation** - Use batch operations instead of loops

---

## Error: "Tool execution failed"

**Uzrok:** Agent tool je vratio grešku.

**Poruka:**
```
[ERROR] Tool execution failed: sheets_read_values
Error: Spreadsheet not found
```

**Debugging:**

```bash
# Check agent logs
cat logs/agent_execution.log | grep "ERROR"

# Check tool-specific logs
cat logs/app.log | grep "sheets_read_values"
```

**Rješenje:**
- Provjerite da su tool parametri ispravni
- Validirajte IDs (spreadsheet_id, file_id, etc.)
- Ensure user has permissions

---

# 7. File System Errors

## Error: "File not found"

**Uzrok:** File ne postoji na specified path.

**Poruka:**
```
[ERROR] File not found: /path/to/invoice.pdf
No such file or directory
```

**Rješenje:**

```bash
# Check if file exists
ls -la /path/to/invoice.pdf

# Use absolute path instead of relative
python main.py --file "C:\Users\...\invoice.pdf"

# Check current working directory
pwd  # Linux/Mac
cd   # Windows
```

---

## Error: "Permission denied" (File System)

**Uzrok:** Nemate permission za read/write file.

**Poruka:**
```
[ERROR] Permission denied: /protected/folder/file.txt
```

**Rješenje:**

```bash
# Linux/Mac - Check permissions
ls -la /protected/folder/file.txt

# Fix permissions (if you own the file)
chmod 644 file.txt

# Windows - Run as Administrator or check folder permissions
```

---

# Debugging Strategies

## 1. Enable Debug Logging

```python
import logging

# Set to DEBUG level
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

**What you'll see:**
- All API requests and responses
- Tool parameter values
- Agent decision-making process
- Retry attempts
- Circuit breaker state changes

---

## 2. Inspect API Responses

```python
# Add debug print in tool functions
async def sheets_read_values(spreadsheet_id, range):
    result = await api_call()
    print(f"[DEBUG] API Response: {result}")  # Add this
    return result
```

**Look for:**
- Actual vs expected response structure
- Error messages from API
- Missing fields

---

## 3. Use Test Mode

```python
# Enable test mode to prevent actual operations
TEST_MODE = True

if TEST_MODE:
    print(f"[TEST] Would send email to: {recipient}")
    return {"status": "test_success"}
else:
    # Actually send email
    return await send_email(recipient, subject, body)
```

---

## 4. Isolate the Problem

```bash
# Test individual components

# 1. Test OAuth credentials
python tools/oauth_cli.py --check

# 2. Test single API operation
python -c "
from tools.adk_tools.sheets_adk_tools import sheets_list_spreadsheets
import asyncio
result = asyncio.run(sheets_list_spreadsheets())
print(result)
"

# 3. Test agent individually
python main.py --agent analyst --query "List my spreadsheets"

# 4. Test full orchestration
python main.py --agent smart_orchestrator --query "Complex multi-step task"
```

---

## 5. Check System Resources

```bash
# Check disk space
df -h

# Check memory usage
free -m  # Linux
# Task Manager - Performance tab (Windows)

# Check network connectivity
ping google.com
curl -I https://sheets.googleapis.com
```

---

## 6. Review Recent Changes

```bash
# Check git history
git log --oneline -10

# See what changed
git diff HEAD~1

# Revert to previous version if needed
git checkout HEAD~1 -- path/to/file.py
```

---

# Log Analysis

## Common Log Patterns

### Success Pattern

```
[INFO] Agent: analyst
[INFO] Query: List all spreadsheets
[INFO] Tool: sheets_list_spreadsheets
[DEBUG] API Response: {'spreadsheets': [...], 'status': 'success'}
[INFO] Result: Found 5 spreadsheets
[INFO] Execution time: 1.2s
```

### Failure Pattern

```
[INFO] Agent: analyst
[INFO] Query: Read non-existent sheet
[ERROR] Tool: sheets_read_values
[ERROR] API Response: {'error': 'Not found', 'status': 404}
[ERROR] Exception: Spreadsheet not found
[ERROR] Execution failed after 0.5s
```

### Retry Pattern

```
[WARNING] API call failed: Rate limit exceeded
[INFO] Retry attempt 1/3 after 1.0s
[WARNING] API call failed: Rate limit exceeded
[INFO] Retry attempt 2/3 after 2.0s
[INFO] API call successful on retry attempt 2
```

---

## Log Locations

```
logs/
├── app.log                    # Main application log
├── fiskalizacija.log          # Fiskalizacija operations
└── agent_execution.log        # Agent execution traces
```

**Real-time monitoring:**

```bash
# Linux/Mac
tail -f logs/app.log

# Windows PowerShell
Get-Content logs/app.log -Wait -Tail 50
```

**Search logs:**

```bash
# Find all errors
grep "ERROR" logs/app.log

# Find specific operation
grep "fiskalizacija" logs/app.log

# Find within time range
grep "2026-02-02 14:" logs/app.log
```

---

# Recovery Procedures

## Scenario 1: OAuth Credentials Corrupted

```bash
# 1. Backup existing tokens (optional)
cp ~/.google_workspace_adk/tokens.json ~/.google_workspace_adk/tokens.json.backup

# 2. Revoke and re-authenticate
python tools/oauth_cli.py --revoke
python tools/oauth_cli.py --auth

# 3. Verify
python tools/oauth_cli.py --check
```

---

## Scenario 2: Persistent API Failures

```bash
# 1. Check API status
curl https://status.cloud.google.com/

# 2. Wait for recovery (if API is down)
sleep 300  # 5 minutes

# 3. Clear circuit breaker state (restart application)
# Circuit breaker state is in-memory, restart clears it

# 4. Retry operation
python main.py --agent analyst --query "..."
```

---

## Scenario 3: Fiskalizacija Certificate Expired

```bash
# 1. Check expiration
openssl x509 -in client_cert.pem -noout -dates

# 2. Obtain new certificate from FINA
# (Follow FINA's certificate renewal process)

# 3. Convert to PEM if needed
openssl pkcs12 -in new_cert.p12 -clcerts -nokeys -out client_cert.pem
openssl pkcs12 -in new_cert.p12 -nocerts -nodes -out client_key.pem

# 4. Update config/company_config.py paths

# 5. Test with sandbox
python test_fiskalizacija_e2e.py
```

---

## Scenario 4: Database Ledger Corruption

```bash
# If Firestore ledger has issues:

# 1. Check Firestore console
# https://console.firebase.google.com/

# 2. Verify credentials
echo $GOOGLE_APPLICATION_CREDENTIALS

# 3. Test connection
python -c "
from tools.api_implementations.fiskalizacija_ledger import FiskalizacijaLedger
ledger = FiskalizacijaLedger()
print('Ledger connection OK')
"

# 4. If corrupted, manually fix in Firestore console
# Or re-create collection
```

---

# Getting Help

## 1. Check Documentation

- [CLI_WORKFLOW_GUIDE.md](CLI_WORKFLOW_GUIDE.md) - Basic usage
- [ENVIRONMENT_CONFIGURATION.md](ENVIRONMENT_CONFIGURATION.md) - Configuration options
- This guide - Error handling

---

## 2. Search Issues

```bash
# Check if error is already known
grep -r "your error message" docs/

# Search git history
git log --all --grep="error keyword"
```

---

## 3. Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run operation again and capture full output
python main.py --agent analyst --query "..." > debug.log 2>&1
```

---

## 4. Provide Debug Information

When reporting issues, include:

1. **Error message** (full stack trace)
2. **Command that failed** (exact command)
3. **Relevant logs** (last 50 lines)
4. **Environment info:**
   - OS version
   - Python version
   - Package versions: `pip list | grep google`
5. **What you already tried**

Example:

```
Error: Spreadsheet not found

Command:
python main.py --agent analyst --query "Read sheet X"

Logs:
[ERROR] Spreadsheet ID not found: 1ABC...XYZ

Environment:
- Windows 11
- Python 3.11.5
- google-api-python-client 2.108.0

Tried:
- Verified spreadsheet ID
- Checked OAuth permissions
- Tested with different spreadsheet
```

---

# Quick Reference: Common Fixes

| Error | Quick Fix |
|-------|-----------|
| No OAuth credentials | `python tools/oauth_cli.py --auth` |
| Token expired | `python tools/oauth_cli.py --refresh` |
| Permission denied | `python tools/oauth_cli.py --revoke && python tools/oauth_cli.py --auth` |
| Rate limit | Wait 60s, use batch operations |
| Certificate error | Check cert expiry: `openssl x509 -in client_cert.pem -noout -dates` |
| Network timeout | Increase timeout, check internet connection |
| Circuit breaker OPEN | Wait 60s, check logs for root cause |
| File not found | Use absolute paths, check file exists |
| Invalid format | Check RFC3339 for dates, validate emails |
| Agent not found | `python main.py --list-agents` |

---

**Zadnje ažurirano:** 02.02.2026
**Verzija:** 1.0
**Status:** Production-ready
