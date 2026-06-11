# Faza 0: Arhitekturna specifikacija
**Datum**: 2026-04-03
**Status**: Compliance remediation (rok 01.01.2026 je prosao)

---

## 1. Kanonski modeli racuna po tipu

### 1.1 Zajednicka polja (svi tipovi)

Svaki racun, bez obzira na tip, MORA imati:

```
IDENTIFIKACIJA
  invoice_id          : str (UUID, Firestore document ID)
  display_id          : str (human-readable, e.g. "RA-2026-000042")
  invoice_number      : str (fiskalni broj: XXX/PP/NU za B2C, slobodno za ostale)
  invoice_type        : enum (b2c | b2b | b2g | eu | int)
  invoice_type_code   : str (UNCL 1001: "380"=invoice, "381"=credit note, ...)
  company_id          : str (tenant isolation)

STRANKE
  supplier_oib        : str (11 digit, Module 11)
  supplier_name       : str
  supplier_address    : str
  supplier_vat_number : str (HR + OIB za domace)
  buyer_oib           : str (obavezan za B2C/B2B/B2G, opcionalan za EU/INT)
  buyer_name          : str
  buyer_address       : str
  buyer_vat_number    : str (obavezan za B2B/B2G/EU)
  buyer_country_code  : str (ISO 3166-1 alpha-2)

DATUMI
  issue_date          : date (ISO 8601)
  due_date            : date
  delivery_date       : date (opcionalno, obavezno za B2G)

STAVKE
  items[]             : list (min 1)
    description       : str
    quantity          : Decimal
    unit_code         : str (UN/ECE Rec 20)
    unit_price        : Decimal (neto)
    vat_rate          : enum (25 | 13 | 5 | 0)
    tax_category_code : str (S | Z | E | AE | K | G | O)
    kpd_code          : str (XX.XX.XX, KPD 2025)
    kpd_confidence    : float (0.0-1.0)
    line_total        : Decimal (quantity * unit_price)

IZNOSI
  subtotal_net        : Decimal
  vat_total           : Decimal
  grand_total         : Decimal
  currency            : str (ISO 4217, default EUR)

PLACANJE
  payment_means_code  : str (UNCL 4461: "30"=transfer, "10"=cash, "48"=card)
  bank_account        : str (IBAN)
  payment_reference   : str (poziv na broj)

STATUSI (3 odvojena koncepta - NIKAD mijesati)
  document_status     : str (state machine)
  payment_status      : str (computed: unpaid | partial | paid)
  is_overdue          : bool (computed, NIKAD stored)

AUDIT
  created_at          : datetime (UTC ISO 8601)
  created_by          : str (user_id)
  updated_at          : datetime
  source_quote_id     : str (opcionalno, ako je iz ponude)
  deleted             : bool (soft delete)
```

### 1.2 B2C - specificna polja

```
FISKALIZACIJA (CIS/FINA)
  fiscalization_status : enum (pending | fiscalized | error | queued)
  jir                  : str (36-char UUID od FINA)
  zki                  : str (32-char MD5 hash)
  qr_code_url          : str (URL za verifikaciju)
  qr_code_data         : str (raw QR content)
  signed_xml           : str (potpisani RacunZahtjev XML)
  fina_response_xml    : str (FINA odgovor)
  fiscalized_at        : datetime

SPECIFIKA
  cash_register_id     : str (oznaka naplatnog uredaja - NU)
  business_premises_id : str (oznaka poslovnog prostora - PP)
  operator_oib         : str (OIB operatera)
  subsequent_delivery  : bool (naknadno dostavljanje)

TRANSPORT
  delivery_channel     : "direct" (tiskan/na ekranu)
```

### 1.3 B2B - specificna polja

```
e-RACUN (UBL 2.1 + HR-FISK 2.0 CIUS)
  ubl_customization_id : str (HR_FISK_CUSTOMIZATION_ID)
  ubl_profile_id       : str (PEPPOL_PROFILE_ID)
  ubl_xml              : str (generirani UBL 2.1 XML)
  signed_ubl_xml       : str (XAdES-BES potpisani)

CTC DUAL REPORTING
  ctc_fina_xml         : str (RacunZahtjev za Poreznu)
  ctc_fina_status      : enum (pending | reported | error)
  ctc_fina_response    : str
  eracun_status        : enum (pending | sent | delivered | rejected | accepted)
  eracun_delivery_id   : str (tracking ID od AP)

TRANSPORT
  delivery_channel     : enum (email | access_point | portal)
  delivery_endpoint    : str (email adresa ili AP ID primaoca)

BUYER SPECIFIKA
  buyer_order_reference : str (broj narudzbe kupca)
  contract_reference    : str (broj ugovora)
```

