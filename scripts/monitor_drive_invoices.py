"""
Drive Invoice Monitor

Monitors Google Drive folders (Invoices_Input, Expense_Receipts) for new files
and processes them automatically via OCR + Firestore.

ROUTING LOGIC:
  - Documents with OIB, invoice number, and line items -> vendor_invoices (URA)
  - Simple cash receipts without structured data -> expense_records
  - UBL/XML files -> vendor_invoices via UBL parser (when available)

Designed to be called by the scheduler on a recurring basis (e.g., every hour).
Tracks processed files to avoid duplicates.

Usage:
    python scripts/monitor_drive_invoices.py [--folder invoices_input] [--dry-run]
"""

import asyncio
import argparse
import os
import sys
import json
import logging
import time
from typing import List, Dict, Any, Set
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# File to track already-processed Drive file IDs
PROCESSED_IDS_FILE = Path(__file__).parent.parent / "config" / "drive_processed_ids.json"


def load_processed_ids() -> Set[str]:
    """Load set of already-processed Drive file IDs."""
    if not PROCESSED_IDS_FILE.exists():
        return set()
    try:
        with open(PROCESSED_IDS_FILE, 'r') as f:
            data = json.load(f)
        return set(data.get("processed_ids", []))
    except Exception as e:
        logger.error(f"Failed to load processed IDs: {e}")
        return set()


