"""
Simple script to add circuit breaker decorators
"""
from pathlib import Path

def add_circuit_breaker(file_path, service_name):
    """Add circuit breaker decorator before each @with_retry"""
    path = Path(file_path)

    if not path.exists():
        print(f"File not found: {file_path}")
        return

    lines = path.read_text(encoding='utf-8').split('\n')
    new_lines = []

    # Add import if needed
    has_import = False
    for line in lines:
        if "from tools.resilience.circuit_breaker import with_circuit_breaker" in line:
            has_import = True
            break

    # Process lines
    for i, line in enumerate(lines):
        # Check if we need to add import
        if not has_import and "from tools.resilience.retry_handler import" in line:
            new_lines.append(line)
            new_lines.append("from tools.resilience.circuit_breaker import with_circuit_breaker")
            has_import = True
            continue

        # Add circuit breaker before @with_retry if not already there
        if line.strip().startswith("@with_retry("):
            # Check if previous line already has circuit breaker
            if i > 0 and "@with_circuit_breaker" in lines[i-1]:
                new_lines.append(line)  # Already has it
            else:
                # Add circuit breaker decorator
                indent = len(line) - len(line.lstrip())
                new_lines.append(' ' * indent + f'@with_circuit_breaker("{service_name}")')
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Write back
    path.write_text('\n'.join(new_lines), encoding='utf-8')

    # Count decorators
    count = '\n'.join(new_lines).count(f'@with_circuit_breaker("{service_name}")')
    print(f"[OK] {file_path}: Added circuit breaker to {count} functions")

# Process all API files
apis = [
    ("tools/api_implementations/sheets_api.py", "sheets"),
    ("tools/api_implementations/contacts_api.py", "people"),
    ("tools/api_implementations/tasks_api.py", "tasks"),
    ("tools/api_implementations/gmail_api.py", "gmail"),
    ("tools/api_implementations/drive_api.py", "drive"),
    ("tools/api_implementations/calendar_api.py", "calendar"),
]

print("Adding circuit breaker decorators...\n")
for file_path, service in apis:
    add_circuit_breaker(file_path, service)

print("\n[SUCCESS] All API files updated!")