### 1.4 B2G - specificna polja

```
PEPPOL / FINA e-Racun
  peppol_participant_id : str (FINA Peppol ID primaoca)
  peppol_process_id     : str
  peppol_document_id    : str (primljen od AP-a)

JAVNA NABAVA (obavezna polja)
  procurement_reference : str (evidencijski broj nabave)
  delivery_date         : date (OBAVEZNO za B2G)
  buyer_reference       : str (referenca narucioca)

TRANSPORT
  delivery_channel     : "fina_peppol"

STATUSI (prosireni)
  peppol_status        : enum (pending | sent | delivered | accepted | rejected)
  peppol_response      : str
```

### 1.5 EU - specificna polja

```
POREZNE SPECIFIKE
  tax_category_code    : "AE" (reverse charge) ili "K" (intra-community)
  reverse_charge       : bool
  vies_validated       : bool (OBAVEZNO true prije izdavanja)
  vies_validation_date : date
  vies_request_id      : str
  buyer_vat_number     : str (OBAVEZNO, s country prefiksom)

e-REPORTING
  ereporting_status    : enum (pending | reported | confirmed)
  ereporting_date      : date

TRANSPORT
  delivery_channel     : enum (email | peppol)

NAPOMENE
  tax_exemption_reason : str ("Prijenos porezne obveze cl. 75. st. 1. t. 1. Zakona o PDV-u")
```

### 1.6 INT - specificna polja

```
POREZNE SPECIFIKE
  tax_category_code    : "G" (export) ili "O" (outside scope)
  zero_rate_reason     : str ("Izvoz - cl. 45. Zakona o PDV-u")

CARINSKI DOKUMENTI
  customs_declaration   : str (broj carinske deklaracije)
  export_document_ref   : str
  incoterms             : str (EXW, FOB, CIF, ...)

e-REPORTING
  ereporting_status    : enum (pending | reported | confirmed)
  ereporting_date      : date

TRANSPORT
  delivery_channel     : enum (email | courier)
```

### 1.7 VENDOR INVOICE (Inbound / URA) - kanonski model

```
IDENTIFIKACIJA
  vendor_invoice_id    : str (UUID, Firestore doc ID)
  display_id           : str ("URA-2026-000001")
  vendor_invoice_no    : str (broj racuna dobavljaca)
  company_id           : str (tenant)

DOBAVLJAC
  vendor_id            : str (referenca na customers collection)
  vendor_name          : str
  vendor_oib           : str
  vendor_vat_number    : str

DATUMI
  issue_date           : date (datum izdavanja od dobavljaca)
  received_date        : date (datum zaprimanja - ZAKONSKI BITAN)
  due_date             : date
  fiscalization_deadline : date (received_date + 5 radnih dana)

STAVKE I IZNOSI
  items[]              : list (isto kao outgoing)
  subtotal_net         : Decimal
  vat_amount           : Decimal
  total_gross          : Decimal
  currency             : str

IZVORNI DOKUMENT (OBAVEZNO cuvati original)
  source_type          : enum (ubl_xml | ocr_scan | manual | email_attachment)
  source_ubl_xml       : str (originalni UBL XML od dobavljaca, ako postoji)
  source_scan_file_id  : str (Drive ID skenirane slike/PDF-a)
  source_email_id      : str (Gmail message ID, ako je dosao emailom)

PARSIRANJE (ako je UBL)
  parsed_from_ubl      : bool
  ubl_validation_status : enum (valid | invalid | warning)
  ubl_validation_errors : list[str]

STATUSI
  document_status      : str (state machine - vidi dijagram)
  payment_status       : str (computed: unpaid | partial | paid)
  fiscalization_status : enum (pending | fiscalized | overdue | error)
  acceptance_status    : enum (pending | accepted | rejected)
  rejection_reason     : str (obavezan ako rejected)

NAPLATA / EVIDENCIJA
  amount_paid          : Decimal
  amount_due           : Decimal

OCR METADATA (ako iz OCR-a)
  from_ocr             : bool
  ocr_data             : dict (raw OCR output)
  ocr_confidence       : float
  vendor_match_status  : enum (matched | no_match | manual)

AUDIT
  created_at           : datetime
  created_by           : str
  approved_by          : str
  approved_at          : datetime
  _dedup_hash          : str (vendor_oib + invoice_no + date + amount)
  category             : str (materials | services | utilities | equipment | other)
```

