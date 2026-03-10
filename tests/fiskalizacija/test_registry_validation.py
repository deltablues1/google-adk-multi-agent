"""
Registry Validation Test

Verifies that all 20 agents registered in agent_registry.py can be loaded
without errors. This is a critical pre-commit test to ensure the registry
is consistent with the codebase.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.agent_registry import (
    AGENT_REGISTRY,
    get_all_agent_names,
    get_worker_agent_names,
    create_agent_instance,
    validate_registry
)


def test_registry_structure():
    """Test 1: Verify registry structure is valid"""
    print("\n" + "="*80)
    print("TEST 1: Registry Structure Validation")
    print("="*80)
    print()

    all_agents = get_all_agent_names()
    worker_agents = get_worker_agent_names()

    print(f"Total agents registered: {len(all_agents)}")
    print(f"Worker agents: {len(worker_agents)}")
    print(f"Infrastructure agents: {len(all_agents) - len(worker_agents)}")
    print()

    expected_total = 20  # Actual count in agent_registry.py
    if len(all_agents) == expected_total:
        print(f"[OK] Agent count matches expected: {expected_total}")
        return True
    else:
        print(f"[FAIL] Agent count mismatch!")
        print(f"  Expected: {expected_total}")
        print(f"  Actual: {len(all_agents)}")
        return False


def test_registry_validation():
    """Test 2: Validate all modules and classes exist"""
    print("\n" + "="*80)
    print("TEST 2: Registry Validation (Modules & Classes)")
    print("="*80)
    print()

    print("Validating all agent entries...")
    is_valid = validate_registry()

    if is_valid:
        print("[OK] All agent modules and classes exist")
        return True
    else:
        print("[FAIL] Some agents have missing modules or classes")
        return False


def test_agent_loading():
    """Test 3: Try to load each agent instance"""
    print("\n" + "="*80)
    print("TEST 3: Agent Instance Loading")
    print("="*80)
    print()

    all_agents = get_all_agent_names()
    loaded = []
    failed = []

    for agent_name in all_agents:
        try:
            print(f"Loading {agent_name}...", end=" ")

            # Special handling for agents that need sub_agents parameter
            if agent_name in ["decision_validator"]:
                agent = create_agent_instance(agent_name, sub_agents=[])
            else:
                agent = create_agent_instance(agent_name)

            print(f"[OK]")
            loaded.append(agent_name)

        except Exception as e:
            print(f"[FAIL] {e}")
            failed.append((agent_name, str(e)))

    print()
    print("="*80)
    print(f"Results: {len(loaded)}/{len(all_agents)} agents loaded successfully")
    print()

    if failed:
        print("Failed agents:")
        for agent_name, error in failed:
            print(f"  - {agent_name}: {error}")
        print()
        return False
    else:
        print("[OK] All agents loaded successfully!")
        return True


def test_agent_types():
    """Test 4: Verify agent types (ADK vs Legacy)"""
    print("\n" + "="*80)
    print("TEST 4: Agent Type Verification")
    print("="*80)
    print()

    adk_agents = []
    legacy_agents = []

    for agent_name, config in AGENT_REGISTRY.items():
        if config.use_adk:
            adk_agents.append(agent_name)
        else:
            legacy_agents.append(agent_name)

    print(f"ADK agents: {len(adk_agents)}")
    for name in adk_agents:
        print(f"  - {name}")

    print()
    print(f"Legacy agents: {len(legacy_agents)}")
    for name in legacy_agents:
        print(f"  - {name}")

    print()

    # Check migration progress
    total = len(AGENT_REGISTRY)
    adk_percentage = (len(adk_agents) / total) * 100

    print(f"ADK Migration Progress: {len(adk_agents)}/{total} ({adk_percentage:.1f}%)")
    print()

    if len(legacy_agents) == 0:
        print("[OK] All agents migrated to ADK!")
        return True
    else:
        print(f"[INFO] {len(legacy_agents)} legacy agents remaining")
        return True  # Not a failure, just informational


def test_agent_models():
    """Test 5: Verify model assignments"""
    print("\n" + "="*80)
    print("TEST 5: Model Assignment Verification")
    print("="*80)
    print()

    model_distribution = {}

    for agent_name, config in AGENT_REGISTRY.items():
        model = config.model
        if model not in model_distribution:
            model_distribution[model] = []
        model_distribution[model].append(agent_name)

    for model, agents in sorted(model_distribution.items()):
        print(f"{model}: {len(agents)} agents")
        for agent in agents:
            print(f"  - {agent}")
        print()

    # Check for invalid models
    valid_models = [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash-exp",
        "gemini-3-pro-preview"
    ]

    invalid = []
    for model in model_distribution.keys():
        if model not in valid_models:
            invalid.append(model)

    if invalid:
        print(f"[WARNING] Found unknown models: {invalid}")
        return False
    else:
        print("[OK] All models are valid")
        return True


def main():
    """Run all registry validation tests"""
    print("\n" + "="*80)
    print(" "*25 + "REGISTRY VALIDATION")
    print("="*80)
    print()
    print("Validating agent_registry.py configuration")
    print("This ensures all agents can be loaded before committing")
    print()
    print("="*80)

    tests = [
        ("Registry Structure", test_registry_structure),
        ("Module & Class Validation", test_registry_validation),
        ("Agent Loading", test_agent_loading),
        ("Agent Types", test_agent_types),
        ("Model Assignments", test_agent_models),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("REGISTRY VALIDATION SUMMARY")
    print("="*80)
    print()

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, test_passed in results:
        status = "[OK] PASSED" if test_passed else "[FAIL] FAILED"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print()

    if passed == total:
        print("[OK] REGISTRY VALIDATION COMPLETE!")
        print()
        print("All agents:")
        print("  - Are properly registered")
        print("  - Have valid modules and classes")
        print("  - Can be loaded without errors")
        print("  - Use valid Gemini models")
        print()
        print("Registry is ready for production use!")
    else:
        print("[FAIL] REGISTRY VALIDATION FAILED!")
        print()
        print("Fix the following issues before committing:")
        for test_name, test_passed in results:
            if not test_passed:
                print(f"  - {test_name}")
        print()
        print("DO NOT COMMIT until all tests pass!")

    print()
    print("="*80)

    return passed == total


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
