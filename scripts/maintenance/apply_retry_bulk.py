"""
Bulk apply retry decorators to all remaining API files
"""

import re

# Files to process
FILES = [
    "tools/api_implementations/tasks_api.py",
    "tools/api_implementations/gmail_api.py",
    "tools/api_implementations/drive_api.py",
    "tools/api_implementations/calendar_api.py",
]

IMPORT_LINE = "from tools.resilience.retry_handler import with_retry, RetryConfig\n"
DECORATOR = "@with_retry(RetryConfig(max_retries=3, base_delay=1.0))\n"


def process_file(filepath):
    """Add retry decorator to all async functions in a file"""
    print(f"\n📄 Processing: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if already has import
    if "from tools.resilience.retry_handler import" in content:
        print(f"  ✅ Already has import, skipping...")
        return

    # Step 1: Add import after logging
    if "import logging\n" in content:
        content = content.replace(
            "import logging\n",
            f"import logging\n\n{IMPORT_LINE}"
        )
        print(f"  ✅ Added import statement")

    # Step 2: Find and add decorator to async functions
    # Pattern: "async def function_name(" at start of line
    pattern = r'^(async def \w+\()'

    def add_decorator(match):
        """Add decorator before async def"""
        return f"{DECORATOR}{match.group(1)}"

    # Replace all async def with decorated version
    content_new = re.sub(pattern, add_decorator, content, flags=re.MULTILINE)

    # Count decorators added
    decorators_added = content_new.count(DECORATOR)
    print(f"  ✅ Added {decorators_added} retry decorators")

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content_new)

    print(f"  ✅ File updated successfully")


def main():
    print("🚀 Bulk applying retry decorators...")
    print(f"   Files to process: {len(FILES)}")

    for filepath in FILES:
        try:
            process_file(filepath)
        except Exception as e:
            print(f"  ❌ Error: {e}")

    print("\n✅ Done! All files processed.")


if __name__ == "__main__":
    main()
