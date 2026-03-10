"""
Helper script to integrate rate limiting into API implementation files
"""

import re
from pathlib import Path

# Define API files to process
API_FILES = {
    'drive_api.py': 'drive',
    'gmail_api.py': 'gmail',
    'docs_api.py': 'docs',
    'calendar_api.py': 'calendar',
    'contacts_api.py': 'contacts',
    'tasks_api.py': 'tasks'
}

BASE_PATH = Path(__file__).parent / 'tools' / 'api_implementations'


def add_rate_limit_import(content: str) -> str:
    """Add rate_limiter import if not present"""
    if 'from tools.resilience.rate_limiter import with_rate_limit' in content:
        print("  ✓ Import already present")
        return content

    # Find circuit_breaker import line
    pattern = r'(from tools\.resilience\.circuit_breaker import with_circuit_breaker)'
    replacement = r'\1\nfrom tools.resilience.rate_limiter import with_rate_limit'

    new_content = re.sub(pattern, replacement, content)

    if new_content != content:
        print("  ✓ Added import")
        return new_content
    else:
        print("  ⚠ Could not find circuit_breaker import")
        return content


def add_rate_limit_decorator(content: str, service_name: str) -> tuple[str, int]:
    """Add @with_rate_limit decorator to all async functions"""
    # Pattern: Find functions with @with_circuit_breaker but no @with_rate_limit
    pattern = rf'(@with_circuit_breaker\("{service_name}"\)\s*\n)(@with_retry\(RetryConfig)'

    # Count matches
    matches = re.findall(pattern, content)
    count = len(matches)

    # Add rate limit decorator
    replacement = rf'\1@with_rate_limit("{service_name}", user_id_param="credentials")\n\2'
    new_content = re.sub(pattern, replacement, content)

    return new_content, count


def process_api_file(filename: str, service_name: str):
    """Process a single API file"""
    filepath = BASE_PATH / filename

    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        return

    print(f"\n📄 Processing {filename} (service: {service_name})")

    # Read file
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add import
    content = add_rate_limit_import(content)

    # Add decorators
    content, count = add_rate_limit_decorator(content, service_name)
    print(f"  ✓ Added @with_rate_limit to {count} functions")

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  ✅ {filename} updated successfully")


def main():
    """Main function"""
    print("=" * 70)
    print("🚀 INTEGRATING RATE LIMITING INTO API IMPLEMENTATIONS")
    print("=" * 70)

    total_functions = 0

    for filename, service_name in API_FILES.items():
        try:
            filepath = BASE_PATH / filename
            if filepath.exists():
                process_api_file(filename, service_name)
                # Count functions for summary
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    count = content.count('@with_rate_limit')
                    total_functions += count
            else:
                print(f"\n⚠️  Skipping {filename} - file not found")
        except Exception as e:
            print(f"\n❌ Error processing {filename}: {e}")

    print("\n" + "=" * 70)
    print(f"✅ INTEGRATION COMPLETE!")
    print(f"   Total API files processed: {len(API_FILES)}")
    print(f"   Total functions protected: {total_functions}")
    print("=" * 70)


if __name__ == "__main__":
    main()
