"""
Test Ledger Persistence

Tests the complete fiscalization ledger functionality:
- Idempotency checking
- Saving successful fiscalizations
- Retry queue management
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


async def test_ledger_in_memory():
    """Test ledger with in-memory storage"""
    from tools.adk_tools.fiskalizacija_adk_tools import (
        check_invoice_ledger,
        save_invoice_ledger,
        add_to_retry_queue,
        get_pending_retries,
        get_retry_queue_stats
    )

    print("=" * 80)
    print("TEST: Fiscalization Ledger (In-Memory)")
    print("=" * 80)

    # Test data
    invoice_number = "001/DEMO/1"
    supplier_oib = "47034854402"
    jir = "94450703-8e84-4c4f-94f6-4586a025ed7b"
    zki = "abc123def456789"
    signed_xml = "<xml>test signed XML</xml>"
    fina_response = "<response>success</response>"
    total_amount = "2100.00"

    # Test 1: Check non-existent invoice (should return exists=False)
    print("\n1. Testing idempotency check (should not exist)...")
    check_result = await check_invoice_ledger(
        invoice_number=invoice_number,
        supplier_oib=supplier_oib,
        use_firestore=False  # In-memory for testing
    )

    if not check_result.get("exists"):
        print("[OK] Invoice not found in ledger (as expected)")
        print(f"     Result: {check_result}")
    else:
        print(f"[FAIL] Invoice unexpectedly found: {check_result}")
        return

    # Test 2: Save successful fiscalization
    print("\n2. Saving successful fiscalization to ledger...")
    save_result = await save_invoice_ledger(
        invoice_number=invoice_number,
        supplier_oib=supplier_oib,
        jir=jir,
        zki=zki,
        signed_xml=signed_xml,
        fina_response=fina_response,
        total_amount=total_amount,
        use_firestore=False
    )

    if save_result.get("success"):
        print("[OK] Fiscalization saved to ledger")
        print(f"     Document ID: {save_result.get('document_id')}")
    else:
        print(f"[FAIL] Save failed: {save_result.get('error')}")
        return

    # Test 3: Check again (should now exist - idempotency)
    print("\n3. Testing idempotency check (should exist now)...")
    check_result2 = await check_invoice_ledger(
        invoice_number=invoice_number,
        supplier_oib=supplier_oib,
        use_firestore=False
    )

    if check_result2.get("exists"):
        print("[OK] Invoice found in ledger (idempotency working)")
        print(f"     JIR: {check_result2.get('jir')}")
        print(f"     ZKI: {check_result2.get('zki')}")
        print(f"     Status: {check_result2.get('status')}")
        print(f"     Timestamp: {check_result2.get('timestamp')}")
    else:
        print("[FAIL] Invoice not found after saving")
        return

    # Test 4: Retry queue - Add failed fiscalization
    print("\n4. Testing retry queue (failed fiscalization)...")
    failed_invoice = "002/DEMO/1"
    retry_result = await add_to_retry_queue(
        invoice_number=failed_invoice,
        supplier_oib=supplier_oib,
        signed_xml=signed_xml,
        zki=zki,
        error_message="Connection timeout to FINA",
        use_firestore=False
    )

    if retry_result.get("success"):
        print("[OK] Added to retry queue")
        print(f"     Queue position: {retry_result.get('queue_position')}")
        print(f"     Next retry: {retry_result.get('next_retry')}")
        print(f"     Deadline (48h): {retry_result.get('deadline')}")
        print(f"     Attempt count: {retry_result.get('attempt_count')}")
    else:
        print(f"[FAIL] Retry queue add failed: {retry_result.get('error')}")
        return

    # Test 5: Get retry queue stats
    print("\n5. Testing retry queue statistics...")
    stats_result = await get_retry_queue_stats(use_firestore=False)

    if stats_result.get("success"):
        stats = stats_result
        print("[OK] Retry queue stats retrieved")
        print(f"     Total: {stats.get('total')}")
        print(f"     Pending: {stats.get('pending')}")
        print(f"     Expired: {stats.get('expired')}")
    else:
        print(f"[FAIL] Stats retrieval failed: {stats_result.get('error')}")
        return

    # Test 6: Get pending retries (should return the failed invoice)
    print("\n6. Testing get pending retries...")
    pending_result = await get_pending_retries(use_firestore=False)

    if pending_result.get("success"):
        pending = pending_result.get("pending_retries", [])
        print(f"[OK] Retrieved {len(pending)} pending retries")
        for retry in pending:
            print(f"     - Invoice: {retry.get('invoice_number')}")
            print(f"       Attempts: {retry.get('attempt_count')}")
            print(f"       Next retry: {retry.get('next_retry')}")
    else:
        print(f"[FAIL] Pending retries retrieval failed")
        return

    print("\n" + "=" * 80)
    print("[SUCCESS] All Ledger Tests Passed!")
    print("=" * 80)

    print("\nLedger Features Verified:")
    print("  [x] Idempotency check (prevents duplicate fiscalization)")
    print("  [x] Save successful fiscalization to ledger")
    print("  [x] Ledger persistence (invoice found after save)")
    print("  [x] Retry queue for failed fiscalizations")
    print("  [x] Queue statistics")
    print("  [x] Pending retries retrieval")


if __name__ == "__main__":
    print("Starting ledger tests...\n")
    asyncio.run(test_ledger_in_memory())
