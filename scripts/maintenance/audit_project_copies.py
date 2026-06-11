"""Audit duplicate project copies against this (canonical) working copy.

Scans the parent workspace folder for other copies of this project, then for
each copy reports:
  - files that exist ONLY in the copy (not in the canonical repo)
  - files that DIFFER and are NEWER in the copy (potentially unsaved work)

Copies with no unique/newer files are safe to archive or delete.

Usage:
    python scripts/maintenance/audit_project_copies.py            # summary
    python scripts/maintenance/audit_project_copies.py --verbose  # list files
"""

import hashlib
import sys
from datetime import datetime
from pathlib import Path

CANONICAL = Path(__file__).resolve().parents[2]
SEARCH_ROOT = CANONICAL.parents[1]  # the "ai agenti" workspace folder

# A directory is considered a project copy if it contains this marker file.
MARKER = Path("config") / "agent_registry.py"

IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules",
    "logs", "uploads", "sessions", "output", ".idea", ".vscode",
}
IGNORE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}
IGNORE_NAMES = {".env", "tokens.json", "service_account_key.json"}


def find_copies(search_root: Path, canonical: Path) -> list[Path]:
    """Find project copies (dirs containing the marker) up to 3 levels deep."""
    copies = []
    seen = set()

    def scan(directory: Path, depth: int):
        if depth > 3:
            return
        try:
            entries = [e for e in directory.iterdir() if e.is_dir()]
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.name in IGNORE_DIRS:
                continue
            root = entry.resolve()
            if root == canonical or root in seen:
                continue
            if (entry / MARKER).is_file():
                seen.add(root)
                copies.append(entry)
            else:
                scan(entry, depth + 1)

    scan(search_root, 1)
    return sorted(copies)


def iter_project_files(root: Path):
    """Yield relative paths of relevant files under a project root."""
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in IGNORE_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                if entry.suffix.lower() in IGNORE_SUFFIXES or entry.name in IGNORE_NAMES:
                    continue
                yield entry.relative_to(root)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def files_differ(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return True
    return file_hash(a) != file_hash(b)


def audit_copy(copy_root: Path, canonical: Path):
    only_in_copy, newer_in_copy, older_diverged = [], [], []
    for rel in iter_project_files(copy_root):
        copy_file = copy_root / rel
        canon_file = canonical / rel
        if not canon_file.exists():
            only_in_copy.append(rel)
            continue
        try:
            if files_differ(copy_file, canon_file):
                if copy_file.stat().st_mtime > canon_file.stat().st_mtime:
                    newer_in_copy.append(rel)
                else:
                    older_diverged.append(rel)
        except OSError:
            continue
    return only_in_copy, newer_in_copy, older_diverged


def main():
    verbose = "--verbose" in sys.argv
    print(f"Canonical : {CANONICAL}")
    print(f"Workspace : {SEARCH_ROOT}\n")

    copies = find_copies(SEARCH_ROOT, CANONICAL)
    if not copies:
        print("No other project copies found.")
        return

    for copy_root in copies:
        only, newer, older = audit_copy(copy_root, CANONICAL)
        mtime = datetime.fromtimestamp(copy_root.stat().st_mtime).strftime("%Y-%m-%d")
        print(f"=== {copy_root}  (modified {mtime})")
        print(f"    only-in-copy: {len(only)} | newer-in-copy: {len(newer)} "
              f"| older/diverged: {len(older)}")
        if not only and not newer:
            print("    -> SAFE TO ARCHIVE (nothing unique or newer here)")
        else:
            print("    -> REVIEW before archiving:")
            shown = only[:15] if not verbose else only
            for rel in shown:
                print(f"       [only ] {rel}")
            if not verbose and len(only) > 15:
                print(f"       ... and {len(only) - 15} more (use --verbose)")
            shown = newer[:15] if not verbose else newer
            for rel in shown:
                print(f"       [newer] {rel}")
            if not verbose and len(newer) > 15:
                print(f"       ... and {len(newer) - 15} more (use --verbose)")
        print()


if __name__ == "__main__":
    main()