---

## 2. Statusni dijagrami

### 2.1 Outgoing Invoice (B2C) - document_status

```
                    +--------+
                    | draft  |
                    +--------+
                    /        \
                   v          v
             +---------+  +-----------+
             | approved|  | cancelled |  (terminal)
             +---------+  +-----------+
                  |
                  v
             +---------+
             | issued  |
             +---------+
              /       \
             v         v
      +-------------+  +-----------+
      | fiscalized  |  | cancelled |
      +-------------+  +-----------+
             |
             v
          +------+
          | sent |
          +------+
           /       \
          v         v
   +-----------+  +----------------+
   | cancelled |  | storno_issued  |  (terminal)
   +-----------+  +----------------+
```

### 2.2 Outgoing Invoice (B2B/B2G) - document_status
RAZLIKA od B2C: nema "fiscalized" stanja, ima "eracun_sent"

```
                    +--------+
                    | draft  |
                    +--------+
                    /        \
                   v          v
             +---------+  +-----------+
             | approved|  | cancelled |
             +---------+  +-----------+
                  |
                  v
             +---------+
             | issued  | (UBL generiran + potpisan)
             +---------+
                  |
                  v
          +--------------+
          | eracun_sent  | (poslan na AP / email / Peppol)
          +--------------+
           /      |       \
          v       v        v
   +----------+ +----------+ +-----------+
   | delivered| | rejected | | cancelled |
   +----------+ +----------+ +-----------+
        |
        v
     +----------+
     | accepted |
     +----------+
        |
        v
   +----------------+
   | storno_issued  | (terminal, samo ako treba storno)
   +----------------+
```

### 2.3 Outgoing Invoice (EU/INT) - document_status

```
                    +--------+
                    | draft  |
                    +--------+
                    /        \
                   v          v
             +---------+  +-----------+
             | approved|  | cancelled |
             +---------+  +-----------+
                  |
                  v (VIES provjera za EU, customs ref za INT)
             +---------+
             | issued  |
             +---------+
                  |
                  v
             +------+
             | sent | (email, Peppol, ili kurir)
             +------+
              /       \
             v         v
      +-----------+  +----------------+
      | cancelled |  | storno_issued  |
      +-----------+  +----------------+
```

### 2.4 Vendor Invoice (Inbound / URA) - document_status

```
                   +--------+
                   | draft  | (iz OCR-a, rucnog unosa, ili UBL parsiranja)
                   +--------+
                    /       \
                   v         v
            +-----------+  +-----------+
            | received  |  | cancelled |
            +-----------+  +-----------+
             /    |    \
            v     v     v
   +----------+ +----------+ +-----------+
   | approved | | disputed | | cancelled |
   +----------+ +----------+ +-----------+
        |             |
        |             v
        |       +-----------+
        |       | received  | (vracen na ponovni pregled)
        |       +-----------+
        |
        v  (fiskalizacija primitka - rok 5 radnih dana)
   +-----------------+
   | fisc_reported   | (prijavljeno Poreznoj upravi)
   +-----------------+
        |
        v (placanje)
   payment_status: unpaid -> partial -> paid
```

**NOVI STATUSI za vendor invoice (prosirenje postojeceg SM):**
- `fisc_reported` - fiskalizacija primljenog racuna zavrsena
- Acceptance: `accepted` / `rejected` s obaveznim `rejection_reason`
- SLA alarm: `fiscalization_deadline` = `received_date` + 5 radnih dana

### 2.5 Payment Status (computed, svi tipovi)

```
  amount_paid == 0                -> "unpaid"
  0 < amount_paid < total_gross   -> "partial"
  amount_paid >= total_gross      -> "paid"

  NIKAD stored via state machine.
  UVIJEK computed on read.
```

### 2.6 Quote - document_status (postojece, bez promjena)

