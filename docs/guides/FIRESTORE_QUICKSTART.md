# 🚀 Firestore Database Population - Quick Start

## ✅ What's Ready

Automatsko punjenje Firestore baza iz starih računa je **gotovo i testirano!**

### Kreirana Infrastruktura

1. **Firestore Tools** (`tools/adk_tools/firestore_adk_tools.py`)
   - ✅ `add_product` - Dodaje proizvod
   - ✅ `query_products` - Query proizvoda
   - ✅ `add_customer` - Dodaje kupca
   - ✅ `find_customer` - Traži kupca po emailu
   - ✅ `create_quote` - Kreira ponudu
   - ✅ `add_expense_record` - Dodaje expense record
   - ✅ `query_expenses` - Query expense-ova

2. **Enhanced Expense Agent** (`agents/adk_agents/expense_adk.py`)
   - ✅ OCR extraction (Gemini Flash)
   - ✅ Firestore integration (svi gore navedeni toolovi)
   - ✅ Automatic database population
   - ✅ Dual storage (Firestore + Sheets)

3. **Batch Processing Script** (`scripts/batch_process_invoices.py`)
   - ✅ Skenira Drive folder za račune
   - ✅ Procesira sve invoicee odjednom
   - ✅ Automatski popunjava sve 3 baze
   - ✅ Izvještava o uspješnosti

4. **Dokumentacija**
   - ✅ `docs/firestore_database_setup.md` - Kompletna dokumentacija
   - ✅ `scripts/test_firestore_setup.py` - Test script
   - ✅ Ovaj quickstart guide

---

## 📋 Kako Koristiti (3 Koraka)

### Korak 1: Upload Stare Račune

Stavi sve stare račune u Drive folder:
```
ADK_Workspace/Invoices_Input/
```

**Podržani formati:**
- JPEG, PNG slike
- PDF dokumenti
- Bilo koji broj fajlova

### Korak 2: Pokreni Batch Processing

```bash
py scripts/batch_process_invoices.py
```

**Što radi:**
- Skenira folder za sve račune
- Za svaki račun:
  - Extrakta podatke s OCR-om (Gemini Flash)
  - Sprema u `expense-records` kolekciju
  - Ako ima line items → sprema u `products` kolekciju
  - Ako ima customer info → sprema u `customers` kolekciju

**Output primjer:**
```
======================================================================
Batch Invoice Processing - Firestore Database Population
======================================================================
🔍 Searching for invoices in folder: invoices_input
✅ Found 50 invoice files

[1/50] Processing: invoice_001.jpg
   📥 Downloading file...
   🔍 Extracting data with OCR...
   💾 Saving to expense-records...
   ✅ Expense record created
   📦 Extracting 5 products...
   ✅ Created 5 product records
   👤 Customer created
   ✅ Processing complete!

...

======================================================================
PROCESSING SUMMARY
======================================================================
📊 Results:
   ✅ Successfully processed: 48/50
   ❌ Failed: 2/50
   💾 Expense records created: 48
   📦 Products extracted: 215
   👤 Customers extracted: 12
======================================================================
```

### Korak 3: Provjeri Podatke

Otvori Firestore Console:
```
https://console.cloud.google.com/firestore/databases/-default-/data/panel
```

Provjeri kolekcije:
- `expense-records` - Trebao bi vidjeti sve račune
- `products` - Ekstraktirani proizvodi iz računa
- `customers` - Kupci (ako su bili u računima)

---

## 🎯 Što Se Ekstraktira

### Iz SVIH Računa → `expense-records`

```json
{
  "vendor": "Konzum",
  "amount": 125.50,
  "currency": "EUR",
  "date": "2025-01-15",
  "category": "Hrana",
  "invoice_number": "R-2025-001",
  "payment_method": "Kartica",
  "items": [...],
  "created_at": "2025-01-15T10:30:00Z"
}
```

### Iz Line Items → `products`