def save_processed_ids(ids: Set[str]) -> None:
    """Save processed file IDs to disk."""
    try:
        with open(PROCESSED_IDS_FILE, 'w') as f:
            json.dump({
                "processed_ids": list(ids),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save processed IDs: {e}")


async def find_new_files(folder_alias: str, processed_ids: Set[str]) -> List[Dict[str, Any]]:
    """
    Find new (unprocessed) invoice files in a Drive folder.

    Args:
        folder_alias: Drive folder alias (e.g., 'invoices_input', 'expense_receipts')
        processed_ids: Set of already-processed file IDs

    Returns:
        List of new file metadata dicts
    """
    from tools.drive_navigator import DriveNavigator
    from tools.api_implementations.drive_api import drive_search_files
    from tools.google_api_client import create_api_client_auto

    navigator = DriveNavigator()
    await navigator.ensure_structure()
    folder_id = navigator.get_folder_id(folder_alias)

    if not folder_id:
        logger.error(f"Folder '{folder_alias}' not found in Drive structure")
        return []

    credentials = create_api_client_auto().credentials

    # Search for images, PDFs, and XML/UBL documents
    query = (
        f"'{folder_id}' in parents and ("
        f"mimeType='image/jpeg' or mimeType='image/png' or "
        f"mimeType='image/bmp' or mimeType='image/x-ms-bmp' or "
        f"mimeType='application/pdf' or "
        f"mimeType='text/html' or mimeType='application/xhtml+xml' or "
        f"mimeType='text/xml' or mimeType='application/xml'"
        f") and trashed=false"
    )

    result = await drive_search_files(credentials, query, max_results=100)
    all_files = result.get('files', [])

    # Filter out already-processed files
    new_files = [f for f in all_files if f.get('id') not in processed_ids]

    logger.info(f"Folder '{folder_alias}': {len(all_files)} total files, {len(new_files)} new")
    return new_files


def _classify_document(ocr_data: Dict[str, Any], file_name: str) -> str:
    """
    Classify OCR output as 'vendor_invoice' or 'expense_receipt'.

    A document is a vendor invoice (URA) if it has structured data:
    - OIB/tax ID of the vendor
    - An invoice number (not just a receipt number)
    - Line items with quantities and prices
    - Amount > 100 EUR (heuristic for non-trivial invoices)

    Simple cash receipts (kava, taxi, parking) go to expense_records.
    """
    tax_id = ocr_data.get('tax_id', '') or ocr_data.get('vendor_oib', '')
    invoice_no = ocr_data.get('invoice_number', '') or ocr_data.get('receipt_number', '')
    items = ocr_data.get('items', [])
    amount = float(ocr_data.get('total_amount', 0))
    vat = float(ocr_data.get('vat_amount', 0) or ocr_data.get('tax_amount', 0) or 0)

    # UBL/XML files are always vendor invoices
    lower_name = file_name.lower()
    if lower_name.endswith('.xml') or lower_name.endswith('.ubl'):
        return 'vendor_invoice'

    # Score-based classification
    score = 0
    if tax_id and len(tax_id) >= 11:
        score += 3  # Has vendor OIB - strong signal
    if invoice_no and any(c.isdigit() for c in invoice_no):
        score += 2  # Has invoice number
    if len(items) >= 2:
        score += 2  # Multiple line items
    if amount > 100:
        score += 1  # Non-trivial amount
    if vat > 0:
        score += 1  # Has explicit VAT breakdown

    # Threshold: score >= 4 = vendor invoice, else expense receipt
    return 'vendor_invoice' if score >= 4 else 'expense_receipt'


async def _save_as_ubl_vendor_invoice(
    xml_content: bytes, file_id: str, file_name: str
) -> Dict[str, Any]:
    """Parse UBL 2.1 XML and save as vendor invoice via ERP service."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    from services.erp.request_context import ERPRequestContext

    # System context — will be reviewed by accountant
    ctx = ERPRequestContext(
        company_id="default",
        user_id="system:drive_monitor",
        role="system",
    )
    try:
        svc = get_vendor_invoice_service()
        doc = await svc.create_from_ubl(
            xml_input=xml_content,
            ctx=ctx,
            drive_file_id=file_id,
        )
        return {"vendor_invoice_id": doc.get("vendor_invoice_id", ""), "display_id": doc.get("display_id", "")}
    except Exception as exc:
        return {"error": str(exc)}


async def _archive_drive_document(vendor_invoice_id: str, drive_file_id: str) -> Dict[str, Any]:
    """Best-effort: archive original Drive file and update vendor invoice archive metadata."""
    try:
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        from services.erp.request_context import ERPRequestContext

        ctx = ERPRequestContext(
            company_id="default",
            user_id="system:drive_monitor",
            role="system",
        )
        result = await get_vendor_invoice_service().archive_original_document(vendor_invoice_id, ctx)
        return result
    except Exception as exc:
        logger.warning(f"Archive step failed for {vendor_invoice_id}: {exc}")
        return {"archive_status": "error", "error": str(exc)}


async def _save_as_vendor_invoice(
    ocr_data: Dict[str, Any], file_id: str, file_name: str
) -> Dict[str, Any]:
    """Save OCR result as a vendor invoice (URA) in the ERP system."""
    from config.deployment_config import is_erp_enabled

    if not is_erp_enabled():
        return {
            "success": False,
            "skipped": True,
            "reason": "ERP is disabled in the active deployment profile",
        }

    from tools.adk_tools.erp_adk_tools import erp_create_vendor_invoice_from_ocr

    save_result = await erp_create_vendor_invoice_from_ocr(
        merchant_name=ocr_data.get('merchant_name', ''),
        total_amount=float(ocr_data.get('total_amount', 0)),
        transaction_date=ocr_data.get('transaction_date', ''),
        vat_amount=float(ocr_data.get('vat_amount', 0) or ocr_data.get('tax_amount', 0) or 0),
        invoice_number=ocr_data.get('invoice_number', '') or ocr_data.get('receipt_number', ''),
        vendor_oib=ocr_data.get('tax_id', '') or ocr_data.get('vendor_oib', ''),
        expense_category=ocr_data.get('expense_category', 'Ostalo'),
        confidence_score=float(ocr_data.get('confidence_score', 0)),
        scan_file_id=file_id,
        items=ocr_data.get('items', []),
        extraction_notes=f"Source: drive_monitor, File: {file_name}",
    )
    return save_result


async def _save_as_expense_record(
    ocr_data: Dict[str, Any], file_name: str, confidence: float
) -> Dict[str, Any]:
    """Save OCR result as an expense record (simple cash receipt)."""
    from tools.adk_tools.firestore_adk_tools import add_expense_record

    description_parts = [f"Source: drive_monitor, File: {file_name}"]
    if confidence < 0.8:
        description_parts.append("NEEDS REVIEW (low confidence)")
    tax_id = ocr_data.get('tax_id', '')
    if tax_id:
        description_parts.append(f"OIB: {tax_id}")

    save_result = await add_expense_record(
        vendor=ocr_data.get('merchant_name', ''),
        amount=ocr_data.get('total_amount', 0),
        currency=ocr_data.get('currency', 'EUR'),
        date=ocr_data.get('transaction_date', ''),
        category=ocr_data.get('expense_category', 'Ostalo'),
        description=", ".join(description_parts),
        invoice_number=ocr_data.get('receipt_number', ''),
        items=ocr_data.get('items', [])
    )
    return save_result


async def process_file(file_meta: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """
    Process a single file: download, OCR, classify, route to correct store.

    Routing:
      - Structured invoices (OIB + invoice number + items) -> vendor_invoices (URA)
      - Simple cash receipts -> expense_records

    Args:
        file_meta: File metadata from Drive API
        dry_run: If True, only preview without saving

    Returns:
        Processing result dict
    """
    from tools.adk_tools.vision_adk_tools import extract_receipt_data
    from tools.api_implementations.drive_api import drive_get_file
    from tools.google_api_client import create_api_client_auto

    file_id = file_meta.get('id')
    file_name = file_meta.get('name', 'unknown')
    mime_type = file_meta.get('mimeType', 'image/jpeg')

    result = {
        "file_id": file_id,
        "file_name": file_name,
        "status": "pending",
        "routed_to": None,
        "error": None
    }

    try:
        # Download file
        credentials = create_api_client_auto().credentials
        file_data = await drive_get_file(credentials, file_id, include_content=True)

        if not file_data.get('content'):
            result["status"] = "error"
            result["error"] = "Empty file content"
            return result

        # ------------------------------------------------------------------
        # UBL/XML path — bypass OCR entirely
        # ------------------------------------------------------------------
        is_xml = (
            mime_type in ("text/xml", "application/xml")
            or file_name.lower().endswith(".xml")
            or file_name.lower().endswith(".ubl")
        )
        if is_xml:
            result["routed_to"] = "vendor_invoice"
            if dry_run:
                result["status"] = "dry_run"
                result["preview"] = {"classification": "vendor_invoice", "path": "ubl_xml"}
                return result
            save_result = await _save_as_ubl_vendor_invoice(file_data['content'], file_id, file_name)
            if save_result.get('vendor_invoice_id'):
                result["status"] = "success"
                result["vendor_invoice_id"] = save_result.get('vendor_invoice_id', '')
                result["display_id"] = save_result.get('display_id', '')
                result["path"] = "ubl_xml"
                # Best-effort archive — failure is logged but doesn't block intake
                archive_res = await _archive_drive_document(save_result['vendor_invoice_id'], file_id)
                result["archive_status"] = archive_res.get("archive_status", "error")
            else:
                result["status"] = "error"
                result["error"] = f"UBL save failed: {save_result.get('error', 'Unknown')}"
            return result

        # ------------------------------------------------------------------
        # OCR path — images, PDFs, HTML scans
        # ------------------------------------------------------------------

        # OCR with retry for rate limits
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ocr_result = await extract_receipt_data(
                    image_data=file_data['content'],
                    mime_type=mime_type
                )
                if ocr_result.get('status') == 'success':
                    break
                error_msg = str(ocr_result.get('error', ''))
                if '429' in error_msg or 'RESOURCE_EXHAUSTED' in error_msg:
                    if attempt < max_retries - 1:
                        wait = 20 * (attempt + 1)
                        logger.warning(f"Rate limit on {file_name}, waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                result["status"] = "error"
                result["error"] = f"OCR failed: {ocr_result.get('error', 'Unknown')}"
                return result
            except Exception as e:
                if '429' in str(e) and attempt < max_retries - 1:
                    await asyncio.sleep(20 * (attempt + 1))
                    continue
                result["status"] = "error"
                result["error"] = str(e)
                return result

        receipt_data = ocr_result.get('data', {})
        merchant = receipt_data.get('merchant_name', '')
        confidence = receipt_data.get('confidence_score', 0)

        # Validate: skip if Lux Tech detected as vendor (our own company)
        if 'lux tech' in merchant.lower():
            result["status"] = "skipped"
            result["error"] = "Lux Tech detected as vendor (OCR misidentification)"
            return result

        tax_id = receipt_data.get('tax_id', '')
        if tax_id and '47034854402' in tax_id:
            result["status"] = "skipped"
            result["error"] = "Customer OIB detected as vendor OIB"
            return result

        # Classify: vendor invoice or expense receipt
        doc_type = _classify_document(receipt_data, file_name)
        result["routed_to"] = doc_type

        if dry_run:
            result["status"] = "dry_run"
            result["preview"] = {
                "merchant": merchant,
                "amount": receipt_data.get('total_amount'),
                "date": receipt_data.get('transaction_date'),
                "confidence": confidence,
                "classification": doc_type,
            }
            return result

        # Route to correct store
        if doc_type == 'vendor_invoice':
            save_result = await _save_as_vendor_invoice(receipt_data, file_id, file_name)
            if save_result.get('status') == 'success' or save_result.get('vendor_invoice_id'):
                result["status"] = "success"
                result["vendor_invoice_id"] = save_result.get('vendor_invoice_id', '')
                result["display_id"] = save_result.get('display_id', '')
                result["merchant"] = merchant
                result["amount"] = receipt_data.get('total_amount', 0)
                result["confidence"] = confidence
            else:
                result["status"] = "error"
                result["error"] = f"ERP save failed: {save_result.get('error', save_result.get('message', 'Unknown'))}"
        else:
            save_result = await _save_as_expense_record(receipt_data, file_name, confidence)
            if save_result.get('status') == 'success':
                result["status"] = "success"
                result["expense_id"] = save_result.get('expense_id', '')
                result["merchant"] = merchant
                result["amount"] = receipt_data.get('total_amount', 0)
                result["confidence"] = confidence
            else:
                result["status"] = "error"
                result["error"] = f"Firestore save failed: {save_result.get('error', 'Unknown')}"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"Error processing {file_name}: {e}")

    return result


async def monitor_folder(folder_alias: str = "invoices_input", dry_run: bool = False, delay: float = 12.0) -> Dict[str, Any]:
    """
    Monitor a Drive folder for new invoices and process them.

    Args:
        folder_alias: Drive folder alias
        dry_run: Preview only, don't save
        delay: Delay between processing files (rate limiting)

    Returns:
        Summary dict with results
    """
    start_time = time.time()
    processed_ids = load_processed_ids()

    print(f"\n{'='*60}")
    print(f"Drive Invoice Monitor - {folder_alias}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Previously processed: {len(processed_ids)} files")
    print(f"{'='*60}\n")

    # Find new files
    new_files = await find_new_files(folder_alias, processed_ids)

    if not new_files:
        print("No new files found.")
        return {"new_files": 0, "processed": 0, "errors": 0, "skipped": 0}

    print(f"Found {len(new_files)} new files to process\n")

    results = {
        "new_files": len(new_files),
        "processed": 0,
        "errors": 0,
        "skipped": 0,
        "details": []
    }

    for i, file_meta in enumerate(new_files, 1):
        file_name = file_meta.get('name', 'unknown')
        print(f"[{i}/{len(new_files)}] Processing: {file_name}")

        result = await process_file(file_meta, dry_run=dry_run)
        results["details"].append(result)

        if result["status"] == "success":
            results["processed"] += 1
            processed_ids.add(file_meta['id'])
            routed = result.get('routed_to', 'unknown')
            ref_id = result.get('display_id') or result.get('vendor_invoice_id') or result.get('expense_id', '')
            print(f"   OK [{routed}]: {result.get('merchant', '?')} - {result.get('amount', 0)} EUR -> {ref_id}")
        elif result["status"] == "skipped":
            results["skipped"] += 1
            processed_ids.add(file_meta['id'])  # Mark as processed to avoid retrying
            print(f"   SKIP: {result.get('error', '?')}")
        elif result["status"] == "dry_run":
            preview = result.get("preview", {})
            classification = preview.get('classification', '?')
            print(f"   DRY RUN [{classification}]: {preview.get('merchant', '?')} - {preview.get('amount', 0)} (conf: {preview.get('confidence', 0):.0%})")
        else:
            results["errors"] += 1
            print(f"   ERROR: {result.get('error', 'Unknown')}")

        # Rate limit delay between files
        if i < len(new_files):
            await asyncio.sleep(delay)

    # Save updated processed IDs
    if not dry_run:
        save_processed_ids(processed_ids)

    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  New files: {results['new_files']}")
    print(f"  Processed: {results['processed']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"  Errors: {results['errors']}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"{'='*60}\n")

    return results


async def monitor_all_folders(dry_run: bool = False) -> Dict[str, Any]:
    """Monitor Invoices_Input, Vendor_Invoices_Input, and Expense_Receipts folders."""
    all_results = {}

    for folder in ["invoices_input", "vendor_invoices_input", "expense_receipts"]:
        print(f"\n--- Monitoring folder: {folder} ---")
        result = await monitor_folder(folder, dry_run=dry_run)
        all_results[folder] = result

    total_new = sum(r.get("new_files", 0) for r in all_results.values())
    total_processed = sum(r.get("processed", 0) for r in all_results.values())

    print(f"\nTotal across all folders: {total_new} new, {total_processed} processed")
    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor Drive folders for new invoices")
    parser.add_argument("--folder", default="all", help="Folder alias or 'all' (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't save")
    parser.add_argument("--delay", type=float, default=12.0, help="Delay between files in seconds (default: 12)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if args.folder == "all":
        asyncio.run(monitor_all_folders(dry_run=args.dry_run))
    else:
        asyncio.run(monitor_folder(args.folder, dry_run=args.dry_run, delay=args.delay))
