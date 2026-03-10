

# Firestore Database Population from Invoices

This guide explains how to automatically populate Firestore databases from old invoices using the Expense agent with OCR.

## Overview

The system can automatically extract data from invoice images/PDFs and populate 4 Firestore collections:
1. **expense-records** - All invoice/receipt data
2. **products** - Product catalog extracted from line items
3. **customers** - Customer information from incoming invoices
4. **quotes** - For future use (not populated from invoices)

## Architecture

```
Old Invoices (Drive Folder)
         ↓
   [Batch Processing Script]
         ↓
    [Expense Agent]
    (Gemini Flash OCR)
         ↓
    [Data Extraction]
    ├── Merchant, Date, Amount
    ├── Line Items (Products)
    └── Customer Info (if invoice)
         ↓
    [Firestore Tools]
    ├── add_expense_record() ← All invoices
    ├── add_product() ← Line items
    └── add_customer() ← Customer data
         ↓
  [Populated Databases]
```

## Prerequisites

### 1. Firestore Collections Created

You should have already created these collections in Google Cloud Console:
- `expense-records`
- `products`
- `customers`
- `quotes`

**Verify in Google Cloud Console:**
```
https://console.cloud.google.com/firestore/databases/-default-/data/panel
```

### 2. Drive Folder with Invoices

Upload your old invoices to a Drive folder:
- Folder: `ADK_Workspace/Invoices_Input/`
- Supported formats: JPEG, PNG, PDF
- Any number of files

### 3. Environment Setup

Ensure `.env` has:
```bash
GOOGLE_CLOUD_PROJECT=your-project-id
# OAuth credentials should be configured
```

## Quick Start

### Option 1: Batch Process All Invoices (Recommended)

Process all invoices from the default folder:

```bash
py scripts/batch_process_invoices.py
```

Or specify a custom folder:

```bash
py scripts/batch_process_invoices.py --folder "invoices_input"
```

**What it does:**
1. Scans Drive folder for all images/PDFs
2. For each invoice:
   - Extracts data with Gemini Flash OCR
   - Saves to `expense-records` collection
   - Extracts products from line items → `products` collection
   - Extracts customer info (if present) → `customers` collection
3. Reports summary with success/failure counts

**Expected output:**
```
======================================================================
Batch Invoice Processing - Firestore Database Population
======================================================================
🔍 Searching for invoices in folder: invoices_input
✅ Found 50 invoice files

📋 Processing 50 invoices...
======================================================================

[1/50] Processing: invoice_2024_001.jpg
   📥 Downloading file...
   🔍 Extracting data with OCR...
   💾 Saving to expense-records...
   ✅ Expense record created: abc123
   📦 Extracting 5 products...
   ✅ Created 5 product records
   👤 Checking customer: john@example.com
   ✅ Customer created: xyz789
   ✅ Processing complete!

[2/50] Processing: invoice_2024_002.pdf
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

⚠️  Failed invoices:
   - blurry_receipt.jpg: OCR failed: Low confidence
   - corrupted.pdf: OCR failed: Invalid file format

======================================================================
✅ Batch processing complete!
======================================================================
```

### Option 2: Process Single Invoice via Agent

You can also process invoices one by one through the orchestrator:

```python
# Via main.py or interactive session
User: "Process the invoice in Invoices_Input folder named 'INV-2025-001.pdf'"

Orchestrator → Expense Agent → OCR + Database Population
```

## What Gets Extracted

### From ALL Invoices → `expense-records`

Every invoice populates an expense record:

```json
{
  "vendor": "Office Depot",
  "amount": 249.99,
  "currency": "EUR",
  "date": "2025-01-15",
  "category": "Ured",
  "invoice_number": "INV-2025-001",
  "payment_method": "Kartica",
  "items": [
    {"description": "Paper A4", "quantity": 10, "unit_price": 5.99},
    {"description": "Pens", "quantity": 20, "unit_price": 1.50}
  ],
  "created_at": "2025-01-15T10:30:00Z"
}
```

### From Line Items → `products`

If invoice has line items, each item creates a product record:

```json
{
  "name": "Paper A4 500 sheets",
  "price": 5.99,
  "currency": "EUR",
  "category": "Office Supplies",
  "supplier": "Office Depot",
  "sku": "",
  "stock": 0,
  "description": "Extracted from invoice: INV-2025-001.pdf",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**Duplicate handling:**
- Script does NOT check for duplicates (by design)
- If same product appears in multiple invoices, multiple entries will be created
- You can deduplicate later using Firestore queries

### From Customer Data → `customers`

If invoice has customer information (incoming invoices), creates customer record:

```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "company": "Acme Corp",
  "phone": "+385 99 123 4567",
  "address": "Main St 123, Zagreb",
  "notes": "",
  "created_at": "2025-01-15T10:30:00Z"
}
```

**Duplicate handling:**
- Script checks if customer exists by email
- If exists, skips creation
- No duplicates for customers

## Expense Categories

The agent automatically categorizes expenses:

- **Hrana** (Food): Restaurants, groceries, cafes
- **Prijevoz** (Transport): Fuel, parking, taxi
- **Ured** (Office): Office supplies, electronics
- **Režije** (Utilities): Electricity, internet, rent
- **Ostalo** (Other): Everything else

## Confidence and Validation

The Expense agent uses confidence scoring:
- **< 50%**: Very low confidence → Marked as failed
- **50-79%**: Low confidence → Processed but flagged
- **≥ 80%**: High confidence → Auto-processed

Failed invoices are reported in the summary and can be processed manually.

## Querying Your Data

After batch processing, you can query the databases:

### Query Expenses

```python
from tools.adk_tools.firestore_adk_tools import query_expenses

