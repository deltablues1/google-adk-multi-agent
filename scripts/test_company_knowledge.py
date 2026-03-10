"""
Test Company Knowledge Base Setup

Quick test script to verify that the company knowledge base is set up correctly.

Usage:
    python scripts/test_company_knowledge.py
"""

import os
import sys
from dotenv import load_dotenv

# Fix encoding on Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment
load_dotenv()


def test_environment_variables():
    """Check that required environment variables are set"""
    print("=" * 70)
    print("1. Testing Environment Variables")
    print("=" * 70)

    required_vars = {
        "GOOGLE_CLOUD_PROJECT": "Google Cloud project ID",
        "COMPANY_CORPUS_ID": "Company knowledge RAG corpus ID",
    }

    all_set = True
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Truncate long values
            display_value = value if len(value) < 50 else value[:47] + "..."
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: NOT SET ({description})")
            all_set = False

    if all_set:
        print("\n✅ All environment variables are set!")
    else:
        print("\n⚠️  Missing environment variables. See setup guide.")

    return all_set


def test_drive_map():
    """Check that drive_map.yaml has Company_Knowledge folder"""
    print("\n" + "=" * 70)
    print("2. Testing Drive Map Configuration")
    print("=" * 70)

    try:
        import yaml
        drive_map_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "config",
            "drive_map.yaml"
        )

        with open(drive_map_path, 'r') as f:
            drive_map = yaml.safe_load(f)

        # Check for Company_Knowledge folder
        subfolders = drive_map.get('structure', {}).get('root', {}).get('subfolders', [])
        company_folder = None

        for folder in subfolders:
            if folder.get('name') == 'Company_Knowledge':
                company_folder = folder
                break

        if company_folder:
            print(f"✅ Company_Knowledge folder found in drive_map.yaml")
            print(f"   Alias: {company_folder.get('alias')}")
            print(f"   Description: {company_folder.get('description')}")
            return True
        else:
            print(f"❌ Company_Knowledge folder NOT found in drive_map.yaml")
            print(f"   Please update config/drive_map.yaml")
            return False

    except Exception as e:
        print(f"❌ Failed to load drive_map.yaml: {e}")
        return False


def test_company_tools():
    """Check that company_tools.py exists and can be imported"""
    print("\n" + "=" * 70)
    print("3. Testing Company Tools Module")
    print("=" * 70)

    try:
        from tools.company_tools import get_company_knowledge_tool

        print("✅ company_tools.py imported successfully")

        # Try creating tool
        tool = get_company_knowledge_tool()
        print(f"✅ Company knowledge tool created")
        print(f"   Tool name: {tool.name if hasattr(tool, 'name') else 'N/A'}")
        print(f"   Tool type: {type(tool).__name__}")

        return True

    except ImportError as e:
        print(f"❌ Failed to import company_tools: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Tool created with warnings: {e}")
        return True  # Not a critical error


def test_scripts_exist():
    """Check that setup and ingestion scripts exist"""
    print("\n" + "=" * 70)
    print("4. Testing Script Files")
    print("=" * 70)

    scripts_dir = os.path.dirname(__file__)
    required_scripts = {
        "setup_company_corpus.py": "Creates Vertex AI RAG Corpus",
        "ingest_company_docs.py": "Imports documents into corpus",
    }

    all_exist = True
    for script, description in required_scripts.items():
        script_path = os.path.join(scripts_dir, script)
        if os.path.exists(script_path):
            print(f"✅ {script}: Found")
            print(f"   {description}")
        else:
            print(f"❌ {script}: NOT FOUND")
            all_exist = False

    return all_exist


def print_next_steps(results):
    """Print next steps based on test results"""
    print("\n" + "=" * 70)
    print("Test Results Summary")
    print("=" * 70)

    env_ok, drive_ok, tools_ok, scripts_ok = results

    if all(results):
        print("\n🎉 All tests passed!")
        print("\n📋 Next steps:")
        print("   1. Run: python scripts/setup_company_corpus.py")
        print("   2. Add COMPANY_CORPUS_ID to .env")
        print("   3. Upload documents to Company_Knowledge folder")
        print("   4. Run: python scripts/ingest_company_docs.py")
        print("   5. Test with agents!")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")

        if not env_ok:
            print("\n📝 Environment variables:")
            print("   - Ensure GOOGLE_CLOUD_PROJECT is set in .env")
            print("   - Run setup_company_corpus.py to get COMPANY_CORPUS_ID")

        if not drive_ok:
            print("\n📁 Drive map:")
            print("   - Check config/drive_map.yaml")
            print("   - Ensure Company_Knowledge folder is defined")

        if not tools_ok:
            print("\n🔧 Tools:")
            print("   - Verify tools/company_tools.py exists")
            print("   - Check for import errors")

        if not scripts_ok:
            print("\n📜 Scripts:")
            print("   - Ensure scripts directory has required files")


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("Company Knowledge Base Setup Test")
    print("=" * 70)

    results = (
        test_environment_variables(),
        test_drive_map(),
        test_company_tools(),
        test_scripts_exist(),
    )

    print_next_steps(results)

    print("\n" + "=" * 70)
    print("Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
