#!/usr/bin/env python3
"""
Finalize retry integration for remaining API files
"""
import re
import sys

FILES = [
    "tools/api_implementations/gmail_api.py",
    "tools/api_implementations/drive_api.py",
    "tools/api_implementations/calendar_api.py",
]

IMPORT_LINE = "from tools.resilience.retry_handler import with_retry, RetryConfig"
DECORATOR = "@with_retry(RetryConfig(max_retries=3, base_delay=1.0))"


def process_file(filepath):
    """Add retry decorators to a file"""
    print(f"\nProcessing: {filepath}")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"  ERROR: File not found")
        return False

    # Check if already has import
    has_import = any(IMPORT_LINE in line for line in lines)

    if has_import:
        print(f"  SKIP: Already has retry import")
        return True

    # Step 1: Add import after "import logging"
    new_lines = []
    import_added = False

    for line in lines:
        new_lines.append(line)
        if not import_added and line.strip() == "import logging":
            new_lines.append("\n")
            new_lines.append(IMPORT_LINE + "\n")
            import_added = True
            print(f"  OK: Added import")

    # Step 2: Add decorators to async functions
    final_lines = []
    decorator_count = 0

    i = 0
    while i < len(new_lines):
        line = new_lines[i]

        # Check if this is an async function definition
        if line.strip().startswith("async def "):
            # Add decorator before async def
            final_lines.append(DECORATOR + "\n")
            final_lines.append(line)
            decorator_count += 1
            print(f"  OK: Added decorator to: {line.strip()[:50]}...")
        else:
            final_lines.append(line)

        i += 1

    # Step 3: Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(final_lines)

    print(f"  DONE: {decorator_count} decorators added")
    return True


def main():
    print("=" * 60)
    print("FINALIZING RETRY INTEGRATION")
    print("=" * 60)

    success_count = 0

    for filepath in FILES:
        if process_file(filepath):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"COMPLETED: {success_count}/{len(FILES)} files processed")
    print("=" * 60)

    if success_count == len(FILES):
        print("\nSUCCESS: All files integrated with retry handler!")
        return 0
    else:
        print("\nWARNING: Some files failed to process")
        return 1


if __name__ == "__main__":
    sys.exit(main())