```
  draft -> sent -> accepted -> converted (terminal)
                -> rejected  (terminal)
                -> expired   (terminal)
       -> cancelled (terminal)
```

---

## 3. Audit paket - sto MORA postojati za svaki racun

### 3.1 Outgoing Invoice (svi tipovi)

```
OBAVEZNI ARTEFAKTI:
  1. Firestore dokument          (source of truth za podatke)
  2. PDF renderiran racun        (za kupca/arhivu)
  3. Originalni XML/UBL          (za B2C: RacunZahtjev, za B2B/B2G: UBL 2.1)
  4. Potpisani XML               (XAdES-BES za B2C i B2B/B2G)
  5. FINA/AP odgovor             (JIR za B2C, delivery status za B2B/B2G)
  6. QR kod                      (za B2C, obavezno od 01.01.2026)
  7. Status trail                (audit_log collection - tko, sto, kada)

DRIVE POHRANA:
  Invoices_Archive/OUT/{tip}/YYYY/MM/{display_id}/
    ├── {display_id}.pdf           (renderiran racun)
    ├── {display_id}_ubl.xml       (originalni UBL / RacunZahtjev)
    ├── {display_id}_signed.xml    (potpisani dokument)
    └── {display_id}_qr.png        (QR kod, samo B2C)

FIRESTORE REFERENCE:
  drive_folder_id      : str
  drive_pdf_file_id    : str
  drive_xml_file_id    : str
  drive_signed_xml_id  : str
  drive_qr_file_id     : str (samo B2C)
  archived_at          : datetime
  archive_status       : enum (pending | archived | error)
```

### 3.2 Vendor Invoice (inbound)

```
OBAVEZNI ARTEFAKTI:
  1. Firestore dokument          (source of truth)
  2. ORIGINALNI dokument         (UBL XML od dobavljaca ILI skenirana slika/PDF)
  3. OCR output                  (ako iz skena)
  4. Normalizirani podaci        (ono sto ERP koristi)
  5. Fiskalizacija primitka      (potvrda prijave Poreznoj)
  6. Accept/Reject odluka        (s razlogom ako rejected)
  7. Status trail                (audit_log)

DRIVE POHRANA:
  Invoices_Archive/IN/YYYY/MM/{display_id}/
    ├── {display_id}_original.xml  (UBL od dobavljaca)
    ├── {display_id}_original.pdf  (sken ako OCR)
    ├── {display_id}_ocr.json      (OCR output, ako primjenjivo)
    └── {display_id}_fisc.xml      (potvrda fiskalizacije primitka)

FIRESTORE REFERENCE:
  drive_folder_id         : str
  drive_original_file_id  : str
  drive_ocr_file_id       : str (opcionalno)
  drive_fisc_file_id      : str
  archived_at             : datetime
  archive_status          : enum (pending | archived | error)
```

### 3.3 ERP Izvjestaji

```
DRIVE POHRANA:
  Reports_Output/ERP/{tip_izvjestaja}/YYYY/MM/
    ├── PDV_2026-03.pdf
    ├── Cashflow_2026-03.pdf
    ├── Receivables_Aging_2026-03-31.pdf
    ├── Payables_Aging_2026-03-31.pdf
    └── Financial_Summary_2026-03.pdf

AUTO-EXPORT: Scheduler job, mjesecno, 1. u mjesecu za prethodni mjesec.
```

---

## 4. Test matrica

### 4.1 Outgoing Invoice Test Scenarios

| # | Scenario | Tip | Kljucne provjere | Prioritet |
|---|----------|-----|-------------------|-----------|
| O1 | Izdavanje standardnog racuna | B2C | JIR, ZKI, QR, PDF, FINA SOAP, ledger zapis | P0 |
| O2 | Izdavanje racuna s vise stavki i razlicitim PDV stopama | B2C | 25%+13%+5% na istom racunu, tax breakdown tocan | P0 |
| O3 | Storno racun (credit note 381) | B2C | Storno JIR, originalni JIR referenca | P1 |
| O4 | Naknadno dostavljanje (subsequent) | B2C | subsequent_delivery=true, 48h deadline | P1 |
| O5 | Quote -> Invoice -> Fiskalizacija | B2C | Cijeli tok bez zaobilazenja | P0 |
| O6 | Izdavanje UBL B2B racuna | B2B | UBL 2.1 validan, HR-FISK CIUS, XAdES-BES | P0 |
| O7 | CTC dual reporting | B2B | I FINA prijava I e-Racun poslan | P0 |
| O8 | B2G racun za javnu nabavu | B2G | Peppol delivery, procurement_reference | P1 |
| O9 | EU reverse charge racun | EU | VIES validiran, AE tax category, 0% PDV | P0 |
| O10 | INT export racun | INT | Zero-rate, customs ref, tax exemption reason | P1 |
| O11 | Racun s predujmom | svi | Prepayment (386), advance deduction | P2 |

