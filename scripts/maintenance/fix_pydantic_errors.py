#!/usr/bin/env python3
"""
Fix Pydantic Validation Errors in MCP Tool Files

Removes all 'optional': True lines from MCP toolsets as they cause
Pydantic v2 validation errors. Optional parameters are defined by
NOT being in the 'required' list.
"""

import os
import re
from pathlib import Path


def fix_optional_fields(file_path: Path) -> tuple[int, bool]:
    """
    Remove 'optional': True lines from a file

    Args:
        file_path: Path to the file to fix

    Returns:
        Tuple of (lines_removed, file_was_modified)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Pattern to match lines with "optional": True
    # Handles various formatting:
    #   "optional": True
    #   "optional": True,
    #   with any amount of whitespace
    pattern = re.compile(r'^\s*"optional"\s*:\s*True\s*,?\s*$')

    # Filter out lines matching the pattern
    original_count = len(lines)
    filtered_lines = [line for line in lines if not pattern.match(line)]
    new_count = len(filtered_lines)

    lines_removed = original_count - new_count

    if lines_removed > 0:
        # Write back the filtered content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(filtered_lines)
        return lines_removed, True

    return 0, False


def main():
    """Main execution"""
    print("="*70)
    print("Fixing Pydantic Validation Errors in MCP Tools")
    print("="*70)
    print()

    # MCP toolset directory
    toolsets_dir = Path("tools/mcp_toolsets")

    if not toolsets_dir.exists():
        print(f"ERROR: Directory not found: {toolsets_dir}")
        return

    # Find all Python files in the directory
    mcp_files = list(toolsets_dir.glob("*.py"))

    if not mcp_files:
        print(f"ERROR: No Python files found in {toolsets_dir}")
        return

    print(f"Found {len(mcp_files)} MCP tool files")
    print()

    total_lines_removed = 0
    files_modified = 0

    # Process each file
    for file_path in sorted(mcp_files):
        if file_path.name == "__init__.py":
            continue

        print(f"Processing: {file_path.name}...", end=" ")

        lines_removed, was_modified = fix_optional_fields(file_path)

        if was_modified:
            print(f"OK - Removed {lines_removed} line(s)")
            total_lines_removed += lines_removed
            files_modified += 1
        else:
            print("OK - No changes needed")

    print()
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Files processed: {len(mcp_files)}")
    print(f"Files modified: {files_modified}")
    print(f"Total lines removed: {total_lines_removed}")
    print()

    if files_modified > 0:
        print("SUCCESS! All Pydantic errors fixed!")
        print()
        print("Next step: Re-run test_real_system.py to verify the fixes")
        print("  py test_real_system.py")
    else:
        print("INFO: No modifications were needed")


if __name__ == "__main__":
    main()
