"""
Bulk script to add Circuit Breaker decorator to all API functions

Dodaje @with_circuit_breaker() decorator iznad svakog @with_retry() decoratora
"""

import re
from pathlib import Path

# API files to update
API_FILES = [
    ("tools/api_implementations/sheets_api.py", "sheets"),
    ("tools/api_implementations/contacts_api.py", "people"),
    ("tools/api_implementations/tasks_api.py", "tasks"),
    ("tools/api_implementations/gmail_api.py", "gmail"),
    ("tools/api_implementations/drive_api.py", "drive"),
    ("tools/api_implementations/calendar_api.py", "calendar"),
]

def add_circuit_breaker_to_file(file_path: str, service_name: str):
    """Add circuit breaker import and decorators to API file"""
    path = Path(file_path)

    if not path.exists():
        print(f"❌ File not found: {file_path}")
        return False

    print(f"Processing: {file_path}")

    # Read file
    content = path.read_text(encoding='utf-8')

    # Check if already has circuit breaker import
    if "from tools.resilience.circuit_breaker import with_circuit_breaker" in content:
        print(f"  [OK] Already has circuit breaker import")
    else:
        # Add import after retry_handler import
        content = content.replace(
            "from tools.resilience.retry_handler import with_retry, RetryConfig",
            "from tools.resilience.retry_handler import with_retry, RetryConfig\n"
            "from tools.resilience.circuit_breaker import with_circuit_breaker"
        )
        print(f"  [OK] Added circuit breaker import")

    # Add @with_circuit_breaker() decorator before each @with_retry()
    # Pattern: find @with_retry that's NOT already preceded by @with_circuit_breaker
    pattern = r'(?<!@with_circuit_breaker\("[^"]+"\)\n)(@with_retry\(RetryConfig\([^)]+\)\)\nasync def [a-z_]+\()'

    def add_decorator(match):
        return f'@with_circuit_breaker("{service_name}")\n{match.group(1)}'

    original_content = content
    content = re.sub(pattern, add_decorator, content)

    if content != original_content:
        # Write back
        path.write_text(content, encoding='utf-8')

        # Count decorators added
        count = content.count(f'@with_circuit_breaker("{service_name}")')
        print(f"  [OK] Added circuit breaker to {count} functions")
        return True
    else:
        print(f"  [OK] All functions already have circuit breaker")
        return True

def main():
    print("=" * 60)
    print("BULK CIRCUIT BREAKER INTEGRATION")
    print("=" * 60)
    print()

    success_count = 0

    for file_path, service_name in API_FILES:
        if add_circuit_breaker_to_file(file_path, service_name):
            success_count += 1
        print()

    print("=" * 60)
    print(f"COMPLETED: {success_count}/{len(API_FILES)} files updated")
    print("=" * 60)

    if success_count == len(API_FILES):
        print("\n[SUCCESS] ALL API FILES UPDATED SUCCESSFULLY!")
    else:
        print(f"\n[WARNING] Some files had issues. Please check manually.")

if __name__ == "__main__":
    main()
