"""
Bulk Invoice Import from Local Folders

Reads PDFs from local folder structure and imports into Firestore:
  - racuni/ulazni/YYYY/MM/*.pdf  -> vendor_invoices (via VendorInvoiceService.create_from_ocr)
  - racuni/izlazni/YYYY/MM/*.pdf -> invoices_b2c / invoices_b2b (direct Firestore write)

Uses Gemini 2.5 Flash for OCR extraction.

Usage:
    python scripts/bulk_import_invoices.py --root "C:/path/to/racuni"
    python scripts/bulk_import_invoices.py --root "C:/path/to/racuni" --direction ulazni
    python scripts/bulk_import_invoices.py --root "C:/path/to/racuni" --year 2024
    python scripts/bulk_import_invoices.py --root "C:/path/to/racuni" --limit 5 --dry-run
"""

import asyncio
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".htm", ".html"}
MIME_MAP = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".htm": "text/html",
    ".html": "text/html",
}
DEFAULT_COMPANY_ID = "lux-tech"
DEFAULT_USER_ID = "tomislav.luxtech@gmail.com"

# Rate limiting
DEFAULT_DELAY = 7  # seconds between OCR calls (~8.5 RPM, safe for 10 RPM quota)
MAX_RETRIES = 4
RETRY_BASE_DELAY = 20  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def discover_invoices(root: str, direction: Optional[str], year: Optional[int],
                      month: Optional[int]) -> list[dict]:
    """Walk folder tree and return list of invoice file info dicts."""
    root_path = Path(root)
    if not root_path.exists():
        logger.error(f"Root path does not exist: {root}")
        return []

    results = []
    directions = [direction] if direction else ["ulazni", "izlazni"]

    for d in directions:
        dir_path = root_path / d
        if not dir_path.exists():
            logger.warning(f"Directory not found: {dir_path}")
            continue

        for year_dir in sorted(dir_path.iterdir()):
            if not year_dir.is_dir():
                continue
            try:
                y = int(year_dir.name)
            except ValueError:
                continue
            if year and y != year:
                continue

            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                # Handle "01siječanj", "02veljača", or plain "01", "1"
                m_match = re.match(r"^(\d{1,2})", month_dir.name)
                if not m_match:
                    continue
                m = int(m_match.group(1))
                if month and m != month:
                    continue

                for f in sorted(month_dir.iterdir()):
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                        results.append({
                            "path": str(f),
                            "filename": f.name,
                            "direction": d,
                            "year": y,
                            "month": m,
                            "mime_type": MIME_MAP.get(f.suffix.lower(), "application/pdf"),
                        })

    return results


