"""Quick test for OIB validation after bug fix"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from main import WorkspaceADKSystem, sanitize_emojis


async def test_oib():
    print("\n" + "="*80)
    print("QUICK OIB VALIDATION TEST (After Bug Fix)")
    print("="*80)

    # Initialize system
    print("\nInitializing system...")
    system = WorkspaceADKSystem()
    system.initialize_agents()

    print(f"\n[OK] System initialized")
    print(f"Session: {system.session_id}\n")

    # Test 1: Valid OIB
    print("="*80)
    print("TEST 1: Valid OIB (47034854402)")
    print("="*80)
    try:
        response = await system.orchestrator_helper.run("Validiraj OIB 47034854402")
        print(sanitize_emojis(f"\n[OK] Result:\n{response}"))
    except Exception as e:
        print(f"\n[ERROR] {e}")

    print("\n" + "="*80)

    # Test 2: Invalid OIB
    print("TEST 2: Invalid OIB (12345678901)")
    print("="*80)
    try:
        response = await system.orchestrator_helper.run("Validiraj OIB 12345678901")
        print(sanitize_emojis(f"\n[OK] Result:\n{response}"))
    except Exception as e:
        print(f"\n[ERROR] {e}")

    print("\n" + "="*80)
    print("Tests complete!")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_oib())
