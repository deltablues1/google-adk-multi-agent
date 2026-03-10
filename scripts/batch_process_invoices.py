"""
Batch Invoice Processing Script

Automatically processes all invoices from a Drive folder and populates Firestore databases:
- expense-records: All receipt/invoice data
- products: Extracted product items from invoices
- customers: Customer data from incoming invoices

This script is designed to populate databases from historical invoices.

Usage:
    python scripts/batch_process_invoices.py --folder "Invoices_Input"

Or process all invoices in default folder:
    python scripts/batch_process_invoices.py

Prerequisites:
    1. Expense agent configured with OCR and Firestore tools
    2. Drive folder with invoice images/PDFs
    3. GOOGLE_CLOUD_PROJECT set in .env
    4. OAuth credentials available
"""

import asyncio
import argparse
import os
import sys
from typing import List, Dict, Any
from datetime import datetime, timezone
from dotenv import load_dotenv
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment
load_dotenv()


async def find_invoices_in_folder(folder_alias: str = "invoices_input") -> List[Dict[str, Any]]:
    """
    Find all invoice images/PDFs in a Drive folder.

    Args:
        folder_alias: Drive folder alias from drive_map.yaml (default: "invoices_input")

    Returns:
        List of file metadata dictionaries
    """
    from tools.drive_navigator import get_drive_navigator
    from tools.api_implementations.drive_api import drive_search_files
    from tools.google_api_client import create_api_client_auto

    print(f"🔍 Searching for invoices in folder: {folder_alias}")

    # Get folder ID
    navigator = await get_drive_navigator()
    folder_id = navigator.get_folder_id(folder_alias)

    if not folder_id:
        print(f"❌ Error: Folder '{folder_alias}' not found")
        print("   Available folders:", list(navigator.folder_map.keys()))
        return []

    # Search for images and PDFs
    credentials = create_api_client_auto().credentials

    queries = [
        # Image files (JPEG, PNG, BMP)
        f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/bmp' or mimeType='image/x-ms-bmp') and trashed=false",
        # PDF files
        f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false",
        # HTML files (HTM)
        f"'{folder_id}' in parents and (mimeType='text/html' or mimeType='application/xhtml+xml') and trashed=false"
    ]

    all_files = []
    file_type_counts = {}

    for i, query in enumerate(queries):
        # Use max_results=1000 to fetch all files with pagination
        result = await drive_search_files(credentials, query, max_results=1000)
        files = result.get('files', [])
        all_files.extend(files)

        # Debug: Show file count per type
        type_names = ["Images (JPEG, PNG, BMP)", "PDFs", "HTML files"][i]
        file_type_counts[type_names] = len(files)
        print(f"   - {type_names}: {len(files)} files")

    print(f"\n✅ Found {len(all_files)} invoice files total")
    return all_files