def file_dedup_hash(path: str) -> str:
    """SHA-256 of file content for dedup."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


async def ocr_with_retry(handler, method_name: str, image_b64: str, mime_type: str) -> dict:
    """Call OCR method with exponential backoff on 429."""
    method = getattr(handler, method_name)
    for attempt in range(MAX_RETRIES):
        try:
            return await method(image_b64, mime_type)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Rate limited (attempt {attempt+1}/{MAX_RETRIES}), waiting {wait}s...")
                await asyncio.sleep(wait)
            else:
                raise
    raise RuntimeError(f"OCR failed after {MAX_RETRIES} retries (rate limit)")


# ---------------------------------------------------------------------------
# Import: Incoming (ulazni) → vendor_invoices
# ---------------------------------------------------------------------------
async def import_incoming(file_info: dict, ctx, dedup_set: set, dry_run: bool) -> dict:
    """Import a single incoming (vendor) invoice via VendorInvoiceService.create_from_ocr."""
    from tools.handlers.vision_handler import VisionHandler
    from services.erp.vendor_invoice_service import get_vendor_invoice_service

    path = file_info["path"]
    result = {"file": file_info["filename"], "direction": "ulazni", "status": "pending"}

    # Read and encode file
    with open(path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("utf-8")

    # Dedup by file hash
    fhash = hashlib.sha256(raw).hexdigest()
    if fhash in dedup_set:
        result["status"] = "skipped"
        result["reason"] = "duplicate file (same content)"
        return result
    dedup_set.add(fhash)

    # OCR
    handler = VisionHandler()
    try:
        ocr_data = await ocr_with_retry(handler, "extract_receipt_data", b64, file_info["mime_type"])
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"OCR failed: {e}"
        return result

    # Validation: reject if OCR picked up our own company as vendor
    vendor = ocr_data.get("merchant_name") or ""
    oib = ocr_data.get("tax_id") or ""
    if "lux tech" in vendor.lower() or "47034854402" in oib:
        result["status"] = "error"
        result["error"] = "OCR extracted seller instead of vendor"
        return result

    # HRK→EUR conversion for pre-2023 invoices
    currency = (ocr_data.get("currency") or "EUR").upper()
    if currency == "HRK":
        rate = 7.53450  # Fixed EUR/HRK conversion rate
        for field in ("total_amount", "tax_base", "tax_amount", "vat_amount"):
            val = ocr_data.get(field)
            if val is not None:
                ocr_data[field] = round(float(val) / rate, 2)
        ocr_data["_hrk_original"] = {
            "total_amount": ocr_data.get("total_amount"),
            "currency": "HRK",
        }
        ocr_data["currency"] = "EUR"
        logger.info(f"  HRK->EUR converted (rate {rate})")

    if dry_run:
        result["status"] = "dry_run"
        result["ocr"] = {
            "vendor": vendor,
            "amount": ocr_data.get("total_amount"),
            "date": ocr_data.get("transaction_date"),
            "invoice_no": ocr_data.get("receipt_number") or ocr_data.get("invoice_number"),
            "currency": ocr_data.get("currency", "EUR"),
        }
        return result

    # Create vendor invoice via service
    svc = get_vendor_invoice_service()
    try:
        doc = await svc.create_from_ocr(ocr_data, scan_file_id=f"local:{fhash[:12]}", ctx=ctx)
        result["status"] = "success"
        result["vendor_invoice_id"] = doc.get("vendor_invoice_id")
        result["display_id"] = doc.get("display_id")
        result["vendor"] = vendor
        result["amount"] = ocr_data.get("total_amount")
    except Exception as e:
        err = str(e)
        if "DUPLICATE" in err.upper() or "409" in err:
            result["status"] = "skipped"
            result["reason"] = f"duplicate: {err}"
        else:
            result["status"] = "error"
            result["error"] = err

    return result


# ---------------------------------------------------------------------------
# Import: Outgoing (izlazni) → invoices_b2c / invoices_b2b
# ---------------------------------------------------------------------------
async def import_outgoing(file_info: dict, ctx, dedup_set: set, dry_run: bool) -> dict:
    """Import a single outgoing invoice directly into Firestore."""
    from tools.handlers.vision_handler import VisionHandler
    from services.erp.base_erp_service import get_firestore_db

    path = file_info["path"]
    result = {"file": file_info["filename"], "direction": "izlazni", "status": "pending"}

    with open(path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("utf-8")

    fhash = hashlib.sha256(raw).hexdigest()
    if fhash in dedup_set:
        result["status"] = "skipped"
        result["reason"] = "duplicate file (same content)"
        return result
    dedup_set.add(fhash)

    # OCR with outgoing invoice prompt
    handler = VisionHandler()
    try:
        ocr_data = await ocr_with_retry(handler, "extract_outgoing_invoice", b64, file_info["mime_type"])
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"OCR failed: {e}"
        return result

    # Validation
    buyer = ocr_data.get("buyer_name") or ""
    buyer_oib = ocr_data.get("buyer_oib") or ""
    if "lux tech" in buyer.lower() or buyer_oib == "47034854402":
        result["status"] = "error"
        result["error"] = "OCR extracted seller as buyer"
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["ocr"] = {
            "buyer": buyer,
            "amount": ocr_data.get("grand_total"),
            "date": ocr_data.get("invoice_date"),
            "invoice_no": ocr_data.get("invoice_number"),
            "type": ocr_data.get("invoice_type", "b2c"),
        }
        return result

    # Determine collection
    inv_type = ocr_data.get("invoice_type", "b2c")
    collection = f"invoices_{inv_type}"

    # Build Firestore document
    now_iso = datetime.now(timezone.utc).isoformat()
    invoice_number = ocr_data.get("invoice_number", "")

    # Dedup by invoice_number within collection
    db = get_firestore_db()
    if invoice_number:
        from google.cloud.firestore_v1.base_query import FieldFilter
        existing = (
            db.collection(collection)
            .where(filter=FieldFilter("invoice_number", "==", invoice_number))
            .where(filter=FieldFilter("company_id", "==", ctx.company_id))
            .limit(1)
        )
        async for _ in existing.stream():
            result["status"] = "skipped"
            result["reason"] = f"invoice {invoice_number} already exists in {collection}"
            return result

    doc_id = str(uuid4())

    # HRK→EUR conversion for pre-2023 invoices
    currency = ocr_data.get("currency", "EUR")
    grand_total = float(ocr_data.get("grand_total", 0))
    total_without_vat = float(ocr_data.get("total_without_vat", 0))
    total_vat = float(ocr_data.get("total_vat", 0))
    hrk_original = None
    if currency == "HRK":
        hrk_original = {
            "grand_total_hrk": grand_total,
            "total_without_vat_hrk": total_without_vat,
            "total_vat_hrk": total_vat,
        }
        rate = 7.53450  # Fixed EUR/HRK conversion rate
        grand_total = round(grand_total / rate, 2)
        total_without_vat = round(total_without_vat / rate, 2)
        total_vat = round(total_vat / rate, 2)
        currency = "EUR"

    doc_data = {
        "invoice_number": invoice_number,
        "date": ocr_data.get("invoice_date", ""),
        "due_date": ocr_data.get("due_date", ""),
        "delivery_date": ocr_data.get("delivery_date", ""),
        "seller_oib": "47034854402",
        "seller_name": "Lux Tech d.o.o.",
        "total_without_vat": total_without_vat,
        "total_vat": total_vat,
        "grand_total": grand_total,
        "currency": currency,
        "items": ocr_data.get("items", []),
        "payment_method": ocr_data.get("payment_method", ""),
        "voided": False,
        # Company scoping
        "company_id": ctx.company_id,
        # Import metadata
        "import_source": "bulk_import",
        "import_file_hash": fhash[:16],
        "import_timestamp": now_iso,
        "ocr_confidence": ocr_data.get("confidence_score", 0),
        "ocr_notes": ocr_data.get("extraction_notes", ""),
        # ERP tracking fields (pre-populated as unpaid)
        "erp_amount_paid": 0,
        "erp_amount_due": grand_total,
        "erp_payment_status": "unpaid",
    }

    if hrk_original:
        doc_data["hrk_original"] = hrk_original

    # B2B-specific fields
    if inv_type == "b2b":
        doc_data["buyer_oib"] = ocr_data.get("buyer_oib", "")
        doc_data["buyer_name"] = ocr_data.get("buyer_name", "")
        doc_data["buyer_address"] = ocr_data.get("buyer_address", "")
        doc_data["payment_reference"] = ocr_data.get("payment_reference", "")
    # B2C-specific fields
    elif inv_type == "b2c":
        doc_data["customer_name"] = ocr_data.get("buyer_name", "")
        doc_data["customer_id"] = ""  # No customer_id from OCR
        doc_data["jir"] = ocr_data.get("jir", "")
        doc_data["zki"] = ocr_data.get("zki", "")
        doc_data["business_premise"] = ""
        doc_data["cash_register"] = ""
        doc_data["fiscalization_status"] = "imported"

    # Write to Firestore
    try:
        await db.collection(collection).document(doc_id).set(doc_data)
        result["status"] = "success"
        result["doc_id"] = doc_id
        result["collection"] = collection
        result["invoice_number"] = invoice_number
        result["buyer"] = buyer
        result["amount"] = grand_total
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
async def bulk_import(root: str, direction: Optional[str] = None,
                      year: Optional[int] = None, month: Optional[int] = None,
                      limit: Optional[int] = None, delay: int = DEFAULT_DELAY,
                      dry_run: bool = False, start_from: int = 0):
    """Run the full bulk import pipeline."""
    from services.erp.request_context import ERPRequestContext

    ctx = ERPRequestContext(
        user_id=DEFAULT_USER_ID,
        company_id=DEFAULT_COMPANY_ID,
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )

    # Discover files
    invoices = discover_invoices(root, direction, year, month)
    if not invoices:
        logger.error("No invoice files found. Check --root path and folder structure.")
        return

    # Apply start_from and limit
    if start_from > 0:
        invoices = invoices[start_from:]
        logger.info(f"Skipping first {start_from} files (--start-from)")
    if limit:
        invoices = invoices[:limit]

    total = len(invoices)
    ulazni_count = sum(1 for i in invoices if i["direction"] == "ulazni")
    izlazni_count = sum(1 for i in invoices if i["direction"] == "izlazni")

    logger.info("=" * 70)
    logger.info("BULK INVOICE IMPORT")
    logger.info("=" * 70)
    logger.info(f"Root:      {root}")
    logger.info(f"Files:     {total} ({ulazni_count} ulazni, {izlazni_count} izlazni)")
    logger.info(f"Delay:     {delay}s between OCR calls (~{60/delay:.1f} RPM)")
    logger.info(f"Dry run:   {dry_run}")
    est_min = (total * delay) // 60
    est_sec = (total * delay) % 60
    logger.info(f"Est. time: ~{est_min}m {est_sec}s")
    logger.info("=" * 70)

    dedup_set: set = set()
    results = []
    success = skipped = errors = 0

    for i, inv in enumerate(invoices, 1):
        tag = f"[{i}/{total}]"
        logger.info(f"{tag} {inv['direction']}/{inv['year']}/{inv['month']:02d}/{inv['filename']}")

        if inv["direction"] == "ulazni":
            res = await import_incoming(inv, ctx, dedup_set, dry_run)
        else:
            res = await import_outgoing(inv, ctx, dedup_set, dry_run)

        results.append(res)

        if res["status"] == "success":
            success += 1
            logger.info(f"{tag} -> OK: {res.get('display_id') or res.get('invoice_number', '')}")
        elif res["status"] == "skipped":
            skipped += 1
            logger.info(f"{tag} -> SKIP: {res.get('reason', '')}")
        elif res["status"] == "dry_run":
            logger.info(f"{tag} -> DRY RUN: {json.dumps(res.get('ocr', {}), ensure_ascii=False)}")
        else:
            errors += 1
            logger.error(f"{tag} -> ERROR: {res.get('error', 'unknown')}")

        # Rate limit (skip delay after last file)
        if i < total:
            await asyncio.sleep(delay)

    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total processed: {total}")
    logger.info(f"  Success:       {success}")
    logger.info(f"  Skipped:       {skipped}")
    logger.info(f"  Errors:        {errors}")

    if errors > 0:
        logger.info("")
        logger.info("Failed files:")
        for r in results:
            if r["status"] == "error":
                logger.info(f"  - {r['file']}: {r.get('error', '')}")

    # Write results to JSON for later review
    out_path = os.path.join(os.path.dirname(__file__), "bulk_import_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"\nDetailed results saved to: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Bulk import invoices from local folders into Firestore")
    parser.add_argument("--root", required=True,
                        help="Root folder (contains ulazni/ and izlazni/ subdirectories)")
    parser.add_argument("--direction", choices=["ulazni", "izlazni"],
                        help="Process only ulazni or izlazni (default: both)")
    parser.add_argument("--year", type=int, help="Process only specific year")
    parser.add_argument("--month", type=int, help="Process only specific month (1-12)")
    parser.add_argument("--limit", type=int, help="Max number of files to process")
    parser.add_argument("--start-from", type=int, default=0,
                        help="Skip first N files (for resuming)")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY,
                        help=f"Seconds between OCR calls (default: {DEFAULT_DELAY})")
    parser.add_argument("--dry-run", action="store_true",
                        help="OCR only, don't write to Firestore")
    args = parser.parse_args()

    asyncio.run(bulk_import(
        root=args.root,
        direction=args.direction,
        year=args.year,
        month=args.month,
        limit=args.limit,
        delay=args.delay,
        dry_run=args.dry_run,
        start_from=args.start_from,
    ))


if __name__ == "__main__":
    main()
