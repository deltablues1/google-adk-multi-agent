"""
NKD 2025 - Nacionalna Klasifikacija Djelatnosti Service

Provides:
- Loading NKD 2025 classification data
- Search by code or description
- Hierarchical navigation (Podrucje > Odjeljak > Skupina > Razred > Podrazred)
- LLM-friendly activity mapping suggestions
- Company registered activities validation

NKD 2025 structure:
- Podrucje (Section): A-V (1 letter)
- Odjeljak (Division): 01-99 (2 digits)
- Skupina (Group): 01.1-99.9 (3 digits with dot)
- Razred (Class): 01.11-99.99 (4 digits with dot)
- Podrazred (Subclass): 01.11.0-99.99.9 (5 digits with dots)
"""

import json
import csv
import os
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class NKDEntry:
    """Single NKD classification entry."""
    code: str
    name: str
    level: str  # podrucje, odjeljak, skupina, razred, podrazred
    parent_code: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "level": self.level,
            "parent_code": self.parent_code
        }


@dataclass
class NKDHierarchy:
    """Hierarchical NKD entry with children."""
    entry: NKDEntry
    children: List['NKDHierarchy'] = field(default_factory=list)


class NKDService:
    """
    Service for NKD 2025 classification lookup and search.

    Supports:
    - Loading from JSON or CSV
    - Exact code lookup
    - Fuzzy text search
    - Hierarchical navigation
    - Company activity validation
    """

    # Level names in Croatian
    LEVEL_NAMES = {
        "podrucje": "Područje",
        "odjeljak": "Odjeljak",
        "skupina": "Skupina",
        "razred": "Razred",
        "podrazred": "Podrazred"
    }

    def __init__(self, data_path: str = None):
        """
        Initialize NKD service.

        Args:
            data_path: Path to NKD data file (JSON or CSV).
                      If None, looks in default locations.
        """
        self._entries: Dict[str, NKDEntry] = {}
        self._by_level: Dict[str, List[NKDEntry]] = {
            "podrucje": [],
            "odjeljak": [],
            "skupina": [],
            "razred": [],
            "podrazred": []
        }
        self._search_index: Dict[str, List[str]] = {}  # word -> [codes]
        self._company_activities: List[str] = []

        if data_path:
            self.load(data_path)

    def load(self, path: str) -> bool:
        """
        Load NKD data from file.

        Args:
            path: Path to JSON or CSV file

        Returns:
            True if loaded successfully
        """
        path = Path(path)

        if not path.exists():
            logger.error(f"NKD data file not found: {path}")
            return False

        try:
            if path.suffix.lower() == '.json':
                return self._load_json(path)
            elif path.suffix.lower() == '.csv':
                return self._load_csv(path)
            else:
                logger.error(f"Unsupported file format: {path.suffix}")
                return False
        except Exception as e:
            logger.error(f"Failed to load NKD data: {e}")
            return False

    def _load_json(self, path: Path) -> bool:
        """Load from JSON format."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Skip header row if present
        start_idx = 1 if data and data[0].get("5") == "Naziv" else 0

        for row in data[start_idx:]:
            entry = self._parse_row(row)
            if entry:
                self._add_entry(entry)

        self._build_search_index()
        logger.info(f"Loaded {len(self._entries)} NKD entries from JSON")
        return True

    def _load_csv(self, path: Path) -> bool:
        """Load from CSV format."""
        with open(path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)

            # Skip header rows
            next(reader, None)  # Column numbers
            next(reader, None)  # Column names

            for row in reader:
                if len(row) >= 6:
                    row_dict = {
                        "0": row[0] if row[0] else None,
                        "1": row[1] if row[1] else None,
                        "2": row[2] if row[2] else None,
                        "3": row[3] if row[3] else None,
                        "4": row[4] if row[4] else None,
                        "5": row[5] if row[5] else None
                    }
                    entry = self._parse_row(row_dict)
                    if entry:
                        self._add_entry(entry)

        self._build_search_index()
        logger.info(f"Loaded {len(self._entries)} NKD entries from CSV")
        return True

    def _parse_row(self, row: dict) -> Optional[NKDEntry]:
        """Parse a row into NKDEntry."""
        name = row.get("5", "").strip()
        if not name:
            return None

        # Determine level and code based on which column has value
        if row.get("0"):  # Podrucje (A, B, C...)
            code = row["0"]
            level = "podrucje"
            parent = None
        elif row.get("1"):  # Odjeljak (01, 02...)
            code = row["1"]
            level = "odjeljak"
            # Parent is the section letter - need to find it
            parent = self._find_section_for_division(code)
        elif row.get("2"):  # Skupina (01.1, 01.2...)
            code = row["2"]
            level = "skupina"
            parent = code.split('.')[0]  # 01.1 -> 01
        elif row.get("3"):  # Razred (01.11, 01.12...)
            code = row["3"]
            level = "razred"
            # 01.11 -> 01.1
            parts = code.split('.')
            parent = f"{parts[0]}.{parts[1][0]}" if len(parts) > 1 else None
        elif row.get("4"):  # Podrazred (01.11.0...)
            code = row["4"]
            level = "podrazred"
            # 01.11.0 -> 01.11
            parent = '.'.join(code.split('.')[:2])
        else:
            return None

        return NKDEntry(
            code=code,
            name=name,
            level=level,
            parent_code=parent
        )

    def _find_section_for_division(self, division_code: str) -> Optional[str]:
        """Find section letter for a division code based on NACE Rev. 2 ranges."""
        try:
            div_num = int(division_code)
        except ValueError:
            return None

        # NACE Rev. 2 section ranges
        section_ranges = {
            "A": (1, 3),
            "B": (5, 9),
            "C": (10, 33),
            "D": (35, 35),
            "E": (36, 39),
            "F": (41, 43),
            "G": (45, 47),
            "H": (49, 53),
            "I": (55, 56),
            "J": (58, 63),
            "K": (64, 66),
            "L": (68, 68),
            "M": (69, 75),
            "N": (77, 82),
            "O": (84, 84),
            "P": (85, 85),
            "Q": (86, 88),
            "R": (90, 93),
            "S": (94, 96),
            "T": (97, 98),
            "U": (99, 99)
        }

        for section, (start, end) in section_ranges.items():
            if start <= div_num <= end:
                return section
        return None

    def _add_entry(self, entry: NKDEntry):
        """Add entry to indices."""
        self._entries[entry.code] = entry
        self._by_level[entry.level].append(entry)

    def _build_search_index(self):
        """Build inverted index for text search."""
        self._search_index.clear()

        for code, entry in self._entries.items():
            # Tokenize name
            words = self._tokenize(entry.name)
            for word in words:
                if word not in self._search_index:
                    self._search_index[word] = []
                if code not in self._search_index[word]:
                    self._search_index[word].append(code)

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text for search index."""
        # Convert to lowercase, remove punctuation, split
        text = text.lower()
        text = re.sub(r'[^\w\sčćžšđ]', ' ', text)
        words = text.split()
        # Filter short words
        return [w for w in words if len(w) >= 3]

    # =========================================================================
    # Public API
    # =========================================================================

    def get(self, code: str) -> Optional[NKDEntry]:
        """
        Get NKD entry by exact code.

        Args:
            code: NKD code (e.g., "43.32", "43.32.0", "F")

        Returns:
            NKDEntry or None if not found
        """
        return self._entries.get(code)

    def search(self, query: str, limit: int = 10, level: str = None) -> List[NKDEntry]:
        """
        Search NKD entries by text.

        Args:
            query: Search text (e.g., "ugradnja stolarije", "pivo")
            limit: Maximum results
            level: Filter by level (podrucje, odjeljak, skupina, razred, podrazred)

        Returns:
            List of matching entries sorted by relevance
        """
        query_words = self._tokenize(query)
        if not query_words:
            return []

        # Score each entry
        scores: Dict[str, int] = {}

        for word in query_words:
            # Exact word match
            if word in self._search_index:
                for code in self._search_index[word]:
                    scores[code] = scores.get(code, 0) + 10

            # Prefix match
            for index_word, codes in self._search_index.items():
                if index_word.startswith(word) or word.startswith(index_word):
                    for code in codes:
                        scores[code] = scores.get(code, 0) + 5

        # Sort by score descending
        sorted_codes = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)

        # Filter by level if specified
        results = []
        for code in sorted_codes:
            entry = self._entries[code]
            if level is None or entry.level == level:
                results.append(entry)
                if len(results) >= limit:
                    break

        return results

    def search_for_invoice_item(self, description: str) -> List[Dict[str, Any]]:
        """
        Search for NKD code matching an invoice item description.
        Returns suggestions suitable for LLM and user selection.

        Args:
            description: Invoice item description (e.g., "Ugradnja PVC prozora")

        Returns:
            List of suggestions with code, name, confidence, and hierarchy
        """
        # Search at podrazred level (most specific)
        results = self.search(description, limit=5, level="podrazred")

        # If no podrazred results, try razred
        if not results:
            results = self.search(description, limit=5, level="razred")

        suggestions = []
        for entry in results:
            # Get hierarchy
            hierarchy = self.get_hierarchy(entry.code)

            suggestion = {
                "code": entry.code,
                "name": entry.name,
                "level": entry.level,
                "level_name": self.LEVEL_NAMES.get(entry.level, entry.level),
                "hierarchy": hierarchy,
                "display": f"{entry.code} - {entry.name}"
            }
            suggestions.append(suggestion)

        return suggestions

    def get_hierarchy(self, code: str) -> List[Dict[str, str]]:
        """
        Get full hierarchy path for a code.

        Args:
            code: NKD code

        Returns:
            List of {code, name, level} from top to bottom
        """
        hierarchy = []
        entry = self._entries.get(code)

        while entry:
            hierarchy.insert(0, {
                "code": entry.code,
                "name": entry.name,
                "level": entry.level
            })

            if entry.parent_code:
                entry = self._entries.get(entry.parent_code)
            else:
                break

        return hierarchy

    def get_children(self, code: str) -> List[NKDEntry]:
        """
        Get direct children of a code.

        Args:
            code: Parent NKD code

        Returns:
            List of child entries
        """
        return [
            entry for entry in self._entries.values()
            if entry.parent_code == code
        ]

    def list_sections(self) -> List[NKDEntry]:
        """Get all top-level sections (Područja)."""
        return self._by_level["podrucje"]

    def get_entry_count(self) -> Dict[str, int]:
        """Get count of entries by level."""
        return {
            level: len(entries)
            for level, entries in self._by_level.items()
        }

    # =========================================================================
    # Company Activity Validation
    # =========================================================================

    def set_company_activities(self, nkd_codes: List[str]):
        """
        Set registered NKD activities for the company.

        Args:
            nkd_codes: List of registered NKD codes
        """
        self._company_activities = nkd_codes
        logger.info(f"Set {len(nkd_codes)} registered company activities")

    def get_company_activities(self) -> List[NKDEntry]:
        """Get registered company activities as NKDEntry list."""
        return [
            self._entries[code]
            for code in self._company_activities
            if code in self._entries
        ]

    def is_activity_registered(self, nkd_code: str) -> Tuple[bool, Optional[str]]:
        """
        Check if NKD activity is registered for the company.

        Args:
            nkd_code: NKD code to check

        Returns:
            Tuple of (is_registered, warning_message)
        """
        if not self._company_activities:
            return True, None  # No restrictions if not configured

        # Check exact match
        if nkd_code in self._company_activities:
            return True, None

        # Check if parent is registered (e.g., 43.32 covers 43.32.0)
        entry = self._entries.get(nkd_code)
        if entry and entry.parent_code:
            if entry.parent_code in self._company_activities:
                return True, None

        # Check if any child is registered
        for registered in self._company_activities:
            reg_entry = self._entries.get(registered)
            if reg_entry:
                # Check if nkd_code is parent of registered
                if registered.startswith(nkd_code):
                    return True, None

        # Not registered - create warning
        entry = self._entries.get(nkd_code)
        if entry:
            warning = (
                f"NKD {nkd_code} ({entry.name}) NIJE registrirana djelatnost za vašu tvrtku. "
                f"Potrebno je registrirati djelatnost prije izdavanja računa."
            )
        else:
            warning = f"NKD {nkd_code} nije pronađen u klasifikaciji."

        return False, warning

    def validate_invoice_items(
        self,
        items: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Validate NKD codes for all invoice items.

        Args:
            items: List of items with 'nkd_code' key

        Returns:
            Validation result with warnings
        """
        warnings = []
        all_valid = True

        for i, item in enumerate(items):
            nkd_code = item.get("nkd_code")
            if not nkd_code:
                continue

            is_valid, warning = self.is_activity_registered(nkd_code)
            if not is_valid:
                all_valid = False
                warnings.append({
                    "item_index": i,
                    "item_description": item.get("description", ""),
                    "nkd_code": nkd_code,
                    "warning": warning
                })

        return {
            "valid": all_valid,
            "warnings": warnings,
            "registered_activities": len(self._company_activities)
        }


# ============================================================================
# Module-level singleton and helper functions
# ============================================================================

_nkd_service: Optional[NKDService] = None


def get_nkd_service(data_path: str = None) -> NKDService:
    """
    Get or create NKD service singleton.

    Args:
        data_path: Optional path to NKD data file

    Returns:
        NKDService instance
    """
    global _nkd_service

    if _nkd_service is None:
        _nkd_service = NKDService()

        # Try to load from default locations
        if data_path:
            _nkd_service.load(data_path)
        else:
            # Try common locations
            possible_paths = [
                Path(__file__).parent.parent.parent / "data" / "kpd_2025" / "NKD_2025.json",
                Path(__file__).parent.parent.parent / "data" / "kpd_2025" / "NKD_2025.csv",
                Path(__file__).parent.parent.parent / "data" / "NKD_2025.json",
                Path(__file__).parent.parent.parent / "NKD_2025.json",
                Path(__file__).parent.parent.parent / "NKD_2025.csv",
            ]

            for path in possible_paths:
                if path.exists():
                    _nkd_service.load(str(path))
                    break

    return _nkd_service


def search_nkd(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search NKD by text description.

    Args:
        query: Search text
        limit: Max results

    Returns:
        List of matching entries as dicts
    """
    service = get_nkd_service()
    entries = service.search(query, limit=limit)
    return [e.to_dict() for e in entries]


def get_nkd(code: str) -> Optional[Dict[str, Any]]:
    """
    Get NKD entry by code.

    Args:
        code: NKD code

    Returns:
        Entry dict or None
    """
    service = get_nkd_service()
    entry = service.get(code)
    return entry.to_dict() if entry else None


def suggest_nkd_for_item(description: str) -> List[Dict[str, Any]]:
    """
    Suggest NKD codes for invoice item description.

    Args:
        description: Item description

    Returns:
        List of suggestions with hierarchy
    """
    service = get_nkd_service()
    return service.search_for_invoice_item(description)


def validate_company_activity(nkd_code: str) -> Dict[str, Any]:
    """
    Check if NKD is registered for company.

    Args:
        nkd_code: NKD code to check

    Returns:
        Dict with is_registered and warning
    """
    service = get_nkd_service()
    is_registered, warning = service.is_activity_registered(nkd_code)

    entry = service.get(nkd_code)

    return {
        "code": nkd_code,
        "name": entry.name if entry else None,
        "is_registered": is_registered,
        "warning": warning
    }
