# 🧪 TESTING SETUP GUIDE

## ✅ PRIJE POKRETANJA TESTOVA - CHECKLIST

### 1️⃣ **Python Setup**
```bash
# Provjeri Python verziju (potreban Python 3.11+)
python --version

# Ako Python nije u PATH, dodaj ga ili koristi puni path
```

### 2️⃣ **Instalacija Dependencies**
```bash
# Instaliraj sve dependencies
pip install -r requirements.txt

# ILI ako imaš poetry/pipenv
poetry install
# pipenv install
```

**VAŽNO:** Potrebni packages za testove:
- `pytest>=7.4.0`
- `pytest-asyncio>=0.21.0`
- Svi ostali iz `requirements.txt`

### 3️⃣ **Environment Setup**
✅ **`.env` fajl je već kreiran!**

Minimalni setup (već u `.env`):
```env
ENVIRONMENT=test
LOG_LEVEL=DEBUG
GEMINI_MODEL_FLASH=gemini-1.5-flash
GEMINI_MODEL_PRO=gemini-1.5-pro
SESSION_STORAGE=memory
```

**NAPOMENA:** Testovi koriste **MOCK servere**, ne trebaju pravi API ključevi! 🎉

---

## 🚀 POKRETANJE TESTOVA

### **Brzo testiranje - Provjeri da li radi:**
```bash
# Test jedan jednostavan fajl
pytest tests/unit/test_agents.py -v

# Ako radi - Super! Sve je podešeno! ✅
```

### **Pokretanje svih testova:**
```bash
# SVE testove (463 testa)
pytest

# Sa verbose output
pytest -v

# Sa coverage reportom
pytest --cov=. --cov-report=html --cov-report=term

# Samo unit testovi (brzi)
pytest -m unit

# Samo integration testovi
pytest -m integration

# Samo E2E testovi
pytest tests/e2e/
```

### **Pokretanje specifičnih testova:**
```bash
# Test REAL agent implementacija
pytest tests/integration/test_real_agents.py -v

# Test REAL custom tools
pytest tests/integration/test_real_custom_tools.py -v

# Test Mailer + Gmail MCP
pytest tests/integration/test_mailer_with_gmail_mcp.py -v

# Test Auth Managers
pytest tests/unit/test_real_auth_managers.py -v

# Test Session Service
pytest tests/unit/test_real_session_service.py -v

# Test User Workflows (E2E)
pytest tests/e2e/test_real_user_workflows.py -v
```

---

## 📊 ŠTA TESTOVI POKRIVAJU

### ✅ **Testovi koji NE TREBAJU API ključeve (svi rade odmah!):**

| Test File | Što testira | Broj testova |
|-----------|-------------|--------------|
| `test_real_agents.py` | PRAVE Agent klase (10 agenata) | ~150 |
| `test_real_custom_tools.py` | PRAVE Custom Tools (formatiranje, konverzije) | ~60 |
| `test_mailer_with_gmail_mcp.py` | REAL Agents + Mock MCP serveri | ~40 |
| `test_real_auth_managers.py` | REAL Auth Manager klase | ~50 |
| `test_real_session_service.py` | REAL Session Service klase | ~50 |
| `test_real_user_workflows.py` | REAL E2E workflows | ~30 |
| `test_agents.py` | Unit testovi agenata | ~20 |
| `test_*.py` (ostali) | Drugi unit/integration testovi | ~63 |
| **TOTAL** | | **463 testova** |

### 🟡 **Testovi koji TREBAJU API ključeve (preskoči za sada):**
- Ako test sadrži `@pytest.mark.requires_auth` - preskoči ga
- Ako test sadrži `@pytest.mark.requires_network` - preskoči ga

```bash
# Preskoči testove koji trebaju auth
pytest -m "not requires_auth"
```

---

## 🎯 OČEKIVANI REZULTATI

### ✅ **Ako sve radi:**
```
============================= test session starts =============================
collected 463 items

tests/unit/test_agents.py::TestAgentInitialization::test_mailer_init PASSED
tests/unit/test_agents.py::TestAgentInitialization::test_librarian_init PASSED
...
tests/integration/test_real_agents.py::TestOrchestratorAgent::test_orchestrator_initialization PASSED
...

============================= 463 passed in 15.32s =============================
```

### 🟡 **Ako neki testovi fail (OK za početak):**
```
============================= test session starts =============================
...
FAILED tests/some_test.py::test_something - ImportError: Missing module
...
============================= 450 passed, 13 failed in 18.45s ==================
```

**Razlozi za failures:**
- Missing dependencies (instaliraj: `pip install <package>`)
- Missing instruction files (provjeri `agents/*/instructions.md`)
- Import errors (provjeri PYTHONPATH)

---

## 🔧 TROUBLESHOOTING

### ❌ **Problem: `ModuleNotFoundError: No module named 'agents'`**
```bash
# Rješenje: Dodaj project root u PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"  # Linux/Mac
set PYTHONPATH=%PYTHONPATH%;%cd%          # Windows CMD
$env:PYTHONPATH="$env:PYTHONPATH;$(pwd)"  # Windows PowerShell

# ILI instaliraj projekat u editable mode
pip install -e .
```

### ❌ **Problem: `pytest: command not found`**
```bash
# Instaliraj pytest
pip install pytest pytest-asyncio

# ILI koristi python -m
python -m pytest
```

### ❌ **Problem: `Instruction file not found`**
```bash
# Provjeri da li instruction fajlovi postoje
ls agents/*/instructions.md

# Ako nedostaju, kreiraj ih:
# agents/mailer/instructions.md
# agents/librarian/instructions.md
# etc.
```

### ❌ **Problem: Testovi prolaze ali WARNINGS**
```bash
# Ignoriši warnings (već konfigurirano u pytest.ini)
pytest --disable-warnings
```

---

## 🎉 NAKON USPJEŠNOG SETUP-A

Ako sve radi:
1. ✅ 463 testova (ili većina) prolazi
2. ✅ Coverage report generiran (ako koristiš --cov)
3. ✅ Možeš dodavati nove testove
4. ✅ CI/CD može pokrenuti testove automatski

**Production-ready! 🚀**

---

## 📚 DODATNO (Napredno)

### **Continuous Integration (CI/CD):**
GitHub Actions već konfigurirano u `.github/workflows/test.yml`

### **Pre-commit hooks:**
```bash
# Pokreni testove prije svakog commit-a
pip install pre-commit
pre-commit install
```

### **Coverage threshold:**
```bash
# Zahtijevaj minimum 60% coverage
pytest --cov=. --cov-fail-under=60
```

---

## 📞 POMOĆ

Ako imaš problema:
1. Provjeri `pytest.ini` konfiguraciju
2. Provjeri `tests/conftest.py` fixtures
3. Pokreni unit testove prvo (najbrži, najsigurniji)
4. Postupno dodaj integration i E2E testove

**Testovi koriste MOCK servere - ne bi trebalo biti problema! ✅**
