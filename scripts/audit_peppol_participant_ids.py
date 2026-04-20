#!/usr/bin/env python3
"""
Audit: Peppol Participant ID duplicates in company_settings
============================================================
Read-only script that scans the ``company_settings`` Firestore collection and
reports any ``peppol_participant_id`` values shared by more than one company.

Since Sprint D0, CompanyService enforces uniqueness at write time, so new
duplicates cannot be created.  Use this script to identify any *legacy*
duplicates that existed before D0 was deployed.

Exit codes:
  0 — no duplicates found (or no Peppol IDs at all)
  1 — one or more duplicates found (routing is ambiguous for these IDs)

Usage:
  python scripts/audit_peppol_participant_ids.py
  python scripts/audit_peppol_participant_ids.py --verbose
"""

import asyncio
import os
import sys
from collections import defaultdict


async def run(verbose: bool = False) -> int:
    # Bootstrap path so we can import project modules
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from services.erp.base_erp_service import get_firestore_db

    db = get_firestore_db()
    col = db.collection("company_settings")

    # Map peppol_participant_id -> list of (company_id, company_name)
    by_peppol: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total = 0

    async for snap in col.stream():
        total += 1
        data = snap.to_dict() or {}
        pid = (data.get("peppol_participant_id") or "").strip()
        if pid:
            by_peppol[pid].append((snap.id, data.get("name") or snap.id))

    if verbose:
        print(f"Scanned {total} company_settings document(s).")
        print(f"Peppol IDs in use: {len(by_peppol)}")
        print()

    duplicates = {pid: entries for pid, entries in by_peppol.items() if len(entries) > 1}

    if not duplicates:
        print("OK — no duplicate peppol_participant_id values found.")
        return 0

    print(f"WARNING — {len(duplicates)} duplicate peppol_participant_id value(s) found:")
    print()
    for pid, entries in sorted(duplicates.items()):
        print(f"  peppol_participant_id: {pid!r}")
        for company_id, name in entries:
            print(f"    company_id={company_id!r}  name={name!r}")
        print()
    print(
        "These IDs are ambiguous for inbound webhook routing.  "
        "For each duplicate, keep the correct company and clear the field on the others "
        "via: PATCH /api/erp/company/settings  {\"peppol_participant_id\": \"\"}"
    )
    return 1


def main() -> None:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    exit_code = asyncio.run(run(verbose=verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
