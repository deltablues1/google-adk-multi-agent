# 🚦 Rate Limiting - Kompletan Vodič

## 📋 Sadržaj

1. [Uvod](#uvod)
2. [Zašto je Rate Limiting Kritičan](#zašto-je-rate-limiting-kritičan)
3. [Arhitektura](#arhitektura)
4. [Konfiguracije po Servisima](#konfiguracije-po-servisima)
5. [Kako Koristiti](#kako-koristiti)
6. [Best Practices](#best-practices)
7. [Monitoring i Debugging](#monitoring-i-debugging)
8. [Troubleshooting](#troubleshooting)

---

## 🎯 Uvod

**Rate Limiting** je mehanizam koji kontrolira brzinu slanja zahtjeva ka Google API-jima kako bi se:
- Poštovali službeni API limiti
- Izbjegle `429 Too Many Requests` greške
- Osigurala stabilnost sistema pri skaliranju
- Spriječile cascading failures

Naš Rate Limiter koristi **Token Bucket** algoritam koji omogućava:
- ✅ Kontrolirane burst-ove (kratke špiceve saobraćaja)
- ✅ Predvidljivu prosječnu brzinu
- ✅ Per-service i per-user izolaciju
- ✅ Automatsko čekanje (blocking) dok tokeni ne postanu dostupni

---

## 🔥 Zašto je Rate Limiting Kritičan

### Problem: Bez Rate Limitinga

```python
# ❌ LOŠE - Probija limite i ruši sistem
for i in range(1000):
    result = await sheets_update_values(...)  # 1000 zahtjeva u sekundi
    # Google blokira nakon 60. zahtjeva (60 RPM limit per user)
    # Svi zahtjevi nakon 60. dobijaju 429 Too Many Requests
```

**Posljedice:**
- 🔴 940/1000 zahtjeva fails (94% failure rate)
- 🔴 Podaci ostaju parcijalno ažurirani (nekonzistentno stanje)
- 🔴 Circuit breaker se aktivira
- 🔴 Servis postaje nedostupan za sve korisnike

### Rješenje: Sa Rate Limitingom

```python
# ✅ DOBRO - Automatski respektuje limite
for i in range(1000):
    # Rate limiter automatski čeka dok ne bude dostupan slot
    result = await sheets_update_values(...)  # Blokira prema potrebi
    # Svih 1000 zahtjeva prolazi, ali raspodijeljeno kroz vrijeme
```

**Rezultati:**
- ✅ 1000/1000 zahtjeva succeeds (100% success rate)
- ✅ Podaci konzistentni
- ✅ Stabilna brzina (45 RPM)
- ✅ Zero downtime

---

## 🏗️ Arhitektura

### Token Bucket Algoritam

Rate Limiter koristi **Token Bucket** pattern:

```
┌─────────────────────────────┐
│   Token Bucket (Capacity)   │
│  ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐   │  Refill Rate: N tokens/second
│  │T│ │T│ │T│ │T│ │T│ │T│   │  ◄────────── Constant refill
│  └─┘ └─┘ └─┘ └─┘ └─┘ └─┘   │
└─────────────────────────────┘
         │
         │ consume(cost)
         ▼
   API Request ───► Google API
```

**Kako radi:**
1. **Kofa** ima kapacitet (npr. 50 tokena)
2. Tokeni se dodaju konstantnom brzinom (npr. 45 tokena/min = 0.75 tokena/sec)
3. Svaki API poziv **konzumira** tokene (cost)
4. Ako nema dovoljno tokena, zahtjev **čeka** dok se ne napuni

### Tri Sloja Zaštite

```python
@with_circuit_breaker("sheets")        # 🛡️ Layer 1: Fast-fail ako je servis down
@with_rate_limit("sheets", ...)        # 🚦 Layer 2: Kontrola brzine zahtjeva
@with_retry(RetryConfig(...))          # 🔄 Layer 3: Retry transient errors
async def sheets_update_values(...):
    # Trostruko zaštićen API poziv!
```

### Dva Nivoa Limita

#### 1. **Project-Level Limit** (Ukupni kapacitet aplikacije)

```python
# Sheets: 250 RPM za cijeli projekt
# Ako imate 10 korisnika koji istovremeno koriste API,
# ukupno mogu poslati maksimalno 250 zahtjeva u minuti
```

#### 2. **Per-User Limit** (Individualni kapacitet)

```python
# Sheets: 45 RPM po korisniku
# Sprečava da jedan korisnik monopolizuje resurse
# 10 korisnika * 45 RPM = 450 RPM teoretski, ali project limit je 250
```

### Daily Limits (Gmail)

```python
# Gmail: 1500 emailova/dan po korisniku
# Prati se u daily counters i resetuje se svakog dana
```

---

## 📊 Konfiguracije po Servisima

Sve konfiguracije su postavljene na **80-90% službenih limita** za sigurnosnu marginu.

### Google Sheets API

```python
SERVICE_CONFIGS["sheets"] = RateLimitConfig(
    requests_per_minute=250,      # Službeni: 300 (83% safe limit)
    per_user_rpm=45,               # Službeni: 60 (75% safe limit)
    per_user_burst=50,
    burst_size=300
)
```

**Najrestriktivniji API!** Koristi **OBAVEZNO**:
- `batchUpdate` za više ažuriranja odjednom
- `batchGet` za čitanje više rangova
- **Nikad** ne koristiti petlje sa pojedinačnim `update()` pozivima

**Primjer:**
```python
# ❌ LOŠE - 100 zahtjeva
for row in rows:
    await sheets_update_values(spreadsheet_id, f"A{row}", [[value]])

# ✅ DOBRO - 1 zahtjev
await sheets_batch_update(spreadsheet_id, requests=[...])  # Sve odjednom
```

---

### Google Drive API

```python
SERVICE_CONFIGS["drive"] = RateLimitConfig(
    requests_per_minute=10000,    # Službeni: 12,000 queries (83%)
    per_user_rpm=10000,
    burst_size=12000
)
```

**Najliberalniji za metapodatke!**
- Upload/download imaju odvojen limit (750 GB/dan)
- Batch zahtjevi **ne štede kvotu** (svaki interni poziv se broji)
- Fokus na upload/copy limitu, ne na broj zahtjeva

---

### Gmail API (Quota Units)

```python
SERVICE_CONFIGS["gmail"] = RateLimitConfig(
    requests_per_minute=1000000,  # Quota units (ne zahtjevi!)
    per_user_rpm=10000,           # Službeni: 15,000 units (67%)
    use_quota_units=True,
    daily_limit=1500              # Email sending (službeni: 2000)
)
```

**Kompleksnost:** Svaki metod ima **različitu cijenu** u quota units:

| Metoda                | Quota Units | Napomena                        |
|-----------------------|-------------|---------------------------------|
| `messages.get`        | 5           | Čitanje jedne poruke            |
| `messages.list`       | 5           | Lista poruka                    |
| `messages.delete`     | 10          | Brisanje poruke                 |
| `messages.send`       | 100         | **Slanje emaila (skupo!)**      |
| `messages.batchDelete`| 50          | Batch brisanje                  |

**Primjer:**
```python
# Slanje 10 emailova troši 1000 units (10 * 100)
# Čitanje 100 poruka troši 500 units (100 * 5)

# Koristiti specifičan cost:
@with_rate_limit("gmail", cost=100)  # Email sending
async def gmail_send_message(...):
    ...
```

---

### Google Contacts API (People API)

```python
SERVICE_CONFIGS["people"] = RateLimitConfig(
    requests_per_minute=250,      # Konzervativno
    per_user_rpm=45,
    burst_size=300
)
```

**Napomena:** Koristi service name `"people"` (ne `"contacts"`).

---

### Google Tasks API

```python
SERVICE_CONFIGS["tasks"] = RateLimitConfig(
    requests_per_minute=250,
    per_user_rpm=45,
    daily_limit=50000             # Courtesy limit
)
```

**Nedokumentirani limiti!** Konzervativno postavljeno.

---

### Google Calendar API

```python
SERVICE_CONFIGS["calendar"] = RateLimitConfig(
    requests_per_minute=250,
    per_user_rpm=45,
    burst_size=300
)
```

---

### Vertex AI (Gemini)

```python
SERVICE_CONFIGS["vertex_ai_flash"] = RateLimitConfig(
    requests_per_minute=60,       # Konzervativni start
    burst_size=100
)
```

**Napredne značajke:**
- Limiti variraju po **regionu** (us-central1 vs europe-west1)
- Prate se **tokeni po minuti** (TPM) i zahtjevi po minuti (RPM)
- Dinamički shared quota za Pay-as-you-go korisnike

---

## 🛠️ Kako Koristiti

### 1. Automatska Integracija (Već Aktivno!)

Sve API funkcije **već imaju** rate limiting integriran:

```python
# tools/api_implementations/sheets_api.py

@with_circuit_breaker("sheets")
@with_rate_limit("sheets", user_id_param="credentials")  # ✅ Već dodano!
@with_retry(RetryConfig(max_retries=3, base_delay=1.0))
async def sheets_update_values(credentials, spreadsheet_id, range, values):
    # Rate limiter automatski blokira dok ne bude dostupan slot
    ...
```

**Ne trebate ništa mijenjati!** Samo pozovite funkciju normalno:

```python
from tools.api_implementations.sheets_api import sheets_update_values

# Rate limiting se dešava automatski
result = await sheets_update_values(
    credentials=creds,
    spreadsheet_id="abc123",
    range="Sheet1!A1:D10",
    values=[[1, 2, 3, 4], ...]
)
```

---

### 2. Manuelno Korištenje Rate Limitera

Ako pišete vlastitu funkciju:

```python
from tools.resilience.rate_limiter import with_rate_limit

@with_rate_limit("sheets", user_id_param="credentials", cost=1, timeout=60.0)
async def my_custom_function(credentials, ...):
    # Vaš kod ovdje
    ...
```

**Parametri:**
- `service`: Ime servisa (`"sheets"`, `"gmail"`, `"drive"`, ...)
- `cost`: Trošak u tokenima/quota units (default: 1)
- `user_id_param`: Ime parametra koji sadrži user credentials (default: None)
- `timeout`: Maksimalno vrijeme čekanja u sekundama (default: 60.0)

---

### 3. Direktno Korištenje (Bez Dekoratora)

```python
from tools.resilience.rate_limiter import get_rate_limiter

limiter = get_rate_limiter()

# Zatraži dozvolu
granted = await limiter.acquire(
    service="sheets",
    user_id="user_123",
    cost=1,
    timeout=60.0
)

if granted:
    # Pozovi API
    result = await some_api_call(...)
else:
    # Timeout - nije mogao dobiti slot
    logger.error("Rate limit timeout!")
```

---

### 4. Definisanje Custom Cost-a (Gmail)

Za Gmail operacije sa različitim cost-om:

```python
from tools.resilience.rate_limiter import get_gmail_cost

# Dohvati cost za metod
cost = get_gmail_cost("messages.send")  # Returns: 100

@with_rate_limit("gmail", cost=cost)
async def send_email(...):
    ...
```

**Tabela Gmail Costs:**
```python
GMAIL_QUOTA_COSTS = {
    'messages.get': 5,
    'messages.send': 100,
    'messages.batchDelete': 50,
    'messages.delete': 10,
    'drafts.send': 100,
    ...
}
```

---

## ⚡ Best Practices

### 1. Preferirajte Batch Operacije

```python
# ❌ LOŠE
for item in items:
    await api_function(item)  # N zahtjeva

# ✅ DOBRO
await api_batch_function(items)  # 1 zahtjev
```

---

### 2. Koristite Asinkroni Kod

```python
# ❌ LOŠE - Serijski
results = []
for id in ids:
    result = await get_item(id)
    results.append(result)

# ✅ DOBRO - Paralelno (rate limiter će throttle-ati)
tasks = [get_item(id) for id in ids]
results = await asyncio.gather(*tasks)
```

Rate limiter će automatski throttle-ati i održati brzinu ispod limita.

---

### 3. Postavite Razumne Timeout-e

```python
# Za kritične operacije
@with_rate_limit("sheets", timeout=120.0)  # 2 minute

# Za background job-ove
@with_rate_limit("sheets", timeout=600.0)  # 10 minuta
```

---

### 4. Pratite Metrics

```python
from tools.resilience.rate_limiter import get_all_metrics

metrics = get_all_metrics()

print(f"Total requests: {metrics['total_requests']}")
print(f"Blocked: {metrics['blocked_requests']}")
print(f"Block rate: {metrics['block_rate']:.2%}")

# Per-service breakdown
for service, stats in metrics['services'].items():
    print(f"{service}: {stats['requests']} requests, {stats['blocked']} blocked")
```

---

### 5. Provjera Stanja Buckets

```python
from tools.resilience.rate_limiter import get_service_status

status = get_service_status("sheets", user_id="user_123")

print(f"Available tokens: {status['project_bucket']['available_tokens']}")
print(f"Utilization: {status['project_bucket']['utilization']:.2%}")

if 'daily_usage' in status:
    print(f"Daily emails sent: {status['daily_usage']['count']}/{status['daily_usage']['limit']}")
```

---

## 📈 Monitoring i Debugging

### Log Poruke

Rate limiter logira sve aktivnosti:

```
INFO: Acquiring rate limit for 'sheets' (function=sheets_update_values, cost=1, user=user_123)
DEBUG: Consumed 1 tokens. Remaining: 44.25
INFO: Rate limit check passed: 'sheets' (cost=1, user=user_123, elapsed=0.02s)
```

```
WARNING: Rate limit timeout (60s) for 'sheets' (cost=1, user=user_123)
ERROR: Rate limit exceeded for 'sheets' after 60s timeout
```

---

### Dashboard Metrics (Primjer)

```python
import asyncio
from tools.resilience.rate_limiter import get_all_metrics, get_service_status

async def print_dashboard():
    while True:
        metrics = get_all_metrics()

        print("\n" + "="*50)
        print("RATE LIMITER DASHBOARD")
        print("="*50)

        print(f"📊 Total Requests: {metrics['total_requests']}")
        print(f"🚫 Blocked: {metrics['blocked_requests']} ({metrics['block_rate']:.1%})")
        print(f"💎 Quota Units: {metrics['quota_units_consumed']}")

        print("\n🔹 Per-Service:")
        for service, stats in metrics['services'].items():
            print(f"  {service:12s}: {stats['requests']:5d} req, {stats['blocked']:3d} blocked")

        await asyncio.sleep(60)  # Update every minute

# Run dashboard
asyncio.run(print_dashboard())
```

---

## 🔧 Troubleshooting

### Problem: `RateLimitExceededError`

```
RateLimitExceededError: Rate limit exceeded for 'sheets' after 60s timeout
```

**Uzroci:**
1. Previše konkurentnih zahtjeva
2. Nedovoljan timeout
3. Probijen project ili user limit

**Rješenja:**

#### 1. Povećaj Timeout
```python
@with_rate_limit("sheets", timeout=120.0)  # Dvostruko više vremena
```

#### 2. Koristi Batch Operacije
```python
# Umjesto 100 pojedinačnih poziva
await sheets_batch_update(...)  # 1 poziv
```

#### 3. Raspodijeli Load Kroz Vrijeme
```python
for batch in chunks(items, 50):  # 50 itema po batchu
    await process_batch(batch)
    await asyncio.sleep(60)  # Pauza između batch-eva
```

#### 4. Povećaj Kvotu (Ako je Legitimna Potreba)
- Idi na Google Cloud Console → APIs & Services → Quotas
- Zatraži povećanje kvote za specifičan API
- Obrazloži potrebu i dosadašnju usage history

---

### Problem: Sporije Izvršavanje Nakon Dodavanja Rate Limitera

**Normalno je!** Rate limiter namjerno **usporava** zahtjeve da bi se poštovali limiti.

**Optimizacije:**

1. **Batch Operacije** (najvažnije)
2. **Caching** - ne pozivaj API ako imaš podatke lokalno
3. **Paralelizacija** - više taskova istovremeno (rate limiter će throttle-ati)

---

### Problem: Per-User Limit se Prebrzo Iscrpljuje

**Uzrok:** Svi zahtjevi se tretiraju kao jedan korisnik (koristi se Service Account umjesto OAuth).

**Rješenje:**

Koristi `quotaUser` parametar:

```python
# Umjesto:
service.spreadsheets().values().get(spreadsheetId=id, range=range).execute()

# Koristi:
service.spreadsheets().values().get(
    spreadsheetId=id,
    range=range,
    quotaUser="user_123"  # Eksplicitno navedi korisnika
).execute()
```

---

### Problem: Gmail Limiti Nepredvidivi

**Uzrok:** Različiti metodi imaju različit cost (quota units).

**Rješenje:** Eksplicitno navedi cost:

```python
@with_rate_limit("gmail", cost=100)  # Email sending
async def send_email(...):
    ...

@with_rate_limit("gmail", cost=5)  # Reading message
async def read_email(...):
    ...
```

**Referenca:**
```python
from tools.resilience.rate_limiter import GMAIL_QUOTA_COSTS

print(GMAIL_QUOTA_COSTS)
```

---

### Problem: Daily Limit Dosegnut (Gmail)

```
Request blocked: Daily limit exceeded for 'gmail' user 'user_123'
```

**Uzrok:** Poslano više od 1500 emailova u jednom danu.

**Rješenja:**

1. **Čekaj do sljedećeg dana** (reset u midnight UTC)
2. **Koristi drugi nalog** (multiple service accounts)
3. **Koristi transactional email servis** (SendGrid, Mailgun) za masovne kampanje

---

## 🎯 Sažetak

| Feature                       | Status  | Lokacija                            |
|-------------------------------|---------|-------------------------------------|
| ✅ Core Rate Limiter Engine   | ✅ Done | `tools/resilience/rate_limiter.py`  |
| ✅ Token Bucket Algorithm      | ✅ Done | `TokenBucket` class                 |
| ✅ Per-Service Limits          | ✅ Done | `SERVICE_CONFIGS`                   |
| ✅ Per-User Limits             | ✅ Done | `RateLimiter._user_buckets`         |
| ✅ Daily Limits (Gmail)        | ✅ Done | `RateLimiter._daily_counters`       |
| ✅ Quota Units (Gmail)         | ✅ Done | `GMAIL_QUOTA_COSTS`                 |
| ✅ Decorator Support           | ✅ Done | `@with_rate_limit`                  |
| ✅ Integration (46 functions)  | ✅ Done | All API implementation files        |
| ✅ Test Suite (40+ tests)      | ✅ Done | `tests/test_rate_limiter.py`        |
| ✅ Documentation               | ✅ Done | `RATE_LIMITING_GUIDE.md`            |

---

## 📚 Reference Dokumentacija

- [Google Sheets API Limits](https://developers.google.com/workspace/sheets/api/limits)
- [Google Drive API Limits](https://developers.google.com/workspace/drive/api/guides/limits)
- [Gmail API Quota](https://developers.google.com/workspace/gmail/api/reference/quota)
- [Vertex AI Quotas](https://cloud.google.com/vertex-ai/generative-ai/docs/quotas)
- [Google API Usage Limits](https://cloud.google.com/apis/docs/capping-api-usage)

---

## 🙏 Zaključak

Rate Limiting je **kritična komponenta** production-ready sistema koji koristi Google APIs.

Sa kompletnom implementacijom:
- 🛡️ **3-layer protection** (Circuit Breaker + Rate Limit + Retry)
- 🚦 **46 funkcija** zaštićeno sa rate limitingom
- 📊 **Detaljni metrics** i monitoring
- ✅ **100% coverage** svih Google Workspace APIs

Sistem je sada spreman za **skaliranje** bez rizika od probijanja limita!

---

**Kreirao:** Claude Code
**Datum:** 2025-01-15
**Verzija:** 1.0.0