async def process_single_invoice(
    file_id: str,
    file_name: str,
    mime_type: str,
    index: int,
    total: int
) -> Dict[str, Any]:
    """
    Process a single invoice using Expense agent.

    Returns:
        Dictionary with processing results
    """
    from tools.adk_tools.vision_adk_tools import extract_receipt_data
    from tools.adk_tools.firestore_adk_tools import (
        add_expense_record,
        add_product,
        add_customer,
        find_customer
    )
    from tools.api_implementations.drive_api import drive_get_file
    from tools.google_api_client import create_api_client_auto

    print(f"\n[{index}/{total}] Processing: {file_name}")

    result = {
        "file_name": file_name,
        "file_id": file_id,
        "status": "pending",
        "expense_created": False,
        "sheet_updated": False,
        "products_created": 0,
        "customer_created": False,
        "error": None
    }

    try:
        # Step 1: Download file
        print(f"   📥 Downloading file...")
        credentials = create_api_client_auto().credentials
        file_data = await drive_get_file(credentials, file_id, include_content=True)

        if not file_data.get('content'):
            result["status"] = "error"
            result["error"] = "Empty file content"
            print(f"   ❌ Error: Empty file content")
            return result

        # Step 2: OCR extraction with retry for 429 errors
        print(f"   🔍 Extracting data with OCR...")

        # Retry logic for rate limiting (429 errors)
        max_retries = 5  # Increased to 5 for better recovery with quota limits
        retry_delay = 15  # seconds (increased to handle strict 10 RPM limit)

        for attempt in range(max_retries):
            try:
                # Extract receipt data using vision tool
                ocr_result = await extract_receipt_data(
                    image_data=file_data['content'],
                    mime_type=mime_type  # Use full MIME type (e.g., 'image/jpeg', 'application/pdf')
                )

                if ocr_result.get('status') == 'success':
                    break  # Success - exit retry loop

                # Check if it's a rate limit error
                error_msg = str(ocr_result.get('error', ''))
                if '429' in error_msg or 'RESOURCE_EXHAUSTED' in error_msg:
                    if attempt < max_retries - 1:
                        print(f"   ⚠️  Rate limit (429) - waiting {retry_delay}s before retry {attempt + 2}/{max_retries}...")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        result["status"] = "error"
                        result["error"] = f"OCR failed after {max_retries} retries: Rate limit"
                        print(f"   ❌ {result['error']}")
                        return result
                else:
                    # Other error - don't retry
                    result["status"] = "error"
                    result["error"] = f"OCR failed: {ocr_result.get('error', 'Unknown error')}"
                    print(f"   ❌ OCR failed: {result['error']}")
                    return result

            except Exception as e:
                if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
                    if attempt < max_retries - 1:
                        print(f"   ⚠️  Rate limit (429) - waiting {retry_delay}s before retry {attempt + 2}/{max_retries}...")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        result["status"] = "error"
                        result["error"] = f"OCR failed after {max_retries} retries: {str(e)}"
                        print(f"   ❌ {result['error']}")
                        return result
                else:
                    # Other exception
                    result["status"] = "error"
                    result["error"] = f"OCR exception: {str(e)}"
                    print(f"   ❌ {result['error']}")
                    return result

        receipt_data = ocr_result.get('data', {})

        # DEBUG: Show what OCR extracted
        print(f"   🔍 OCR Extracted:")
        print(f"      Vendor: {receipt_data.get('merchant_name', 'N/A')}")
        print(f"      Date: {receipt_data.get('transaction_date', 'N/A')}")
        print(f"      Amount: {receipt_data.get('total_amount', 'N/A')} {receipt_data.get('currency', 'N/A')}")
        print(f"      Invoice#: {receipt_data.get('receipt_number', 'N/A')}")
        print(f"      OIB: {receipt_data.get('tax_id', 'N/A')}")
        print(f"      Tax Base: {receipt_data.get('tax_base', 'N/A')}")
        print(f"      Tax Amount: {receipt_data.get('tax_amount', 'N/A')}")

        # Post-processing: Fix common OCR mistakes for HTML invoices
        merchant_name_raw = receipt_data.get('merchant_name', '')

        # If vendor looks like an email, try to infer real vendor from invoice number
        if '@' in merchant_name_raw or merchant_name_raw.lower() in ['email', 'n/a', 'unknown']:
            invoice_number = receipt_data.get('receipt_number', '')

            # Erste Bank detection (invoice format: XXXXXX-AUT305-X-XXXX-PPR)
            if 'AUT305' in invoice_number or 'PPR' in invoice_number:
                receipt_data['merchant_name'] = 'Erste Bank'
                receipt_data['tax_id'] = None  # Bankarske usluge nemaju OIB
                print(f"   ✅ Corrected vendor: Email → Erste Bank")

            # Dodaj druge patterne ako treba
            # elif 'pattern' in invoice_number:
            #     receipt_data['merchant_name'] = 'Vendor Name'

        # Step 3: VALIDATION - Check for Lux Tech misdetection
        merchant_name = receipt_data.get('merchant_name', '')
        tax_id = receipt_data.get('tax_id', '')

        # Detect if OCR extracted customer data instead of vendor
        if 'lux tech' in merchant_name.lower() or 'luxtech' in merchant_name.lower():
            print(f"   ❌ ERROR: OCR extracted customer (Lux Tech) instead of vendor - SKIPPING")
            result["status"] = "error"
            result["error"] = "OCR misidentified customer as vendor (Lux Tech detected)"
            return result

        if tax_id and ('47034854402' in tax_id or 'HR47034854402' in tax_id):
            print(f"   ❌ ERROR: OCR extracted customer OIB instead of vendor OIB - SKIPPING")
            result["status"] = "error"
            result["error"] = "OCR misidentified customer OIB (HR47034854402 detected)"
            return result

        # Additional validation: Ensure vendor name is not empty
        if not merchant_name or merchant_name.strip() in ['', 'Unknown', 'N/A']:
            print(f"   ❌ ERROR: Vendor name missing or invalid - SKIPPING")
            result["status"] = "error"
            result["error"] = "Vendor name not extracted"
            return result

        # Step 4: Advanced duplicate detection (invoice number + date + amount)
        invoice_number = receipt_data.get('receipt_number', '')
        transaction_date = receipt_data.get('transaction_date', '')
        total_amount = receipt_data.get('total_amount', 0.0)

        if invoice_number or (transaction_date and total_amount):
            from tools.database.database_handler import get_database_handler

            db = get_database_handler()

            # Check multiple criteria to avoid duplicates
            filters = []

            # Primary check: invoice number (if available)
            if invoice_number:
                filters.append(("invoice_number", "==", invoice_number))

            # Secondary check: date + amount (if invoice number missing)
            if transaction_date and total_amount and not invoice_number:
                filters.append(("date", "==", transaction_date))

            if filters:
                existing_docs = await db.query_documents(
                    collection="expense-records",
                    filters=filters,
                    limit=5
                )

                # Double-check with amount for extra safety
                for doc in existing_docs:
                    existing_amount = doc.get('amount', 0)
                    existing_date = doc.get('date', '')

                    # Match found if:
                    # - Same invoice number, OR
                    # - Same date AND same amount (within 0.01 tolerance)
                    if invoice_number and doc.get('invoice_number') == invoice_number:
                        print(f"   ⚠️  DUPLICATE: Invoice {invoice_number} already exists - SKIPPING")
                        result["status"] = "skipped"
                        result["error"] = f"Duplicate invoice: {invoice_number}"
                        return result

                    if existing_date == transaction_date and abs(existing_amount - total_amount) < 0.01:
                        print(f"   ⚠️  DUPLICATE: Same date ({transaction_date}) and amount ({total_amount}) - SKIPPING")
                        result["status"] = "skipped"
                        result["error"] = f"Duplicate by date+amount"
                        return result

        # Step 4: Validate vendor name using OIB lookup
        merchant_name_ocr = receipt_data.get('merchant_name', 'Unknown')
        tax_id_raw = receipt_data.get('tax_id', '')

        # Normalize OIB for lookup
        if tax_id_raw and not tax_id_raw.startswith('HR') and tax_id_raw.isdigit():
            tax_id_normalized = f"HR{tax_id_raw}"
        else:
            tax_id_normalized = tax_id_raw

        # Manual vendor mapping for known OCR issues (OIB → Canonical Name)
        KNOWN_VENDORS = {
            'HR95243482140': 'SMIT-COMMERCE d.o.o.',  # Often OCR'd as "STUPNIK - MP", "CE d.o.o.", "Snježana Carin", etc.
            'HR46108893754': 'SPAR HRVATSKA d.o.o.',
            'HR29524210204': 'A1 Hrvatska d.o.o.',
            'HR36365310424': 'SCHRACK TECHNIK d.o.o.',
            'HR16372522596': 'TEVETRON d.o.o.',
            'HR52101284898': 'ZELENI ELEMENTI d.o.o.',
            'HR20246776105': 'Arrslog d.o.o.',
            'HR43227166836': 'MIKROTRON d.o.o.',
            'HR71814187727': 'FDS TRGOVINA d.o.o.',
            'HR18290972213': 'ELMATIS d.o.o.',
        }

        # First check: Use manual mapping if OIB is known
        if tax_id_normalized in KNOWN_VENDORS:
            canonical_name = KNOWN_VENDORS[tax_id_normalized]
            if canonical_name.lower() != merchant_name_ocr.lower():
                print(f"   🔍 Manual Mapping: '{merchant_name_ocr}' → '{canonical_name}' (OIB: {tax_id_normalized})")
                receipt_data['merchant_name'] = canonical_name
                merchant_name_ocr = canonical_name  # Update for subsequent checks

        # Vendor validation: Check if OIB exists in database with different name
        if tax_id_normalized:
            from tools.database.database_handler import get_database_handler
            db_temp = get_database_handler()

            try:
                # Look up existing records with this OIB
                existing_records = await db_temp.query_documents(
                    "expense-records",
                    filters=[],  # We'll filter manually since Firestore filter is deprecated
                    limit=100
                )

                # Filter by tax_id in Python
                matching_records = [r for r in existing_records if r.get('tax_id') == tax_id_normalized]

                if matching_records:
                    # Get the most common vendor name for this OIB
                    vendor_names = [r.get('vendor') for r in matching_records if r.get('vendor')]

                    if vendor_names:
                        # Find most common name
                        from collections import Counter
                        name_counts = Counter(vendor_names)
                        canonical_name, count = name_counts.most_common(1)[0]

                        # Check if OCR name looks incomplete (heuristics)
                        ocr_looks_incomplete = (
                            len(merchant_name_ocr) < 10 or  # Too short
                            not any(suffix in merchant_name_ocr.lower() for suffix in ['d.o.o.', 'd.d.', 'obrt']) or  # Missing legal form
                            merchant_name_ocr.count(' ') < 1  # Single word (likely incomplete)
                        )

                        # If names differ significantly and OCR looks incomplete, use canonical name
                        if canonical_name.lower() != merchant_name_ocr.lower() and ocr_looks_incomplete:
                            print(f"   🔍 OIB Lookup: '{merchant_name_ocr}' → '{canonical_name}' (matched {count} existing records)")
                            receipt_data['merchant_name'] = canonical_name

            except Exception as e:
                print(f"   ⚠️  Vendor lookup failed: {e}")

        # Step 5: Validate and fix category
        # Valid categories: Hrana, Prijevoz, Ured, Režije, Ostalo
        valid_categories = ['Hrana', 'Prijevoz', 'Ured', 'Režije', 'Ostalo']
        category = receipt_data.get('expense_category', 'Ostalo')

        # Category mapping for English/invalid categories
        category_mapping = {
            'Food': 'Hrana',
            'Meals': 'Hrana',  # Added
            'Restaurant': 'Hrana',  # Added
            'Groceries': 'Hrana',  # Added
            'Transport': 'Prijevoz',
            'Transportation': 'Prijevoz',  # Added
            'Fuel': 'Prijevoz',  # Added
            'Office': 'Ured',
            'Office Supplies': 'Ured',  # Added
            'Electronics': 'Ured',  # Added
            'Utilities': 'Režije',
            'Bills': 'Režije',  # Added
            'Other': 'Ostalo',
        }

        # Map or default to Ostalo
        if category not in valid_categories:
            category = category_mapping.get(category, 'Ostalo')
            print(f"   ℹ️  Mapped category '{receipt_data.get('expense_category')}' → '{category}'")

        # Normalize OIB - add HR prefix if missing
        tax_id_raw = receipt_data.get('tax_id', '')
        normalized_oib = tax_id_raw
        if tax_id_raw and not tax_id_raw.startswith('HR') and tax_id_raw.isdigit():
            normalized_oib = f"HR{tax_id_raw}"

        # Step 5: Save to expense-records
        print(f"   💾 Saving to expense-records (OIB: {normalized_oib})...")

        # Prepare expense data with normalized OIB
        from tools.database.database_handler import get_database_handler
        db = get_database_handler()

        expense_data = {
            "vendor": receipt_data.get('merchant_name', 'Unknown'),
            "amount": float(receipt_data.get('total_amount', 0.0)),
            "currency": receipt_data.get('currency', 'EUR'),
            "date": receipt_data.get('transaction_date', datetime.now().strftime('%Y-%m-%d')),
            "category": category,
            "invoice_number": receipt_data.get('receipt_number', ''),
            "payment_method": receipt_data.get('payment_method', ''),
            "tax_id": normalized_oib,  # Normalized OIB with HR prefix
            "items": receipt_data.get('items', []),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        # Debug: Verify OIB is in expense_data
        print(f"   🔍 DEBUG - expense_data contains tax_id: {expense_data.get('tax_id')}")

        try:
            expense_id = await db.add_document("expense-records", expense_data)
            expense_result = {
                "status": "success",
                "expense_id": expense_id
            }
        except Exception as e:
            expense_result = {
                "status": "error",
                "error": str(e)
            }

        if expense_result.get('status') == 'success':
            result["expense_created"] = True
            print(f"   ✅ Expense record created: {expense_result.get('expense_id')}")

            # Step 5: DUAL STORAGE - Also save to Google Sheets
            print(f"   📊 Saving to Google Sheets...")
            try:
                from tools.api_implementations.sheets_api import sheets_append_values
                from tools.google_api_client import create_api_client_auto

                # Ulazni računi 2025 spreadsheet
                sheet_id = "1Sgzraal9N8DFj8ei8I9aI_zMDolnhP1FVKwRYjo8YYg"

                # Format date for Croatian locale (DD.MM.YYYY)
                transaction_date_raw = receipt_data.get('transaction_date', '')
                formatted_date = transaction_date_raw
                if transaction_date_raw:
                    try:
                        # Parse YYYY-MM-DD → DD.MM.YYYY
                        from datetime import datetime as dt
                        date_obj = dt.strptime(transaction_date_raw, '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        print(f"   📅 Date conversion: {transaction_date_raw} → {formatted_date}")
                    except Exception as e:
                        formatted_date = transaction_date_raw  # Fallback to raw
                        print(f"   ⚠️  Date conversion failed: {e}")

                # Normalize OIB - always add "HR" prefix if missing
                tax_id_raw = receipt_data.get('tax_id', '')
                normalized_oib = tax_id_raw
                if tax_id_raw and not tax_id_raw.startswith('HR'):
                    # Add HR prefix if it's just numbers
                    if tax_id_raw.isdigit():
                        normalized_oib = f"HR{tax_id_raw}"

                # Handle None values - convert to 0 for Sheets
                tax_base = receipt_data.get('tax_base')
                tax_amount = receipt_data.get('tax_amount')
                total_amount = receipt_data.get('total_amount', 0.0)

                # Convert None to 0.0 for numeric fields
                tax_base = float(tax_base) if tax_base is not None else 0.0
                tax_amount = float(tax_amount) if tax_amount is not None else 0.0

                # Columns: RedBr, BrojRacuna, Datum, Dobavljac, OIB, Osnovica, PDV, Ukupno
                row_data = [
                    "",  # RedBr - auto-numbered by sheet
                    receipt_data.get('receipt_number', ''),  # BrojRacuna
                    formatted_date,  # Datum (DD.MM.YYYY)
                    receipt_data.get('merchant_name', ''),  # Dobavljac
                    normalized_oib if normalized_oib else "",  # OIB (empty string if None)
                    tax_base,  # Osnovica (0.0 if None)
                    tax_amount,  # PDV (0.0 if None)
                    total_amount  # Ukupno
                ]

                credentials = create_api_client_auto().credentials
                await sheets_append_values(
                    credentials,
                    sheet_id,
                    "A:H",  # Append to columns A through H
                    [row_data],
                    value_input_option="RAW"  # Use RAW to prevent date interpretation issues
                )

                result["sheet_updated"] = True
                print(f"   ✅ Google Sheets updated")

            except Exception as e:
                print(f"   ⚠️  Sheets update failed: {e}")
                # Don't fail the whole operation if Sheets fails

        else:
            result["error"] = f"Failed to create expense: {expense_result.get('error')}"
            print(f"   ⚠️  Expense creation failed: {result['error']}")

        # Step 6: Extract products from line items
        items = receipt_data.get('items', [])
        if items:
            print(f"   📦 Extracting {len(items)} products...")
            for item in items:
                # Handle None values from OCR
                unit_price = item.get('unit_price')
                if unit_price is None:
                    unit_price = 0.0

                product_result = await add_product(
                    name=item.get('description', 'Unknown Product'),
                    price=float(unit_price),  # Ensure float
                    currency=receipt_data.get('currency', 'EUR'),
                    category=receipt_data.get('expense_category', ''),
                    supplier=receipt_data.get('merchant_name', ''),
                    description=f"Extracted from invoice: {file_name}"
                )
                if product_result.get('status') == 'success':
                    result["products_created"] += 1

            print(f"   ✅ Created {result['products_created']} product records")

        # Step 6: Extract customer if present (for incoming invoices)
        customer_info = receipt_data.get('customer_info')
        if customer_info and customer_info.get('email'):
            print(f"   👤 Checking customer: {customer_info.get('email')}")

            # Check if customer already exists
            find_result = await find_customer(customer_info['email'])

            if not find_result.get('found'):
                # Create new customer
                customer_result = await add_customer(
                    name=customer_info.get('name', ''),
                    email=customer_info.get('email', ''),
                    company=customer_info.get('company', ''),
                    phone=customer_info.get('phone', ''),
                    address=customer_info.get('address', '')
                )

                if customer_result.get('status') == 'success':
                    result["customer_created"] = True
                    print(f"   ✅ Customer created: {customer_result.get('customer_id')}")
            else:
                print(f"   ℹ️  Customer already exists")

        result["status"] = "success"
        print(f"   ✅ Processing complete!")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"   ❌ Error: {e}")

    return result


async def batch_process_invoices(folder_alias: str = "invoices_input", limit: int = None, delay: int = 12):
    """
    Main batch processing function.

    Args:
        folder_alias: Drive folder alias to process
        limit: Maximum number of invoices to process (None = all)
        delay: Delay in seconds between requests
    """
    print("=" * 70)
    print("Batch Invoice Processing - Firestore Database Population")
    print("=" * 70)

    # Step 1: Find all invoices
    invoices = await find_invoices_in_folder(folder_alias)

    if not invoices:
        print("\n⚠️  No invoices found in folder")
        return

    # Apply limit if specified
    total_found = len(invoices)
    if limit and limit < len(invoices):
        invoices = invoices[:limit]
        print(f"\n⚠️  Limiting to first {limit} invoices (found {total_found} total)")

    # Step 2: Process each invoice
    print(f"\n📋 Processing {len(invoices)} invoices...")
    print(f"⏱️  Rate limiting: {delay} second delay between requests")
    print(f"📊 Quota: 10 requests per minute (1 request every 6s minimum)")
    print(f"💡 Estimated time: {len(invoices) * delay // 60} min {len(invoices) * delay % 60} sec")
    print("\n⚠️  With 10 RPM quota limit:")
    print(f"   - Current delay: {delay}s = {60/delay:.1f} requests per minute")
    if 60/delay > 10:
        print(f"   - ❌ TOO FAST! Will hit rate limits. Use --delay 7 or higher")
    else:
        print(f"   - ✅ Safe rate (under 10 RPM)")
    print("=" * 70)

    results = []
    for i, invoice in enumerate(invoices, 1):
        result = await process_single_invoice(
            file_id=invoice['id'],
            file_name=invoice['name'],
            mime_type=invoice.get('mimeType', 'image/jpeg'),
            index=i,
            total=len(invoices)
        )
        results.append(result)

        # Rate limiting: Wait between requests to avoid 429 errors
        if i < len(invoices):  # Don't wait after last invoice
            print(f"   ⏳ Waiting {delay}s before next request...")
            await asyncio.sleep(delay)

    # Step 3: Summary
    print("\n" + "=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)

    successful = sum(1 for r in results if r['status'] == 'success')
    failed = sum(1 for r in results if r['status'] == 'error')
    skipped = sum(1 for r in results if r['status'] == 'skipped')
    total_products = sum(r['products_created'] for r in results)
    total_customers = sum(1 for r in results if r['customer_created'])
    total_sheets = sum(1 for r in results if r.get('sheet_updated', False))

    print(f"\n📊 Results:")
    print(f"   ✅ Successfully processed: {successful}/{len(invoices)}")
    print(f"   ⚠️  Skipped (duplicates): {skipped}/{len(invoices)}")
    print(f"   ❌ Failed: {failed}/{len(invoices)}")
    print(f"\n💾 Data Storage:")
    print(f"   🔥 Firestore expense records: {successful}")
    print(f"   📊 Google Sheets rows added: {total_sheets}")
    print(f"   📦 Products extracted: {total_products}")
    print(f"   👤 Customers extracted: {total_customers}")

    # Show failed invoices
    if failed > 0:
        print(f"\n⚠️  Failed invoices:")
        for r in results:
            if r['status'] == 'error':
                print(f"   - {r['file_name']}: {r['error']}")

    print("\n" + "=" * 70)
    print("✅ Batch processing complete!")
    print("=" * 70)

    print("\n📋 Next steps:")
    print("   1. Review Firestore collections in Google Cloud Console")
    print("   2. Verify data accuracy")
    print("   3. Process failed invoices manually if needed")
    print("   4. Check expense tracking in your application")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Batch process invoices from Drive folder to populate Firestore databases"
    )
    parser.add_argument(
        '--folder',
        default='invoices_input',
        help='Drive folder alias to process (default: invoices_input)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of invoices to process (default: all)'
    )
    parser.add_argument(
        '--delay',
        type=int,
        default=12,
        help='Delay in seconds between requests (default: 12, safe for 10 RPM quota limit)'
    )

    args = parser.parse_args()

    # Run async batch processing
    asyncio.run(batch_process_invoices(
        folder_alias=args.folder,
        limit=args.limit,
        delay=args.delay
    ))


if __name__ == "__main__":
    main()
