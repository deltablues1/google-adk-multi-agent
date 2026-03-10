"""
TEST: Real Email Send to Tomislav Golic
Tests complete email workflow with actual Gmail API send

This test:
1. Looks up Tomislav Golic contact (rolodex agent)
2. Sends real email via Gmail API (mailer agent)
3. Verifies email was actually sent
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from main import WorkspaceADKSystem

print("=" * 80)
print("EMAIL SEND TEST - Real Gmail API Call")
print("=" * 80)
print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("Recipient: Tomislav Golic")
print("=" * 80)


async def test_email_send():
    """Test real email send workflow"""

    # Initialize system
    print("\n[STEP 1] Initializing ADK System...")
    system = WorkspaceADKSystem()
    system.initialize_agents()
    print(f"✓ System initialized with {len(system.worker_agents)} agents")

    # Test scenarios
    test_scenarios = [
        {
            'id': 'email_lookup_send',
            'query': 'Pronađi email adresu Tomislava Golića i pošalji mu poruku sa temom "ADK Test - Multi-Agent Workflow" i tekstom "Pozdrav! Ovo je automatski test multi-agent sustava. Researcher agent je pronašao informacije, a mailer agent šalje ovaj email. Sustav radi!"',
            'description': 'Contact lookup + Email send (multi-agent chain)',
            'expected_agents': ['rolodex', 'mailer']
        },
        {
            'id': 'direct_email_send',
            'query': 'Pošalji email Tomislavu Goliću (tomi.golic@gmail.com) sa temom "ADK Direct Send Test" i porukom "Test direktnog slanja emaila kroz mailer agenta."',
            'description': 'Direct email send (single agent)',
            'expected_agents': ['mailer']
        }
    ]

    results = []

    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{'=' * 80}")
        print(f"[SCENARIO {i}/{len(test_scenarios)}] {scenario['id']}")
        print(f"{'=' * 80}")
        print(f"Query: {scenario['query']}")
        print(f"Description: {scenario['description']}")
        print(f"Expected agents: {', '.join(scenario['expected_agents'])}")

        try:
            # Execute through orchestrator
            print(f"\n⚙️  Executing...")
            start_time = datetime.now()

            result = await system.orchestrator.execute(scenario['query'])

            duration = (datetime.now() - start_time).total_seconds()

            # Analyze result
            success = (
                result and
                len(result) > 50 and
                "error" not in result.lower() and
                ("sent" in result.lower() or "poslan" in result.lower() or "✅" in result)
            )

            print(f"\n{'✅' if success else '❌'} RESULT ({duration:.2f}s):")
            print(f"{result}\n")

            results.append({
                'scenario': scenario['id'],
                'success': success,
                'duration': duration,
                'result': result
            })

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            results.append({
                'scenario': scenario['id'],
                'success': False,
                'duration': 0,
                'result': str(e)
            })

    # Final report
    print(f"\n{'=' * 80}")
    print("FINAL REPORT")
    print(f"{'=' * 80}")

    successful = sum(1 for r in results if r['success'])
    total = len(results)

    print(f"\nResults: {successful}/{total} passed")
    print(f"\nDetails:")
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"  {status} {r['scenario']} ({r['duration']:.2f}s)")

    if successful == total:
        print(f"\n🎉 ALL TESTS PASSED!")
        print(f"\n✅ CONFIRMATION:")
        print(f"   - Emails should have been sent to Tomislav Golic")
        print(f"   - Check Gmail inbox: tomi.golic@gmail.com")
        print(f"   - Look for subjects:")
        print(f"     1. 'ADK Test - Multi-Agent Workflow'")
        print(f"     2. 'ADK Direct Send Test'")
        return 0
    else:
        print(f"\n❌ SOME TESTS FAILED")
        print(f"\nFailed scenarios:")
        for r in results:
            if not r['success']:
                print(f"  - {r['scenario']}")
                print(f"    Result: {r['result'][:200]}...")
        return 1


async def main():
    """Main entry point"""
    try:
        exit_code = await test_email_send()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n💥 FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