```json
{
  "name": "Laptop Dell XPS 15",
  "price": 999.99,
  "currency": "EUR",
  "category": "Electronics",
  "supplier": "Office Depot",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### Iz Customer Info → `customers`

```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "company": "Acme Corp",
  "phone": "+385 99 123 4567",
  "created_at": "2025-01-15T10:30:00Z"
}
```

---

## 🛠️ Test Before Batch Processing

Provjeri je li sve ready:

```bash
py scripts/test_firestore_setup.py
```

**Trebao bi vidjeti:**
```
🎉 All tests passed! (5/5)

✅ Firestore setup is ready!
```

---

## 💰 Cijena

**Gemini Flash OCR:**
- ~$0.00007 po računu
- 50 računa = $0.0035 (manje od 1 centa!)
- 500 računa = $0.035 (3.5 centi)
- 1000 računa = $0.07 (7 centi)

**Usporedba:**
- Document AI bi koštao: $0.10 po stranici
- 50 računa = $5.00
- **Ušteda: 1400x jeftinije!**

---

## ❓ FAQ

### Q: Što ako račun nema line items?
A: Normalno! Sprema se u `expense-records`, ali ne kreira proizvode. Samo invoicei s jasno vidljivim stavkama će imati products.

### Q: Hoće li kreirati duplikate proizvoda?
A: Da - svaki invoice kreira svoje proizvode. To je namjerno za tracking purchase history. Možeš deduplicirati kasnije ako želiš.

### Q: Što ako OCR ne uspije?
A: Script će izvijestiti failed invoices. Možeš ih procesirati manualno ili re-fotografirati s boljom kvalitetom.

### Q: Mogu li procesirati specifičan folder?
A: Da! `py scripts/batch_process_invoices.py --folder "naziv_foldera"`

### Q: Gdje mogu vidjeti detalje ekstraktiranih podataka?
A: U Firestore Console-u možeš browsati sve dokumente i vidjeti točno što je ekstraktirano.

---

## 📚 Dodatna Dokumentacija

- **Kompletna dokumentacija:** `docs/firestore_database_setup.md`
- **Expense agent upute:** `agents/expense/instructions.md`
- **Firestore tools reference:** `tools/adk_tools/firestore_adk_tools.py`

---

## 🎉 Ready to Go!

Sve je postavljeno. Samo:
1. Upload račune u `ADK_Workspace/Invoices_Input/`
2. Run `py scripts/batch_process_invoices.py`
3. Check Firestore Console

**Gotovo!** 🚀

---

## 🗂️ Firestore Composite Indexes

Repo sadrži `firestore.indexes.json` — manifest svih composite indexa potrebnih za ERP upite.

### Primjena na novi projekt

**Opcija 1 — Firebase CLI** (preporučeno):
```bash
firebase deploy --only firestore:indexes --project YOUR_PROJECT_ID
```

**Opcija 2 — gcloud CLI** (ručno, po indexu):
```bash
gcloud firestore indexes composite create \
  --collection-group=quotes \
  --field-config="field-path=company_id,order=ASCENDING" \
  --field-config="field-path=deleted,order=ASCENDING" \
  --field-config="field-path=created_at,order=DESCENDING" \
  --project=YOUR_PROJECT_ID
```

### Dodavanje novog indexa

Kad Firestore javi `FAILED_PRECONDITION: The query requires an index`:

1. Kreiraj index ručno (`gcloud` ili link iz error poruke)
2. Dodaj ga u `firestore.indexes.json`
3. Commitaj promjenu

### Trenutni indexi

| Kolekcija | Polja | Svrha |
|-----------|-------|-------|
| `quotes` | company_id, deleted, created_at | Lista ponuda |
| `quotes` | company_id, deleted, document_status, created_at | Filtriranje po statusu |
| `inventory_movements` | company_id, product_id, created_at | Kretanja zaliha po proizvodu |
| `audit_log` | company_id, target_service, timestamp | Activity feed |
| `vendor_invoices` | company_id, deleted, issue_date | Lista URA |
| `payments` | company_id, payment_date | Lista plaćanja |
| ... | | (ukupno 26 indexa — vidi `firestore.indexes.json`) |
