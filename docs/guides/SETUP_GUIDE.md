# 🚀 SETUP GUIDE - Google Workspace ADK

Kompletni vodič za postavljanje i pokretanje sistema.

---

## ✅ IMPLEMENTIRAN SUSTAV

### Što je kompletno implementirano:

#### 1. **Tool Registry & Execution Engine** ✅
- `tools/tool_registry.py` - Centralni registry za sve tool funkcije
- Dinamička registracija i izvršavanje tool-ova
- Parameter validacija
- Error handling

#### 2. **Google API Client** ✅
- `tools/google_api_client.py` - Base wrapper za Google APIs
- Automatska credential management
- Service caching
- Support za sve Google Workspace APIs

#### 3. **Real API Implementations** ✅
- **Gmail API** (`tools/api_implementations/gmail_api.py`)
  - `gmail_search_threads` - Pretraga emailova
  - `gmail_get_thread` - Dohvaćanje cijelog thread-a
  - `gmail_send_message` - Slanje emaila
  - `gmail_create_draft` - Kreiranje drafta
  - `gmail_modify_thread` - Modificiranje labela
  - `gmail_list_labels` - Lista svih labela

- **Drive API** (`tools/api_implementations/drive_api.py`)
  - `drive_search_files` - Pretraga datoteka
  - `drive_get_file` - Dohvaćanje datoteke
  - `drive_upload_file` - Upload datoteke
  - `drive_update_file` - Update datoteke
  - `drive_delete_file` - Brisanje datoteke
  - `drive_share_file` - Dijeljenje datoteke
  - `drive_create_folder` - Kreiranje foldera
  - `drive_move_file` - Premještanje datoteke

- **Calendar API** (`tools/api_implementations/calendar_api.py`)
  - `calendar_list_events` - Lista događaja
  - `calendar_get_event` - Dohvaćanje događaja
  - `calendar_create_event` - Kreiranje događaja
  - `calendar_update_event` - Update događaja
  - `calendar_delete_event` - Brisanje događaja

#### 4. **OAuth CLI Flow** ✅
- `tools/oauth_cli.py` - Command-line OAuth authorization
- Local callback server
- Token storage i refresh
- Token revocation

#### 5. **Integration** ✅
- `base_agent._execute_tool` povezan s tool registry
- Automatska tool initialization
- Credential management u tool execution

---

## 📋 SETUP KORACI

### Korak 1: Environment Varijable

Kreiraj `.env` file ili ažuriraj postojeći:

```bash
# Google API Key (za Gemini modele)
GOOGLE_API_KEY=your-gemini-api-key

# OAuth 2.0 Credentials (za Google Workspace APIs)
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/oauth2callback

# Gemini Models
GEMINI_MODEL_FLASH=gemini-1.5-flash
GEMINI_MODEL_PRO=gemini-1.5-pro

# Session Storage
SESSION_STORAGE=memory

# Environment
ENVIRONMENT=development
```

### Korak 2: Instaliraj Dependencies

```bash
pip install -r requirements.txt
```

Ključni paketi:
- `google-generativeai` - Gemini AI
- `google-auth` - Google authentication
- `google-auth-oauthlib` - OAuth flow
- `google-auth-httplib2` - HTTP transport
- `google-api-python-client` - Google APIs
- `python-dotenv` - Environment variables

### Korak 3: OAuth Authorization

#### 3.1 Dobij OAuth Credentials

