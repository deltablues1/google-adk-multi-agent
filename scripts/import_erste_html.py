"""
Erste Bank HTML Invoice Importer

Parses Erste Bank HTML invoices (FAKTURA-1101091655_*.htm) directly
without OCR — extracts structured data from HTML tables.

Usage:
    python scripts/import_erste_html.py --root "C:/path/to/racuni"
    python scripts/import_erste_html.py --root "C:/path/to/racuni" --dry-run
"""

import asyncio
import argparse
import os
import re
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

HRK_RATE = 7.53450  # Fixed EUR/HRK conversion rate (valid from 01.01.2023)
ERSTE_OIB = "23057039320"  # Erste&Steiermärkische Bank d.d.


def parse_erste_html(path: str) -> dict | None:
    """Parse Erste Bank HTML invoice and return structured data."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("beautifulsoup4 not installed. Run: pip install beautifulsoup4")

    try:
        # Try encodings
        content = None
        for enc in ['cp1250', 'iso-8859-2', 'utf-8']:
            try:
                content = Path(path).read_text(encoding=enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if not content:
            return None

        soup = BeautifulSoup(content, 'html.parser')
        text = soup.get_text(separator=' ')

        # Invoice number: e.g. "241822-AUT305-1-2022-PPR"
        inv_match = re.search(r'Račun br\.\s*[:.]?\s*([\w\-]+(?:PPR|AUT305)[\w\-]*)', text)
        invoice_number = inv_match.group(1).strip() if inv_match else ""

        # Date: "BJELOVAR, 01.05.2022. 13:54" or similar
        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\.\s+\d{2}:\d{2}', text)
        if not date_match:
            # Fallback: any date near top
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\.', text)
        invoice_date = ""
        if date_match:
            try:
                invoice_date = datetime.strptime(date_match.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Delivery date: "Datum isporuke: 30.04.2022."
        deliv_match = re.search(r'Datum isporuke:\s*(\d{2}\.\d{2}\.\d{4})', text)
        delivery_date = ""
        if deliv_match:
            try:
                delivery_date = datetime.strptime(deliv_match.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Period: "za razdoblje: 01.04.2022. - 30.04.2022."
        period_match = re.search(r'za razdoblje:\s*(\d{2}\.\d{2}\.\d{4})\.\s*-\s*(\d{2}\.\d{2}\.\d{4})', text)
        period = ""
        if period_match:
            period = f"{period_match.group(1)} - {period_match.group(2)}"

        # Currency detection: "UKUPNO KN" = HRK, "UKUPNO EUR" = EUR
        if 'UKUPNO KN' in text or 'UKUPNO HRK' in text:
            currency = 'HRK'
        else:
            currency = 'EUR'

        # Amounts from last summary row: "UKUPNO KN: X Y Z"
        # Table pattern: Osnovica | Iznos PDV-a | Ukupno
        total_gross = 0.0
        vat_amount = 0.0
        subtotal_net = 0.0

        # Find "UKUPNO KN:" or "UKUPNO EUR:" row — has 3 bold amounts
        ukupno_match = re.search(
            r'UKUPNO\s+(?:KN|EUR|HRK):\s+([\d\s,.]+)\s+([\d\s,.]+)\s+([\d\s,.]+)',
            text
        )
        if ukupno_match:
            def parse_hr_num(s):
                # Croatian number format: 1.234,56 or 1 234,56
                s = s.strip().replace(' ', '').replace('.', '').replace(',', '.')
                try:
                    return float(s)
                except ValueError:
                    return 0.0

            subtotal_net = parse_hr_num(ukupno_match.group(1))
            vat_amount = parse_hr_num(ukupno_match.group(2))
            total_gross = parse_hr_num(ukupno_match.group(3))
        else:
            # Fallback: try to find Ukupno from table cells
            cells = [td.get_text(strip=True) for td in soup.find_all('td')]
            # Look for the last numeric cell as total
            amounts = []
            for cell in cells:
                clean = cell.replace('\xa0', '').replace(' ', '').replace('.', '').replace(',', '.')
                try:
                    val = float(clean)
                    if val > 0:
                        amounts.append(val)
                except ValueError:
                    pass
            if amounts:
                total_gross = amounts[-1]

        if total_gross <= 0:
            logger.warning(f"  Could not parse amount from {Path(path).name}")
            return None

        # HRK -> EUR conversion
        hrk_original = None
        if currency == 'HRK':
            hrk_original = {
                'total_gross': total_gross,
                'vat_amount': vat_amount,
                'subtotal_net': subtotal_net,
                'currency': 'HRK',
                'conversion_rate': HRK_RATE,
            }
            total_gross = round(total_gross / HRK_RATE, 2)
            vat_amount = round(vat_amount / HRK_RATE, 2)
            subtotal_net = round(subtotal_net / HRK_RATE, 2)
            currency = 'EUR'

        # Line items from table rows
        items = []
        rows = soup.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 6:
                try:
                    desc = cells[1].get_text(strip=True)
                    qty_text = cells[2].get_text(strip=True).replace('\xa0', '').replace('.', '').replace(',', '.')
                    price_text = cells[3].get_text(strip=True).replace('\xa0', '').replace('.', '').replace(',', '.')
                    amount_text = cells[4].get_text(strip=True).replace('\xa0', '').replace('.', '').replace(',', '.')
                    qty = float(qty_text) if qty_text else None
                    price = float(price_text) if price_text else None
                    amount = float(amount_text) if amount_text else None
                    if desc and amount and amount > 0 and not desc.startswith('Redni'):
                        raw_amount = amount
                        if hrk_original:
                            amount = round(amount / HRK_RATE, 2)
                            price = round(price / HRK_RATE, 2) if price else None
                        items.append({
                            'description': desc,
                            'quantity': qty,
                            'unit_price': price,
                            'amount': amount,
                        })
                except (ValueError, AttributeError):
                    continue

        return {
            'vendor_name': 'Erste&Steiermärkische Bank d.d.',
            'vendor_oib': ERSTE_OIB,
            'invoice_number': invoice_number,
            'issue_date': invoice_date,
            'delivery_date': delivery_date,
            'period': period,
            'total_gross': total_gross,
            'vat_amount': vat_amount,
            'subtotal_net': subtotal_net,
            'currency': currency,
            'category': 'services',
            'items': items,
            'hrk_original': hrk_original,
            'source_file': Path(path).name,
        }

    except Exception as e:
        logger.error(f"Parse error {Path(path).name}: {e}")
        return None


async def import_erste_invoices(root: str, dry_run: bool = False):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    from services.erp.request_context import ERPRequestContext

    ctx = ERPRequestContext(
        user_id="tomislav.luxtech@gmail.com",
        company_id="lux-tech",
        role="owner",
        grants=["*"],
        denies=[],
        request_id=str(uuid4()),
    )

    # Find all .htm files
    root_path = Path(root)
    htm_files = sorted(root_path.rglob("*.htm")) + sorted(root_path.rglob("*.html"))
    # Only Erste Bank pattern
    erste_files = [f for f in htm_files if 'FAKTURA-1101091655' in f.name or 'AUT305' in f.name]

    logger.info(f"Found {len(erste_files)} Erste Bank HTML invoices")

    svc = get_vendor_invoice_service()
    success = skipped = errors = 0
    results = []

    for i, fpath in enumerate(erste_files, 1):
        logger.info(f"[{i}/{len(erste_files)}] {fpath.name}")

        data = parse_erste_html(str(fpath))
        if not data:
            logger.error(f"  -> ERROR: could not parse")
            errors += 1
            results.append({'file': fpath.name, 'status': 'error', 'error': 'parse failed'})
            continue

        logger.info(f"  Vendor: {data['vendor_name']}, Amount: {data['total_gross']} {data['currency']}, Date: {data['issue_date']}, Inv#: {data['invoice_number']}")

        if dry_run:
            logger.info(f"  -> DRY RUN")
            results.append({'file': fpath.name, 'status': 'dry_run', 'data': data})
            continue

        # Build ocr_data compatible dict for create_from_ocr
        ocr_data = {
            'merchant_name': data['vendor_name'],
            'tax_id': data['vendor_oib'],
            'invoice_number': data['invoice_number'],
            'transaction_date': data['issue_date'],
            'total_amount': data['total_gross'],
            'tax_amount': data['vat_amount'],
            'vat_amount': data['vat_amount'],
            'currency': data['currency'],
            'expense_category': 'Ured',
            'items': data['items'],
            'confidence_score': 0.99,
            'extraction_notes': f"Direktno parsirano iz HTML-a. Perioda: {data.get('period', '')}",
        }
        if data.get('hrk_original'):
            ocr_data['_hrk_original'] = data['hrk_original']

        try:
            doc = await svc.create_from_ocr(ocr_data, scan_file_id=f"local:erste:{fpath.stem}", ctx=ctx)
            logger.info(f"  -> OK: {doc.get('display_id')}")
            success += 1
            results.append({'file': fpath.name, 'status': 'success', 'display_id': doc.get('display_id')})
        except Exception as e:
            err = str(e)
            if 'već postoji' in err or 'DUPLICATE' in err.upper() or '409' in err:
                logger.info(f"  -> SKIP: duplicate")
                skipped += 1
                results.append({'file': fpath.name, 'status': 'skipped', 'reason': err})
            else:
                logger.error(f"  -> ERROR: {err}")
                errors += 1
                results.append({'file': fpath.name, 'status': 'error', 'error': err})

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"SUMMARY: {len(erste_files)} files")
    logger.info(f"  Success: {success}")
    logger.info(f"  Skipped: {skipped}")
    logger.info(f"  Errors:  {errors}")

    out = os.path.join(os.path.dirname(__file__), "erste_import_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Results: {out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(import_erste_invoices(args.root, args.dry_run))


if __name__ == "__main__":
    main()
