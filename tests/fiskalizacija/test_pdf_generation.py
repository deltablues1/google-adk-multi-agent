"""
Test PDF Invoice Generation

Tests the complete PDF generation flow with dummy invoice data.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


async def test_pdf_generation():
    """Test PDF generation with dummy data"""
    from tools.adk_tools.fiskalizacija_adk_tools import generate_invoice_pdf, generate_qr_code

    print("=" * 80)
    print("TEST: PDF Invoice Generation")
    print("=" * 80)

    # Dummy invoice data (matching test_fiskalizacija_full.py format)
    invoice_data = {
        "supplier": {
            "name": "LuxWood d.o.o.",
            "oib": "47034854402",
            "address": "Testna ulica 123",
            "city": "Zagreb",
            "postal_code": "10000",
            "phone": "+385 1 234 5678",
            "email": "info@luxwood.hr",
            "iban": "HR1234567890123456789"
        },
        "customer": {
            "name": "Marko Horvat",
            "oib": "12345678903",
            "address": "Kupačka 45",
            "city": "Zagreb",
            "postal_code": "10000"
        },
        "invoice_number": "001/DEMO/1",
        "issue_date": "2026-01-29",
        "issue_time": "18:45:00",
        "due_date": "2026-02-12",
        "payment_means_code": "10",  # Gotovina
        "payment_reference": "00123-456-789",
        "payment_reference_model": "HR00",
        "items": [
            {
                "description": "Stolica LUXURY, bukva, natur boja",
                "quantity": "2",
                "unit_code": "kom",
                "unit_price": "450.00",
                "vat_rate": "25",
                "line_total": "900.00"
            },
            {
                "description": "Stol PREMIUM, hrast, 180x90cm",
                "quantity": "1",
                "unit_code": "kom",
                "unit_price": "1200.00",
                "vat_rate": "25",
                "line_total": "1200.00"
            }
        ],
        "tax_breakdown": {
            "subtotals": [
                {
                    "vat_rate": "25",
                    "taxable_amount": "1680.00",
                    "tax_amount": "420.00"
                }
            ],
            "total_net": "1680.00",
            "total_gross": "2100.00"
        },
        "business_unit": "DEMO",
        "device_number": "1",
        "operator_oib": "47034854402"
    }

    # Test JIR (from successful fiscalization)
    jir = "94450703-8e84-4c4f-94f6-4586a025ed7b"

    # Test ZKI
    zki = "abc123def456789"

    print("\n1. Generating QR Code...")
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

    print(f"[OK] QR code generated: {len(qr_result.get('qr_code_base64', ''))} bytes (base64)")

    print("\n2. Generating PDF...")
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
    print(f"   - Size: {pdf_result.get('size_bytes'):,} bytes")
    print(f"   - Path: {pdf_result.get('pdf_path')}")
    print(f"   - Filename: {pdf_result.get('pdf_filename')}")

    print("\n" + "=" * 80)
    print("[SUCCESS] TEST PASSED - PDF Generated Successfully!")
    print("=" * 80)

    # Verification checklist
    print("\nVerification Checklist:")
    print("   [ ] Open PDF and verify layout")
    print("   [ ] Check supplier information is correct")
    print("   [ ] Check customer information is correct")
    print("   [ ] Verify invoice items are listed correctly")
    print("   [ ] Verify VAT breakdown is correct")
    print("   [ ] Verify JIR and ZKI are displayed")
    print("   [ ] Scan QR code with phone to verify")
    print("\nTip: Open the PDF file to visually inspect the invoice layout.")


if __name__ == "__main__":
    asyncio.run(test_pdf_generation())
