"""
Bulk add retry decorators to all API implementations

This script adds:
1. Import statement for retry handler
2. @with_retry decorator to all async functions
"""

import os
import re

# List of API files to process
API_FILES = [
    "tools/api_implementations/gmail_api.py",
    "tools/api_implementations/drive_api.py",
    "tools/api_implementations/calendar_api.py",
    "tools/api_implementations/contacts_api.py",
    "tools/api_implementations/tasks_api.py",
]

# Import statement to add
IMPORT_STATEMENT = "from tools.resilience.retry_handler import with_retry, RetryConfig\n"

# Decorator to add
DECORATOR = "@with_retry(RetryConfig(max_retries=3, base_delay=1.0))\n"


def add_retry_to_file(filepath):
    """Add retry handler to a single file"""
    print(f"\nProcessing: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if already has retry import
    if "from tools.resilience.retry_handler import" in content:
        print(f"  ✅ Already has retry import")
        return

    # Add import after logging import
    if "import logging" in content:
        content = content.replace(
            "import logging\n",
            f"import logging\n\n{IMPORT_STATEMENT}"
        )
        print(f"  ✅ Added import statement")

    # Find all async function definitions
    async_functions = re.findall(r'(^async def \w+\()', content, re.MULTILINE)
    print(f"  📋 Found {len(async_functions)} async functions")

    # Add decorator to each async function
    for func_match in async_functions:
        # Check if already has decorator
        pattern = f"@with_retry.*\n{re.escape(func_match)}"
        if re.search(pattern, content):
            continue

        # Add decorator
        content = content.replace(
            func_match,
            f"{DECORATOR}{func_match}"
        )

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  ✅ Added retry decorators")


def main():
    """Process all API files"""
    print("🚀 Adding retry decorators to all API implementations...")

    for api_file in API_FILES:
        try:
            add_retry_to_file(api_file)
        except Exception as e:
            print(f"  ❌ Error processing {api_file}: {e}")

    print("\n✅ Done! All API files processed.")
    print("\nFiles updated:")
    for api_file in API_FILES:
        print(f"  - {api_file}")


if __name__ == "__main__":
    main()