# Get all expenses for January 2025
result = await query_expenses(
    start_date="2025-01-01",
    end_date="2025-01-31"
)

print(f"Total expenses: {result['total_amount']} EUR")
print(f"Number of records: {result['count']}")
```

### Query Products

```python
from tools.adk_tools.firestore_adk_tools import query_products

# Get all office supplies
result = await query_products(
    category="Office Supplies",
    max_price=100
)

print(f"Found {result['count']} products")
```

### Find Customer

```python
from tools.adk_tools.firestore_adk_tools import find_customer

result = await find_customer("john@example.com")
if result['found']:
    print(f"Customer: {result['customer']['name']}")
```

## Verifying Data in Google Cloud Console

After batch processing, verify your data:

1. Open [Firestore Console](https://console.cloud.google.com/firestore/databases/-default-/data/panel)
2. Select collection: `expense-records`
3. Browse documents - you should see all processed invoices
4. Check `products` collection for extracted line items
5. Check `customers` collection for customer data

## Troubleshooting

### Error: "Database not available"

**Solution:**
- Verify GOOGLE_CLOUD_PROJECT is set in `.env`
- Check OAuth credentials are valid
- Ensure Firestore API is enabled in Google Cloud Console

### Error: "OCR failed: Low confidence"

**Solution:**
- Invoice image is too blurry or dark
- Re-scan with better quality
- Process manually via web interface

### Error: "Folder not found"

**Solution:**
- Check folder exists in Drive: `ADK_Workspace/Invoices_Input/`
- Verify `config/drive_map.yaml` has correct folder definition
- Run DriveNavigator to create folders if needed

### No products extracted

**Cause:**
- Invoice doesn't have line items visible
- OCR couldn't detect itemized list
- Invoice is a summary only

**Note:** This is expected for some invoices. Only line items that are clearly visible will be extracted.

### Duplicate products

**Expected behavior:**
- Batch script does NOT check for duplicate products
- Same product from different invoices creates multiple entries
- This is by design for tracking purchase history

**If you want unique products:**
```python
# Query all products, deduplicate by name
from tools.adk_tools.firestore_adk_tools import query_products

products = await query_products(limit=1000)
unique_products = {}
for p in products['products']:
    if p['name'] not in unique_products:
        unique_products[p['name']] = p
```

## Advanced Usage

### Process Specific Folder

```bash
# Process invoices from different folder
py scripts/batch_process_invoices.py --folder "invoices_archive"
```

### Process Single File

```python
# Via Python script
from scripts.batch_process_invoices import process_single_invoice

result = await process_single_invoice(
    file_id="DRIVE_FILE_ID",
    file_name="invoice.pdf",
    mime_type="application/pdf",
    index=1,
    total=1
)

print(f"Status: {result['status']}")
print(f"Products created: {result['products_created']}")
```

### Custom OCR Settings

Edit `tools/adk_tools/vision_adk_tools.py` to adjust OCR parameters:
- Temperature for extraction
- Confidence thresholds
- Retry logic

## Cost Estimation

**Gemini Flash OCR costs:**
- ~$0.00007 per receipt
- 50 invoices = $0.0035 (less than 1 cent!)
- 500 invoices = $0.035 (3.5 cents)
- 1000 invoices = $0.07 (7 cents)

**Compared to Document AI:**
- Document AI: $0.10 per page
- 50 invoices = $5.00
- **Savings: 1400x cheaper with Gemini Flash!**

## Next Steps

After populating your databases:

1. **Verify data** - Check Firestore console for accuracy
2. **Build reports** - Query data for expense reports
3. **Create dashboards** - Visualize spending by category
4. **Automate future invoices** - Set up automatic processing for new invoices
5. **Add Sales agents** - Create quotes using product catalog

## See Also

- [Expense Agent Documentation](../agents/expense/instructions.md)
- [Firestore Tools Reference](../tools/adk_tools/firestore_adk_tools.py)
- [Vision/OCR Tools](../tools/adk_tools/vision_adk_tools.py)
- [Batch Processing Script](../scripts/batch_process_invoices.py)