### 4.2 Vendor Invoice (Inbound) Test Scenarios

| # | Scenario | Source | Kljucne provjere | Prioritet |
|---|----------|--------|-------------------|-----------|
| I1 | Zaprimanje UBL XML od dobavljaca | UBL parser | XML parsiran, vendor matched, draft kreiran | P0 |
| I2 | Zaprimanje UBL iz email priloga | Gmail + parser | Email scan, attachment extract, auto-parse | P0 |
| I3 | Zaprimanje skenirane slike | OCR | Gemini OCR, vendor match, draft kreiran | P1 |
| I4 | Zaprimanje iz Drive mape | Drive monitor | File detected, processed, moved to archive | P0 |
| I5 | Duplicate detection | dedup | Isti dobavljac+broj+datum+iznos = rejected | P0 |
| I6 | Odobravanje i placanje URA | workflow | draft->received->approved, payment recorded | P0 |
| I7 | Odbijanje racuna s razlogom | workflow | disputed->cancelled, rejection_reason obavezan | P1 |
| I8 | Fiskalizacija primitka u roku | SLA | received_date + 5 radnih dana, alarm ako kasni | P0 |
| I9 | Mjesecno izvjestavanje odbijanja | reporting | Agregirani izvjestaj svih rejected u mjesecu | P1 |

### 4.3 Drive Archiving Test Scenarios

| # | Scenario | Provjere | Prioritet |
|---|----------|----------|-----------|
| D1 | Outgoing invoice -> Drive archive | PDF + XML u ispravnoj mapi, Firestore ID-evi | P0 |
| D2 | Vendor invoice -> Drive archive | Original + OCR/fisc u IN mapi | P0 |
| D3 | ERP report auto-export | PDF generiran, uploadan, link zapisan | P1 |
| D4 | Auto-move iz Input u Archive | File moved, processed_ids updated | P0 |

### 4.4 Sample dokumenti potrebni

```
OUTGOING (za generiranje - mi kontroliramo):
  sample_b2c_invoice.json        -> generira RacunZahtjev XML
  sample_b2b_invoice.json        -> generira UBL 2.1 XML
  sample_b2g_invoice.json        -> generira UBL + Peppol metadata
  sample_eu_invoice.json         -> generira UBL s reverse charge
  sample_int_invoice.json        -> generira UBL s zero-rate
  sample_credit_note.json        -> generira storno (381)

INBOUND (trebamo primjerke od dobavljaca):
  sample_inbound_b2b.xml         -> UBL 2.1 od HR dobavljaca
  sample_inbound_b2g.xml         -> UBL od drzavnog tijela
  sample_inbound_scan.jpg/.pdf   -> skeniran papirni racun
  sample_inbound_email.eml       -> email s UBL prilogom
```

---

## 5. Kljucne arhitekturne odluke

### 5.1 Source of truth za invoice lifecycle

**PROBLEM**: Danas `QuoteService.convert_to_invoice()` pise direktno u
`invoices_b2c/b2b/...` s `document_status: "draft"`, zaobilazeci fiskalizaciju.

**ODLUKA**: Quote convert SMIJE kreirati draft, ali draft MORA proci kroz
fiskalizacijski pipeline prije nego postane "issued". Tok:

```
Quote (accepted)
  -> convert_to_invoice() -> draft u invoices_{tip}
  -> fiskalizacija pipeline (pripremac -> validator -> HITL -> executor)
  -> issued / fiscalized / eracun_sent
  -> ERP payment tracking
  -> Drive archive
```

**IMPLEMENTACIJA**:
- `convert_to_invoice()` ostaje ali vraca `document_status: "draft"`
- Dodati `POST /api/erp/invoices/{type}/{id}/fiscalize` endpoint
- Fiskalizacija cita draft, provodi pipeline, updatea status
- NIKAD ne preskakati fiskalizaciju

