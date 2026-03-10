"""
Debug QR Code Generation
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def test_qr():
    from tools.adk_tools.fiskalizacija_adk_tools import generate_qr_code

    print("Testing QR code generation...")

    result = await generate_qr_code(
        jir="94450703-8e84-4c4f-94f6-4586a025ed7b",
        zki="abc123def456789",
        invoice_datetime="2026-01-29T18:45:00",
        total_amount="2100.00",
        oib="47034854402"
    )

    print("\n=== QR Code Generation Result ===")
    print(f"Success: {result.get('success')}")
    print(f"Error: {result.get('error')}")
    print(f"QR base64 length: {len(result.get('qr_base64', '')) if result.get('qr_base64') else 0}")
    print(f"Verification URL: {result.get('verification_url')}")

    if result.get('qr_base64'):
        print(f"\nQR base64 (first 100 chars): {result.get('qr_base64')[:100]}...")
    else:
        print(f"\nQR base64 is EMPTY or None!")
        print(f"Full result: {result}")


if __name__ == "__main__":
    asyncio.run(test_qr())
