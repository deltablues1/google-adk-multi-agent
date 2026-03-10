#!/usr/bin/env python3
"""
Quick Test Setup Checker

Pokreni ovaj script da provjeriš da li je sve spremno za testiranje:
    python check_test_setup.py
"""

import sys
import os
from pathlib import Path


def check_python_version():
    """Provjeri Python verziju"""
    print("🔍 Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro} (OK)")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} (Need 3.11+)")
        return False


def check_dependencies():
    """Provjeri da li su potrebni packages instalirani"""
    print("\n🔍 Checking dependencies...")
    required = {
        'pytest': 'pytest',
        'pytest-asyncio': 'pytest_asyncio',
        'dotenv': 'dotenv',
    }

    all_ok = True
    for name, import_name in required.items():
        try:
            __import__(import_name)
            print(f"   ✅ {name} (installed)")
        except ImportError:
            print(f"   ❌ {name} (MISSING - run: pip install {name})")
            all_ok = False

    return all_ok


def check_env_file():
    """Provjeri da li .env postoji"""
    print("\n🔍 Checking .env file...")
    env_path = Path('.env')
    if env_path.exists():
        print("   ✅ .env file exists")
        # Provjeri bitne varijable
        with open(env_path, 'r') as f:
            content = f.read()
            required_vars = ['ENVIRONMENT', 'LOG_LEVEL', 'GEMINI_MODEL_FLASH']
            for var in required_vars:
                if var in content:
                    print(f"      ✅ {var} is set")
                else:
                    print(f"      🟡 {var} is missing (optional for tests)")
        return True
    else:
        print("   ❌ .env file NOT found")
        print("      Run: cp .env.example .env")
        return False


def check_agent_files():
    """Provjeri da li agent fajlovi postoje"""
    print("\n🔍 Checking agent files...")
    agents = ['mailer', 'librarian', 'scribe', 'analyst', 'secretary',
              'orchestrator', 'rolodex', 'tracker', 'researcher', 'scraper']

    all_ok = True
    for agent in agents:
        agent_py = Path(f'agents/{agent}/{agent}.py')
        instructions_md = Path(f'agents/{agent}/instructions.md')

        if agent_py.exists() and instructions_md.exists():
            print(f"   ✅ {agent} (agent.py + instructions.md)")
        elif agent_py.exists():
            print(f"   🟡 {agent} (agent.py OK, instructions.md MISSING)")
            all_ok = False
        else:
            print(f"   ❌ {agent} (MISSING)")
            all_ok = False

    return all_ok


def check_test_files():
    """Provjeri da li test fajlovi postoje"""
    print("\n🔍 Checking test files...")
    test_files = [
        'tests/unit/test_agents.py',
        'tests/integration/test_real_agents.py',
        'tests/integration/test_real_custom_tools.py',
        'tests/integration/test_mailer_with_gmail_mcp.py',
        'tests/unit/test_real_auth_managers.py',
        'tests/unit/test_real_session_service.py',
        'tests/e2e/test_real_user_workflows.py',
    ]

    all_ok = True
    for test_file in test_files:
        if Path(test_file).exists():
            print(f"   ✅ {test_file}")
        else:
            print(f"   ❌ {test_file} (MISSING)")
            all_ok = False

    return all_ok


def check_pytest_config():
    """Provjeri pytest konfiguraciju"""
    print("\n🔍 Checking pytest configuration...")
    pytest_ini = Path('pytest.ini')
    conftest = Path('tests/conftest.py')

    all_ok = True
    if pytest_ini.exists():
        print("   ✅ pytest.ini exists")
    else:
        print("   ❌ pytest.ini MISSING")
        all_ok = False

    if conftest.exists():
        print("   ✅ tests/conftest.py exists")
    else:
        print("   ❌ tests/conftest.py MISSING")
        all_ok = False

    return all_ok


def run_quick_test():
    """Pokreni brzi test"""
    print("\n🧪 Running quick test...")
    try:
        import pytest
        # Pokreni jedan jednostavan test
        result = pytest.main([
            'tests/unit/test_agents.py::TestAgentInitialization::test_mailer_init',
            '-v',
            '--tb=short',
            '--disable-warnings'
        ])

        if result == 0:
            print("   ✅ Quick test PASSED!")
            return True
        else:
            print("   ❌ Quick test FAILED")
            return False
    except Exception as e:
        print(f"   ❌ Could not run test: {e}")
        return False


def main():
    """Main check"""
    print("=" * 60)
    print("🧪 TEST SETUP CHECKER")
    print("=" * 60)

    checks = [
        ('Python Version', check_python_version),
        ('Dependencies', check_dependencies),
        ('Environment File', check_env_file),
        ('Agent Files', check_agent_files),
        ('Test Files', check_test_files),
        ('Pytest Config', check_pytest_config),
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"   ❌ Error checking {name}: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print("-" * 60)
    print(f"Score: {passed}/{total} checks passed")

    if passed == total:
        print("\n🎉 ALL CHECKS PASSED! Ready to run tests!")
        print("\nNext steps:")
        print("  1. Run all tests:  pytest")
        print("  2. Run with verbose: pytest -v")
        print("  3. Run with coverage: pytest --cov=. --cov-report=html")

        # Try quick test
        if input("\n🧪 Run quick test now? (y/n): ").lower() == 'y':
            run_quick_test()
    else:
        print(f"\n⚠️  {total - passed} checks failed. Please fix before running tests.")
        print("\n📚 See TESTING_SETUP.md for detailed instructions.")

    print("=" * 60)


if __name__ == "__main__":
    main()