### 5.2 Transport kanal vs racunovodstveni dokument

```
DOKUMENT (sto)          =/=     TRANSPORT (kako)
----------------------------------------------------------
B2C Invoice                     Direct (print, ekran)
B2B Invoice                     Email, Access Point, Portal
B2G Invoice                     FINA Peppol AP
EU Invoice                      Email, Peppol
INT Invoice                     Email, kurir

Delivery channel je ATRIBUT racuna, ne tip racuna.
Jedan B2B racun moze ici emailom danas, a AP-om sutra.
```

### 5.3 Inbound routing (popravak)

**PROBLEM**: `monitor_drive_invoices.py` sprema u `expense_records` umjesto
`vendor_invoices`.

**ODLUKA**:
- Ako je dokument RACUN (ima OIB dobavljaca, broj racuna, stavke) -> `vendor_invoices`
- Ako je dokument BLAGAJNICKI RACUN bez stavki (kava, taxi) -> `expense_records`
- Klasifikacija se radi na temelju OCR outputa

### 5.4 Drive kao arhiva, Firestore kao system of record

```
Firestore = source of truth (podatci, statusi, linkovi)
Drive = arhiva (originali, PDF-ovi, XML-ovi)

Firestore dokument DRZI reference na Drive (file_id, folder_id).
Drive NE DRZI poslovnu logiku.
Ako Drive file nestane, Firestore podatci su i dalje ispravni.
Ako Firestore doc nestane, Drive file je sirovi backup.
```

---

## 6. Ovisnosti za odluku PRIJE implementacije

| # | Pitanje | Opcije | Impact |
|---|---------|--------|--------|
| 1 | B2B/B2G outbound kanal | FINA AP / vanjski posrednik / email-only za pocetak | Blokira Fazu 2 |
| 2 | B2B inbound kanal | FINA AP / email monitoring / manual upload za pocetak | Blokira Fazu 1 |
| 3 | AMS/MPS registracija | Trebamo identifikator za primanje eRacuna | Preduvjet za automatsko primanje |
| 4 | FINA test certifikat | .p12 za sandbox testiranje | Blokira end-to-end testove |
| 5 | Sample UBL od dobavljaca | Trebamo barem 2-3 realna XML-a | Blokira I1 test |
| 6 | Tko odobrava URA? | Samo accountant / vlasnik / oba | Definira RBAC pravila |

---

## 7. Redoslijed implementacije (detaljno)

```
Tjedan 1-2: Faza 1 (Inbound eRacun)
  - UBL inbound parser (xml -> vendor_invoice)
  - Prosiriti vendor invoice SM (fisc_reported, accepted/rejected)
  - Gmail/Drive monitoring za UBL attachmente
  - SLA scheduler (5 radnih dana alarm)
  - Popraviti monitor_drive_invoices.py routing
  - Drive: nova mapa Vendor_Invoices_Input + auto-archive

Tjedan 3-4: Faza 2 (Outbound B2B/B2G)
  - Odvojiti B2C executor od B2B/B2G executora
  - B2B: UBL generiranje + signing + CTC dual report + status tracking
  - B2G: Peppol metadata + FINA AP slanje (ili email fallback)
  - Quote->Invoice->Fiskalizacija cijelovit tok
  - Ukloniti skip_llm=True, spojiti pripremac+validator

Tjedan 5: Faza 5 (Drive operationalization)
  - Auto-archive workflow (Input -> Archive)
  - Standardne mape: OUT/{tip}/YYYY/MM, IN/YYYY/MM
  - ERP report auto-export (mjesecni scheduler)
  - Firestore drive_file_id reference na svim racunima

Tjedan 6: Faza 4 (ERP konsolidacija)
  - JWT auth umjesto dev header bridge
  - Fiscalize endpoint za draft invoice
  - Credit limit enforcement
  - Customer delete validacija
  - Dunning hookovi (priprema)

Tjedan 7: Faza 3 (EU/INT)
  - VIES pravi API (zamijeniti stub)
  - KPD RAG (embeddings umjesto keyword)
  - EU reverse charge end-to-end test
  - INT zero-rate end-to-end test

Tjedan 8: Faza 6 (Research)
  - google_search_simple popravak
  - PDF web scraping (PyMuPDF)
  - Firecrawl aktivacija
  - Research evidence store
```