1. Idi na [Google Cloud Console](https://console.cloud.google.com/)
2. Kreiraj novi projekt ili odaberi postojeći
3. Enable Google Workspace APIs:
   - Gmail API
   - Google Drive API
   - Google Calendar API
   - Google Docs API
   - Google Sheets API
   - People API (Contacts)
   - Google Tasks API

4. Konfiguriraj OAuth consent screen:
   - User Type: External (za testing)
   - Add scopes:
     - Gmail: `https://www.googleapis.com/auth/gmail.modify`
     - Drive: `https://www.googleapis.com/auth/drive`
     - Calendar: `https://www.googleapis.com/auth/calendar`
     - itd.

5. Kreiraj OAuth 2.0 Client ID:
   - Application type: Web application
   - Authorized redirect URIs: `http://localhost:8080/oauth2callback`
   - Download credentials (JSON)

#### 3.2 Pokreni OAuth Flow

```bash
python tools/oauth_cli.py --auth
```

Ovo će:
1. Otvoriti browser za authorization
2. Pokrenuti lokalni callback server
3. Spremiti OAuth token u `~/.google_workspace_adk/tokens.json`

#### 3.3 Provjeri Status

```bash
python tools/oauth_cli.py --status
```

---

## 🧪 TESTIRANJE

### Test 1: Full Implementation Test

```bash
python test_full_implementation.py
```

Ovaj test provjerava:
- ✓ Tool Registry initialization
- ✓ API Implementations registration
- ✓ OAuth Manager
- ✓ Google API Client
- ✓ Base Agent tool execution
- ✓ Agent Registry
- ✓ Orchestrator routing

**Očekivani rezultat:**
```
Passed: 7/7
Success Rate: 100%
✓✓✓ ALL TESTS PASSED! ✓✓✓
```

### Test 2: Tool Registry Initialization

```bash
python tools/initialize_tools.py
```

Testira registraciju svih API tool-ova.

### Test 3: Interactive System Test

```bash
python main.py
```

Testni upiti:
```
You: List my Gmail labels
You: Find files in my Google Drive
You: Show my calendar events for today
```

---

## 🔧 KAKO RADI TOOL EXECUTION

### 1. Agent Prima Zahtjev
```python
user_request = "List my last 5 emails"
result = await agent.run(user_request)
```

### 2. LLM Odlučuje Koristiti Tool
Gemini model vraća `function_call`:
```json
{
  "name": "gmail_search_threads",
  "args": {
    "query": "in:inbox",
    "max_results": 5
  }
}
```

### 3. Base Agent Izvršava Tool
```python
# base_agent.py
async def _execute_tool(self, tool_name, args):
    # Dohvati tool registry
    tool_registry = get_tool_registry()

    # Dohvati credentials
    api_client = create_api_client_auto()
    credentials = api_client.credentials

    # Izvršava tool
    result = await tool_registry.execute_tool(
        tool_name=tool_name,
        args=args,
        credentials=credentials
    )

    return result
```

### 4. Tool Registry Poziva API Implementaciju
```python
# tools/tool_registry.py
async def execute_tool(self, tool_name, args, credentials):
    tool_def = self._tools[tool_name]

    # Poziva pravu funkciju
    result = await tool_def.function(
        credentials=credentials,
        **args
    )

    return result
```

### 5. API Implementacija Izvršava Google API Poziv
```python
# tools/api_implementations/gmail_api.py
async def gmail_search_threads(credentials, query, max_results):
    api_client = GoogleAPIClient(credentials=credentials)
    service = api_client.gmail_service()

    # Stvarni Gmail API poziv
    results = service.users().threads().list(
        userId='me',
        q=query,
        maxResults=max_results
    ).execute()

    return results
```

### 6. Rezultat Se Vraća LLM-u
LLM prima rezultat i generirac odgovor za korisnika.

---

## 📊 ARHITEKTURA

```
User Request
     ↓
Orchestrator Agent (LLM routing)
     ↓
Specialized Agent (Gmail, Drive, Calendar, itd.)
     ↓
BaseAgent.run() (Multi-turn tool calling loop)
     ↓
BaseAgent._execute_tool()
     ↓
Tool Registry.execute_tool()
     ↓
API Implementation (gmail_api.py, drive_api.py, itd.)
     ↓
Google API Client (credentials + service)
     ↓
Google Workspace API (Gmail, Drive, Calendar, itd.)
     ↓
Response → LLM → User
```

---

## 🎯 SLJEDEĆI KORACI

### Za Production:

1. **Implementiraj Preostale APIs** (Docs, Sheets, Contacts, Tasks)
   - Copy pattern iz `gmail_api.py`
   - Registriraj u tool registry

2. **Error Handling Improvements**
   - Retry logic za API pozive
   - Circuit breakers
   - Rate limiting

3. **Monitoring & Logging**
   - Integracija s monitoring sustavom
   - API usage tracking
   - Performance metrics

4. **Testing**
   - Unit tests za sve API funkcije
   - Integration tests
   - E2E tests s pravim API pozivima

5. **Security**
   - Secure token storage (encryption)
   - Secret management (Google Secret Manager)
   - Permission validation

---

## 🐛 TROUBLESHOOTING

### Problem: "No authentication available"

**Rješenje:**
```bash
python tools/oauth_cli.py --auth
```

### Problem: "Tool not found in registry"

**Rješenje:**
Provjeri da su tool-ovi inicijalizirani:
```bash
python tools/initialize_tools.py
```

### Problem: "API quota exceeded"

**Rješenje:**
- Pričekaj nekoliko minuta
- Provjeri quota na Google Cloud Console
- Implementiraj rate limiting

### Problem: "Invalid credentials"

**Rješenje:**
```bash
python tools/oauth_cli.py --revoke
python tools/oauth_cli.py --auth
```

---

## 📞 KONTAKT & SUPPORT

Za pitanja ili probleme:
- Provjeri dokumentaciju: `ANALIZA_SUSTAVA.md`
- Provjeri test results: `python test_full_implementation.py`
- Kontaktiraj developera

---

**Status:** ✅ IMPLEMENTACIJA KOMPLETNA (Tool Execution Framework)

**Verzija:** 2.0

**Datum:** 2025-11-25
