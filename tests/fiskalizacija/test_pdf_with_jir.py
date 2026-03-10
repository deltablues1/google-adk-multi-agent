"""
Test PDF Generation with Real JIR

Generates PDF invoice with:
- Real JIR from successful fiscalization
- Real ZKI
- QR code for verification
- Complete invoice data

This test uses data from successful deterministic fiscalization.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tools.adk_tools.fiskalizacija_adk_tools import generate_invoice_pdf, generate_qr_code


async def test_pdf_with_jir():
    print("\n" + "="*80)
    print("TEST: PDF Generation with Real JIR")
    print("="*80)
    print("\nGenerating PDF invoice with real fiscalization data.\n")

    # Real data from successful deterministic test
    jir = "7a17ba67-3c3f-42e5-98ce-4586a02527b8"
    zki = "0B5C811B-E993A01E-824F15CF-63C3A295"

    # Invoice data
    invoice_data = {
        "supplier": {
            "name": "LUX TECH d.o.o.",
            "oib": "47034854402",
            "address": "Hrvatski Leskovac",
            "city": "Hrvatski Leskovac",
            "postal_code": "10000",
            "phone": "+385 1 234 5678",
            "email": "info@luxtech.hr",
            "iban": "HR1234567890123456789"
        },
        "customer": {
            "name": "Test Kupac d.o.o.",
            "oib": "12345678903",
            "address": "Test ulica 123",
            "city": "Zagreb",
            "postal_code": "10000"
        },
        "invoice_number": "001/DEMO/1",
        "issue_date": "2026-01-28",
        "issue_time": "11:30:00",
        "due_date": "2026-02-27",
        "payment_means_code": "30",  # Transfer
        "payment_reference": "00-123-456",
        "payment_reference_model": "HR00",
        "items": [
            {
                "description": "IT Consulting Services",
                "quantity": "10.0",
                "unit_code": "HUR",  # Hours
                "unit_price": "150.00",
                "vat_rate": "25",
                "line_total": "1500.00"
            }
        ],
        "tax_breakdown": {
            "subtotals": [
                {
                    "vat_rate": "25",
                    "taxable_amount": "1500.00",
                    "tax_amount": "375.00"
                }
            ],
            "total_net": "1500.00",
            "total_gross": "1875.00"
        },
        "business_unit": "DEMO",
        "device_number": "1",
        "operator_oib": "47034854402"
    }

    print("="*80)
    print("INVOICE DATA")
    print("="*80)
    print(f"Invoice Number: {invoice_data['invoice_number']}")
    print(f"Supplier: {invoice_data['supplier']['name']} (OIB: {invoice_data['supplier']['oib']})")
    print(f"Customer: {invoice_data['customer']['name']} (OIB: {invoice_data['customer']['oib']})")
    print(f"Total: {invoice_data['tax_breakdown']['total_gross']} EUR")
    print(f"Issue Date: {invoice_data['issue_date']} {invoice_data['issue_time']}")
    print(f"\nJIR: {jir}")
    print(f"ZKI: {zki}")
    print()

    # Step 1: Generate QR code
    print("="*80)
    print("STEP 1: Generate QR Code")
    print("="*80)

    qr_result = await generate_qr_code(
        jir=jir,
        zki=zki,
        invoice_datetime=f"{invoice_data['issue_date']}T{invoice_data['issue_time']}",
        total_amount=invoice_data['tax_breakdown']['total_gross'],
        oib=invoice_data['supplier']['oib']
    )

    if not qr_result.get("success"):
        print(f"[FAIL] QR generation failed: {qr_result.get('error')}")
        return

    print(f"[OK] QR code generated")
    print(f"  Size: {len(qr_result.get('qr_code_base64', ''))} bytes (base64)")
    print(f"  Verification URL: {qr_result.get('verification_url')}")
    print()

    # Step 2: Generate PDF
    print("="*80)
    print("STEP 2: Generate PDF Invoice")
    print("="*80)

    pdf_result = await generate_invoice_pdf(
        invoice_data=invoice_data,
        jir=jir,
        zki=zki,
        qr_code_base64=qr_result.get("qr_code_base64")
    )

    if not pdf_result.get("success"):
        print(f"[FAIL] PDF generation failed: {pdf_result.get('error')}")
        return

    print(f"[OK] PDF generated successfully!")
    print(f"  Size: {pdf_result.get('size_bytes'):,} bytes")
    print(f"  Path: {pdf_result.get('pdf_path')}")
    print(f"  Filename: {pdf_result.get('pdf_filename')}")
    print()

    # Verification checklist
    print("="*80)
    print("VERIFICATION CHECKLIST")
    print("="*80)
    print("\nPlease open the PDF and verify:")
    print("  [ ] Supplier information (LUX TECH d.o.o., OIB: 47034854402)")
    print("  [ ] Customer information (Test Kupac d.o.o., OIB: 12345678903)")
    print("  [ ] Invoice number: 001/DEMO/1")
    print("  [ ] Issue date: 2026-01-28")
    print("  [ ] Items: IT Consulting Services, 10 HUR, 150.00 EUR")
    print("  [ ] VAT breakdown: 1500.00 + 375.00 (25%) = 1875.00 EUR")
    print(f"  [ ] JIR displayed: {jir}")
    print(f"  [ ] ZKI displayed: {zki}")
    print("  [ ] QR code visible and scannable")
    print("  [ ] Croatian characters display correctly (č, ć, đ, š, ž)")
    print()

    print("="*80)
    print("[OK] TEST PASSED - PDF Generated!")
    print("="*80)
    print(f"\nPDF Location: {pdf_result.get('pdf_path')}")
    print("\nNext: Open the PDF to verify all data is correct.")
    print()


if __name__ == "__main__":
    asyncio.run(test_pdf_with_jir())
