"""
Seed Data Import Script
========================
Imports company info, customers, and products into Firestore
from JSON and CSV files.

Files:
  data/seed/company.json      Company/obrt configuration
  data/seed/customers.csv     Customer/vendor list
  data/seed/products.csv      Product/service catalog

Usage:
    python scripts/seed_data.py                     # Import all
    python scripts/seed_data.py --only company      # Only company
    python scripts/seed_data.py --only customers     # Only customers
    python scripts/seed_data.py --only products      # Only products
    python scripts/seed_data.py --dry-run            # Preview without writing
    python scripts/seed_data.py --clear-first        # Delete existing data before import
"""

import os
import sys
import csv
import json
import asyncio
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from google.cloud.firestore_v1.async_client import AsyncClient

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent.parent / "data" / "seed"
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', 'fabled-sector-476018-n3')


async def import_company(db, dry_run=False):
    """Import company configuration from company.json."""
    company_file = SEED_DIR / "company.json"
    if not company_file.exists():
        logger.warning(f"  [!] File not found: {company_file}")
        return 0

    with open(company_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Remove comment field
    data.pop('_comment', None)

    # Validate OIB
    oib = data.get('oib', '')
    if oib == '00000000000' or len(oib) != 11:
        logger.warning("  [!] OIB is placeholder (00000000000) - update data/seed/company.json with real data")

    # Add metadata
    data['_type'] = 'company_config'
    data['created_at'] = datetime.now(timezone.utc)
    data['updated_at'] = datetime.now(timezone.utc)

    if not dry_run:
        # Store as company_config document in a dedicated collection
        await db.collection("company_config").document("active").set(data)

        # Also update company_config.py-compatible format for agents
        config_summary = {
            "name": data.get("name"),
            "oib": data.get("oib"),
            "address": data.get("address"),
            "city": data.get("city"),
            "postal_code": data.get("postal_code"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "iban": data.get("iban", ""),
            "business_premises": data.get("business_premises", []),
            "cash_registers": data.get("cash_registers", []),
            "fiscal_settings": data.get("fiscal_settings", {}),
            "environment": data.get("environment", "sandbox"),
            "updated_at": datetime.now(timezone.utc),
        }
        await db.collection("company_config").document("summary").set(config_summary)

    logger.info(f"  Firma: {data.get('name', 'N/A')}")
    logger.info(f"  OIB:   {data.get('oib', 'N/A')}")
    logger.info(f"  Grad:  {data.get('city', 'N/A')}")
    logger.info(f"  Poslovni prostori: {len(data.get('business_premises', []))}")
    logger.info(f"  Blagajne: {len(data.get('cash_registers', []))}")
    logger.info(f"  NKD djelatnosti: {len(data.get('registered_nkd', []))}")
    return 1


async def import_customers(db, dry_run=False):
    """Import customers from customers.csv."""
    csv_file = SEED_DIR / "customers.csv"
    if not csv_file.exists():
        logger.warning(f"  [!] File not found: {csv_file}")
        return 0

    count = 0
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean up values
            doc = {}
            for key, value in row.items():
                key = key.strip()
                if value is None:
                    value = ""
                else:
                    value = value.strip()

                # Type conversions
                if key == 'payment_terms_days' and value:
                    doc[key] = int(value)
                elif key == 'active':
                    doc[key] = value.lower() in ('true', '1', 'yes', 'da')
                else:
                    doc[key] = value

            # Add metadata
            doc['active'] = True
            doc['vies_validated'] = False
            doc['created_at'] = datetime.now(timezone.utc)
            doc['updated_at'] = datetime.now(timezone.utc)

            # Generate doc ID from OIB or name
            doc_id = doc.get('oib') or doc.get('name', '').replace(' ', '_').lower()[:30]
            if not doc_id:
                doc_id = f"customer_{count}"

            if not dry_run:
                await db.collection("customers").document(doc_id).set(doc, merge=True)

            category = doc.get('category', 'N/A')
            ctype = doc.get('type', 'N/A')
            logger.info(f"  [{category}/{ctype}] {doc.get('name', 'N/A')} (OIB: {doc.get('oib', '-')})")
            count += 1

    return count


async def import_products(db, dry_run=False):
    """Import products from products.csv."""
    csv_file = SEED_DIR / "products.csv"
    if not csv_file.exists():
        logger.warning(f"  [!] File not found: {csv_file}")
        return 0

    count = 0
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = {}
            for key, value in row.items():
                key = key.strip()
                if value is None:
                    value = ""
                else:
                    value = value.strip()

                # Type conversions
                if key == 'price' and value:
                    doc[key] = float(value)
                elif key == 'stock_quantity' and value:
                    doc[key] = int(value)
                elif key == 'active':
                    doc[key] = value.lower() in ('true', '1', 'yes', 'da')
                elif key == 'vat_rate' and value:
                    doc[key] = value
                else:
                    doc[key] = value

            # Add metadata
            doc['currency'] = doc.get('currency', 'EUR')
            doc['created_at'] = datetime.now(timezone.utc)
            doc['updated_at'] = datetime.now(timezone.utc)

            # Use SKU as document ID
            doc_id = doc.get('sku', f'product_{count}')

            if not dry_run:
                await db.collection("products").document(doc_id).set(doc, merge=True)

            logger.info(f"  [{doc.get('sku', '?')}] {doc.get('name', 'N/A')} - {doc.get('price', 0)} {doc.get('currency', 'EUR')}/{doc.get('unit', '?')}")
            count += 1

    return count


async def clear_collection(db, collection_name: str):
    """Delete all non-schema documents from a collection."""
    deleted = 0
    async for doc in db.collection(collection_name).stream():
        if not doc.id.startswith('_'):
            await doc.reference.delete()
            deleted += 1
    return deleted


async def main():
    parser = argparse.ArgumentParser(description="Import seed data into Firestore")
    parser.add_argument("--only", choices=["company", "customers", "products"],
                       help="Import only specific data type")
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without writing to Firestore")
    parser.add_argument("--clear-first", action="store_true",
                       help="Delete existing data before import")
    args = parser.parse_args()

    print("=" * 60)
    print("  Firestore Seed Data Import")
    print("=" * 60)

    if args.dry_run:
        print("  MODE: DRY RUN (no writes)")
    print(f"  Project: {PROJECT_ID}")
    print(f"  Seed directory: {SEED_DIR}")
    print()

    db = AsyncClient(project=PROJECT_ID)

    # Determine what to import
    import_all = args.only is None
    do_company = import_all or args.only == "company"
    do_customers = import_all or args.only == "customers"
    do_products = import_all or args.only == "products"

    # Clear existing data if requested
    if args.clear_first and not args.dry_run:
        print("[Brisanje postojecih podataka...]")
        if do_company:
            n = await clear_collection(db, "company_config")
            print(f"  company_config: {n} obrisano")
        if do_customers:
            n = await clear_collection(db, "customers")
            print(f"  customers: {n} obrisano")
        if do_products:
            n = await clear_collection(db, "products")
            print(f"  products: {n} obrisano")
        print()

    total = 0

    # Import company
    if do_company:
        print("[1] Firma (data/seed/company.json)")
        print("-" * 40)
        n = await import_company(db, args.dry_run)
        total += n
        print()

    # Import customers
    if do_customers:
        print("[2] Klijenti/dobavljaci (data/seed/customers.csv)")
        print("-" * 40)
        n = await import_customers(db, args.dry_run)
        total += n
        print()

    # Import products
    if do_products:
        print("[3] Proizvodi/usluge (data/seed/products.csv)")
        print("-" * 40)
        n = await import_products(db, args.dry_run)
        total += n
        print()

    # Summary
    print("=" * 60)
    print(f"  Uvezeno: {total} zapisa")
    if args.dry_run:
        print("  (dry-run - nista nije zapisano)")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
