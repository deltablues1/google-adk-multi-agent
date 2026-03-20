"""
Fiskalizacija ADK Tools

ADK-compatible tools for Croatian electronic invoicing (Fiskalizacija 2.0).

These tools provide deterministic operations for:
- OIB validation (Module 11)
- VAT calculation (Decimal precision)
- KPD code search (RAG)
- UBL XML generation
- XSD validation
- XAdES signing
- FINA SOAP communication
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
import logging
import json
import re

logger = logging.getLogger(__name__)

# Import Pydantic models
from tools.api_implementations.fiskalizacija_models import (
    OIBResult,
    VIESResult,
    KPDMatch,
    KPDSearchResult,
    TaxItem,
    TaxSubtotal,
    TaxBreakdown,
    VATRate,
    ValidationStatus,
    FiskalniPodaci,
    FiskalizacijaResult,
    FiskalizacijaStatus,
    XSDValidationResult,
    XSDError,
    ValidationCheck,
    ValidationResult,
    normalize_unit_code,
    validate_oib_checksum,
    UNIT_CODE_MAP,
)


# ============================================================================
# VALIDATION AND PREPARATION TOOLS
# ============================================================================

async def get_supplier_data() -> dict:
    """
    Get supplier (issuer) company data from company configuration.

    CRITICAL: This tool MUST be called at the start of fiscalization workflow
    to automatically load the correct supplier OIB, address, and business unit data.

    This eliminates the need to manually pass supplier data and prevents
    the common error of using default/invalid OIB (00000000000).

    Returns:
        Dictionary containing:
            - success: bool - Whether data was loaded successfully
            - supplier: dict - Supplier data if successful:
                - name: str - Company name (e.g., "LUX TECH D.O.O.")
                - oib: str - Valid 11-digit OIB (e.g., "47034854402")
                - address: str - Street address
                - city: str - City name
                - postal_code: str - Postal code
                - email: str - Contact email
                - phone: str - Contact phone
                - business_unit: str - Business premise code (default: "1")
                - device_number: str - Cash register code (default: "1")
            - error: Optional[str] - Error message if failed

    Example:
        result = await get_supplier_data()
        # Returns: {
        #     "success": true,
        #     "supplier": {
        #         "name": "LUX TECH D.O.O.",
        #         "oib": "47034854402",
        #         "address": "Leskovački brijeg 2",
        #         "city": "Hrvatski Leskovac",
        #         "postal_code": "10257",
        #         "email": "tomislav.luxtech@gmail.com",
        #         "phone": "+385914575757",
        #         "business_unit": "1",
        #         "device_number": "1"
        #     }
        # }
    """
    try:
        from config.company_config import get_company_config

        config = get_company_config()

        # Validate OIB exists and is correct length
        oib = config.oib
        if not oib or len(oib) != 11:
            logger.error(f"Invalid supplier OIB in company config: {oib}")
            return {
                "success": False,
                "error": f"Invalid supplier OIB in company_config.py: '{oib}' (must be 11 digits)"
            }

        # Get default business premise and cash register
        if not config.business_premises:
            logger.error("No business premises configured")
            return {
                "success": False,
                "error": "No business premises found in company_config.py"
            }

        if not config.cash_registers:
            logger.error("No cash registers configured")
            return {
                "success": False,
                "error": "No cash registers found in company_config.py"
            }

        premise = config.business_premises[0]
        register = config.cash_registers[0]

        supplier = {
            "name": config.name,
            "oib": config.oib,
            "address": config.address,
            "city": config.city,
            "postal_code": config.postal_code,
            "email": config.email,
            "phone": config.phone,
            "business_unit": premise.code,
            "device_number": register.code
        }

        logger.info(f"Supplier data loaded: {config.name}, OIB: ***{oib[-4:]}")

        return {
            "success": True,
            "supplier": supplier
        }

    except ImportError as e:
        logger.error(f"Could not import company_config: {e}")
        return {
            "success": False,
            "error": f"Could not load company_config.py: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error loading supplier data: {e}")
        return {
            "success": False,
            "error": f"Error loading supplier data: {str(e)}"
        }


async def generate_invoice_number(year: Optional[int] = None) -> dict:
    """
    Auto-generate sequential invoice number in FINA-compliant format.

    CRITICAL: FINA requires format "BrojRacuna/OznakaPoslovnogProstora/OznakaUredjaja"
    Example: "1/A1/1" or "123/PP1/NU2"

    This tool eliminates the need to ask users for invoice numbers.
    Format: XXX/PP/NU where:
    - XXX = sequential invoice number (001, 002, ...)
    - PP = business premise code (from company_config)
    - NU = cash register code (from company_config)

    Args:
        year: Year for invoice (optional, not used in FINA format but kept for compatibility)

    Returns:
        Dictionary containing:
            - success: bool - Whether generation succeeded
            - invoice_number: str - Generated number (e.g., "001/1/1")
            - next_sequence: int - Next sequential number
            - business_unit: str - Business premise code used
            - device_number: str - Cash register code used
            - error: Optional[str] - Error message if failed

    Example:
        result = await generate_invoice_number()
        # Returns: {
        #     "success": true,
        #     "invoice_number": "001/1/1",
        #     "next_sequence": 1,
        #     "business_unit": "1",
        #     "device_number": "1"
        # }
    """
    try:
        # Get supplier data to retrieve business_unit and device_number
        supplier_result = await get_supplier_data()

        if not supplier_result.get("success"):
            return {
                "success": False,
                "error": f"Cannot generate invoice number: {supplier_result.get('error')}"
            }

        supplier = supplier_result["supplier"]
        business_unit = supplier["business_unit"]  # e.g., "1"
        device_number = supplier["device_number"]  # e.g., "1"
        supplier_oib = supplier["oib"]

        # Use Firestore counter for sequential invoice numbers
        import os
        use_firestore = os.environ.get('USE_FIRESTORE', 'true').lower() == 'true'

        try:
            from tools.api_implementations.fiskalizacija_ledger import get_ledger_service
            ledger = get_ledger_service(use_firestore=use_firestore)
            sequence = ledger.get_next_invoice_number(
                supplier_oib=supplier_oib,
                business_unit=business_unit,
                device_number=device_number,
                year=year
            )
            logger.info(f"Got next invoice number from ledger counter: {sequence}")
        except Exception as e:
            logger.warning(f"Failed to get invoice number from ledger, using fallback: {e}")
            sequence = 1

        # FINA format: BrojRacuna/OznakaPoslovnogProstora/OznakaUredjaja
        invoice_number = f"{sequence}/{business_unit}/{device_number}"

        logger.info(f"Generated FINA-compliant invoice number: {invoice_number} (business_unit={business_unit}, device={device_number})")

        return {
            "success": True,
            "invoice_number": invoice_number,
            "next_sequence": sequence,
            "business_unit": business_unit,
            "device_number": device_number
        }

    except Exception as e:
        logger.error(f"Error generating invoice number: {e}")
        return {
            "success": False,
            "error": f"Failed to generate invoice number: {str(e)}"
        }


async def validate_oib(oib: str) -> dict:
    """
    Validate Croatian OIB (Personal Identification Number) using Module 11 algorithm.

    The OIB is an 11-digit number used to identify individuals and legal entities
    in Croatia. The last digit is a check digit calculated using the Module 11 algorithm.

    CRITICAL: This is a deterministic tool. NEVER trust LLM to validate OIB manually.

    Args:
        oib: String of exactly 11 digits

    Returns:
        Dictionary containing:
            - valid: bool - Whether OIB is valid
            - oib: str - The OIB that was validated
            - error_message: Optional[str] - Error description if invalid

    Example:
        result = await validate_oib("12345678903")
        # Returns: {"valid": true, "oib": "12345678903", "error_message": null}

        result = await validate_oib("12345678901")
        # Returns: {"valid": false, "oib": "12345678901", "error_message": "Invalid checksum"}
    """
    try:
        # Clean input
        oib_clean = oib.strip() if oib else ""

        # Check length
        if len(oib_clean) != 11:
            return {
                "valid": False,
                "oib": oib_clean,
                "error_message": f"OIB must be exactly 11 digits, got {len(oib_clean)}"
            }

        # Check digits only
        if not oib_clean.isdigit():
            return {
                "valid": False,
                "oib": oib_clean,
                "error_message": "OIB must contain only digits"
            }

        # Module 11 validation
        is_valid = validate_oib_checksum(oib_clean)

        if is_valid:
            logger.info(f"OIB validated successfully: ***{oib_clean[-4:]}")
            return {
                "valid": True,
                "oib": oib_clean,
                "error_message": None
            }
        else:
            logger.warning(f"OIB validation failed: ***{oib_clean[-4:]}")
            return {
                "valid": False,
                "oib": oib_clean,
                "error_message": "Invalid checksum (Module 11 algorithm failed)"
            }

    except Exception as e:
        logger.error(f"OIB validation error: {e}")
        return {
            "valid": False,
            "oib": oib if oib else "",
            "error_message": f"Validation error: {str(e)}"
        }


async def lookup_vies(vat_number: str) -> dict:
    """
    Check VAT number validity in EU VIES (VAT Information Exchange System) database.

    For Croatian VAT numbers (HR prefix), also verifies against local registry.
    Returns company details if found.

    NOTE: This is currently a stub that validates format only.
    Full VIES API integration requires EU SOAP endpoint access.

    Args:
        vat_number: VAT number with country prefix (e.g., "HR12345678903", "DE123456789")

    Returns:
        Dictionary containing:
            - valid: bool - Whether VAT number format is valid
            - vat_number: str - The VAT number checked
            - company_name: Optional[str] - Company name if found
            - address: Optional[str] - Registered address if found
            - vat_active: bool - Whether VAT registration is active
            - country_code: Optional[str] - Country code (HR, DE, etc.)
            - error_message: Optional[str] - Error if lookup failed

    Example:
        result = await lookup_vies("HR12345678903")
        # Returns: {"valid": true, "company_name": "Example d.o.o.", ...}
    """
    try:
        vat_clean = vat_number.strip().upper() if vat_number else ""

        # Extract country code
        country_match = re.match(r'^([A-Z]{2})(.+)$', vat_clean)
        if not country_match:
            return {
                "valid": False,
                "vat_number": vat_clean,
                "company_name": None,
                "address": None,
                "vat_active": False,
                "country_code": None,
                "error_message": "VAT number must start with 2-letter country code (e.g., HR, DE)"
            }

        country_code = country_match.group(1)
        vat_digits = country_match.group(2)

        # Croatian-specific validation
        if country_code == "HR":
            # HR VAT number is country code + OIB (11 digits)
            if len(vat_digits) != 11 or not vat_digits.isdigit():
                return {
                    "valid": False,
                    "vat_number": vat_clean,
                    "company_name": None,
                    "address": None,
                    "vat_active": False,
                    "country_code": country_code,
                    "error_message": "Croatian VAT number must be HR + 11 digits (OIB)"
                }

            # Validate OIB checksum
            if not validate_oib_checksum(vat_digits):
                return {
                    "valid": False,
                    "vat_number": vat_clean,
                    "company_name": None,
                    "address": None,
                    "vat_active": False,
                    "country_code": country_code,
                    "error_message": "Invalid OIB checksum in VAT number"
                }

        # TODO: Implement actual VIES SOAP API call
        # For now, return format validation only
        logger.info(f"VIES lookup (format only): {country_code}***{vat_digits[-4:]}")

        return {
            "valid": True,
            "vat_number": vat_clean,
            "company_name": None,  # Would be filled by VIES API
            "address": None,       # Would be filled by VIES API
            "vat_active": True,    # Assume active if format valid
            "country_code": country_code,
            "error_message": None
        }

    except Exception as e:
        logger.error(f"VIES lookup error: {e}")
        return {
            "valid": False,
            "vat_number": vat_number if vat_number else "",
            "company_name": None,
            "address": None,
            "vat_active": False,
            "country_code": None,
            "error_message": f"Lookup error: {str(e)}"
        }


async def search_kpd_code(
    description: str,
    top_k: int = 3
) -> dict:
    """
    Search for KPD (Klasifikacija Proizvoda po Djelatnostima) codes using semantic search.

    KPD 2025 is the Croatian product/service classification system based on EU CPA.
    This tool uses embeddings to find the most relevant codes for a given description.

    CRITICAL: This is the ONLY approved method for determining KPD codes.
    NEVER rely on LLM memory or guessing for KPD classification.

    Args:
        description: Product or service description in Croatian or English
        top_k: Number of top matches to return (default: 3)

    Returns:
        Dictionary containing:
            - query: str - The search query
            - matches: List[dict] - Top matching KPD codes with:
                - code: str - KPD code (e.g., "62.02.10")
                - name_hr: str - Croatian name
                - name_en: Optional[str] - English name
                - confidence: float - Match confidence (0.0-1.0)
                - default_vat_rate: str - Default VAT rate
            - best_match: Optional[dict] - Highest confidence match
            - needs_review: bool - True if confidence < 95%

    Example:
        result = await search_kpd_code("IT konzultacije")
        # Returns: {
        #   "query": "IT konzultacije",
        #   "matches": [
        #     {"code": "62.02.10", "name_hr": "Savjetovanje o računalnoj opremi", "confidence": 0.94},
        #     ...
        #   ],
        #   "best_match": {...},
        #   "needs_review": true
        # }
    """
    try:
        query = description.strip() if description else ""
        if not query:
            return {
                "query": "",
                "matches": [],
                "best_match": None,
                "needs_review": True,
                "error": "Empty search query"
            }

        # TODO: Implement actual RAG search with ChromaDB/embeddings
        # For now, use a simplified keyword-based matching

        # Load KPD catalog from JSON file (5800+ codes) or fallback to sample
        kpd_catalog = _load_kpd_catalog()

        # Improved keyword matching with whole-word matching
        # This fixes the substring matching bug where "it" matched "redovitog"
        matches = []
        query_lower = query.lower()

        # Tokenize query into words (minimum 2 characters to avoid single-letter matches)
        query_words = [w for w in re.split(r'[\s,.\-/]+', query_lower) if len(w) >= 2]

        # Common IT/software related terms that should boost IT codes
        it_keywords = {'it', 'software', 'softver', 'aplikacija', 'aplikacije', 'razvoj',
                       'razvoja', 'programiranje', 'web', 'internet', 'ai', 'agent',
                       'sustav', 'sustava', 'sistem', 'dizajn', 'dizajna', 'konzultacije',
                       'konzultacija', 'savjetovanje', 'računalo', 'računala', 'computer',
                       'computing', 'digital', 'digitalni', 'mrež', 'network', 'data',
                       'podaci', 'podataka', 'baza', 'database', 'cloud', 'hosting'}

        for code, data in kpd_catalog.items():
            score = 0.0
            name_hr_lower = data["name_hr"].lower()
            name_en_lower = data.get("name_en", "").lower()

            # Tokenize names into words
            keywords_hr = set(re.split(r'[\s,.\-/()]+', name_hr_lower))
            keywords_en = set(re.split(r'[\s,.\-/()]+', name_en_lower))

            matched_words = 0
            total_words = len(query_words)

            for word in query_words:
                # WHOLE-WORD matching only (not substring!)
                if word in keywords_hr:
                    score += 0.4
                    matched_words += 1
                elif word in keywords_en:
                    score += 0.3
                    matched_words += 1
                else:
                    # Check for partial matches only if word is significant (>3 chars)
                    if len(word) > 3:
                        for kw in keywords_hr:
                            if len(kw) > 3 and (word.startswith(kw[:4]) or kw.startswith(word[:4])):
                                score += 0.15
                                matched_words += 0.5
                                break
                        else:
                            for kw in keywords_en:
                                if len(kw) > 3 and (word.startswith(kw[:4]) or kw.startswith(word[:4])):
                                    score += 0.1
                                    matched_words += 0.5
                                    break

            # Boost IT-related codes when query contains IT keywords
            query_has_it_keywords = any(w in it_keywords for w in query_words)
            code_is_it = code.startswith(('62.', '63.'))  # IT/software codes start with 62 or 63

            if query_has_it_keywords and code_is_it:
                score += 0.3  # Boost IT codes for IT-related queries

            # Penalize non-IT codes when query is clearly about IT
            if query_has_it_keywords and not code_is_it:
                score *= 0.5  # Reduce score for non-IT codes

            # Calculate confidence as ratio of matched words
            if total_words > 0 and matched_words > 0:
                word_coverage = matched_words / total_words
                # Combine score with word coverage for final confidence
                confidence = min(score * word_coverage, 0.99)
            else:
                confidence = 0.0

            if confidence > 0.1:  # Only include matches with meaningful confidence
                matches.append({
                    "code": code,
                    "name_hr": data["name_hr"],
                    "name_en": data.get("name_en"),
                    "confidence": round(confidence, 2),
                    "parent_code": data.get("parent"),
                    "default_vat_rate": data.get("vat_rate", "25")
                })

        # Sort by confidence and take top_k
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        matches = matches[:top_k]

        # Determine best match and review status
        best_match = matches[0] if matches else None
        needs_review = best_match is None or best_match["confidence"] < 0.95
        low_confidence = best_match is not None and best_match["confidence"] < 0.5

        logger.info(
            f"KPD search for '{query}': "
            f"found {len(matches)} matches, "
            f"best={best_match['code'] if best_match else 'none'}, "
            f"confidence={best_match['confidence'] if best_match else 0:.2f}"
        )

        result = {
            "query": query,
            "matches": matches,
            "best_match": best_match,
            "needs_review": needs_review,
            "user_confirmation_required": low_confidence
        }

        # Add strong warning for low confidence - this MUST trigger user confirmation
        if low_confidence:
            match_list = "\n".join([
                f"  {i+1}. {m['code']} - {m['name_hr']} (confidence: {m['confidence']})"
                for i, m in enumerate(matches)
            ])
            result["low_confidence_warning"] = (
                f"STOP: Low confidence ({best_match['confidence']}) for KPD search '{query}'. "
                f"You MUST present these options to the user and ask them to confirm:\n"
                f"{match_list}\n"
                f"DO NOT proceed without user confirmation of the KPD code."
            )

        return result

    except Exception as e:
        logger.error(f"KPD search error: {e}")
        return {
            "query": description if description else "",
            "matches": [],
            "best_match": None,
            "needs_review": True,
            "error": f"Search error: {str(e)}"
        }


async def validate_kpd_code(
    code: str,
    description: Optional[str] = None
) -> dict:
    """
    Validate a user-provided KPD code against the official catalog.

    CRITICAL: Use this function when the user EXPLICITLY provides a KPD code.
    This bypasses the search algorithm and directly validates the code exists.

    When the user says "KPD kod 62.10.11" or provides a specific code,
    use this function instead of search_kpd_code.

    Args:
        code: The KPD code to validate (e.g., "62.10.11")
        description: Optional description for logging purposes

    Returns:
        Dictionary containing:
            - valid: bool - Whether the code exists in the catalog
            - code: str - The validated code
            - name_hr: str - Croatian name if found
            - name_en: Optional[str] - English name if found
            - default_vat_rate: str - Default VAT rate
            - error: Optional[str] - Error message if invalid

    Example:
        result = await validate_kpd_code("62.10.11", "IT usluge")
        # Returns: {
        #   "valid": true,
        #   "code": "62.10.11",
        #   "name_hr": "Usluge IT dizajna i razvoja aplikacija",
        #   "default_vat_rate": "25"
        # }
    """
    try:
        # Normalize the code (remove spaces, convert to uppercase for consistency)
        normalized_code = code.strip() if code else ""

        if not normalized_code:
            return {
                "valid": False,
                "code": "",
                "error": "Empty KPD code provided"
            }

        # Load catalog
        kpd_catalog = _load_kpd_catalog()

        # Direct lookup - exact match
        if normalized_code in kpd_catalog:
            entry = kpd_catalog[normalized_code]
            logger.info(f"KPD code validated: {normalized_code} = {entry.get('name_hr', 'Unknown')}")

            return {
                "valid": True,
                "code": normalized_code,
                "name_hr": entry.get("name_hr", ""),
                "name_en": entry.get("name_en"),
                "parent_code": entry.get("parent"),
                "default_vat_rate": entry.get("vat_rate", "25"),
                "description": description  # Keep user's description
            }

        # Try common variations (with/without dots, spaces)
        variations = [
            normalized_code.replace(".", ""),  # No dots
            normalized_code.replace(" ", ""),  # No spaces
            ".".join([normalized_code[i:i+2] for i in range(0, len(normalized_code.replace(".", "")), 2) if i+2 <= len(normalized_code.replace(".", ""))])  # Add dots every 2 chars
        ]

        for variant in variations:
            if variant in kpd_catalog:
                entry = kpd_catalog[variant]
                logger.info(f"KPD code validated (variant): {variant} = {entry.get('name_hr', 'Unknown')}")

                return {
                    "valid": True,
                    "code": variant,
                    "name_hr": entry.get("name_hr", ""),
                    "name_en": entry.get("name_en"),
                    "parent_code": entry.get("parent"),
                    "default_vat_rate": entry.get("vat_rate", "25"),
                    "description": description
                }

        # Code not found
        logger.warning(f"KPD code not found in catalog: {normalized_code}")

        return {
            "valid": False,
            "code": normalized_code,
            "error": f"KPD code '{normalized_code}' not found in catalog. Please verify the code or use search_kpd_code to find the correct classification."
        }

    except Exception as e:
        logger.error(f"KPD validation error: {e}")
        return {
            "valid": False,
            "code": code if code else "",
            "error": f"Validation error: {str(e)}"
        }


def _load_kpd_catalog() -> dict:
    """
    Load KPD 2025 catalog from JSON file.

    Returns complete KPD catalog with 5800+ codes loaded from
    data/kpd_2025/kpd_catalog.json (built from KPD_2025_struktura.xlsx)

    Falls back to minimal sample if file not found.
    """
    import json
    from pathlib import Path

    catalog_path = Path(__file__).parent.parent.parent / "data" / "kpd_2025" / "kpd_catalog.json"

    if catalog_path.exists():
        try:
            with open(catalog_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
                logger.info(f"Loaded KPD catalog: {len(catalog)} codes from {catalog_path}")
                return catalog
        except Exception as e:
            logger.warning(f"Failed to load KPD catalog from {catalog_path}: {e}")
            logger.warning("Falling back to minimal sample catalog")
    else:
        logger.warning(f"KPD catalog not found at {catalog_path}")
        logger.warning("Run: python build_kpd_catalog.py to generate it")
        logger.warning("Falling back to minimal sample catalog")

    # Minimal fallback catalog with REAL codes from KPD 2025
    return {
        "62.10.11": {
            "name_hr": "Usluge IT dizajna i razvoja aplikacija",
            "name_en": "IT design and application development services",
            "parent": "62.10.1",
            "vat_rate": "25",
            "code": "62.10.11"
        },
        "62.10.12": {
            "name_hr": "Usluge IT dizajna i razvoja mreža i sustava",
            "name_en": "IT design and network/system development services",
            "parent": "62.10.1",
            "vat_rate": "25",
            "code": "62.10.12"
        },
        "62.10.22": {
            "name_hr": "Ostali originalni softver",
            "name_en": "Other original software",
            "parent": "62.10.2",
            "vat_rate": "25",
            "code": "62.10.22"
        },
        "62.20.20": {
            "name_hr": "Usluge savjetovanja o sustavima i softveru",
            "name_en": "Systems and software consultancy services",
            "parent": "62.20.2",
            "vat_rate": "25",
            "code": "62.20.20"
        },
        "62.20.50": {
            "name_hr": "Usluge savjetovanja o kibernetičkoj sigurnosti",
            "name_en": "Cybersecurity consultancy services",
            "parent": "62.20.5",
            "vat_rate": "25",
            "code": "62.20.50"
        },
        "63.11.11": {
            "name_hr": "Usluge hostinga i pružanja aplikacijske infrastrukture",
            "name_en": "Web hosting services",
            "parent": "63.11",
            "vat_rate": "25"
        },
        "70.22.11": {
            "name_hr": "Savjetovanje u vezi s poslovanjem i upravljanjem",
            "name_en": "Business consulting services",
            "parent": "70.22",
            "vat_rate": "25"
        },
        "70.22.12": {
            "name_hr": "Savjetovanje u vezi s financijskim upravljanjem",
            "name_en": "Financial management consulting",
            "parent": "70.22",
            "vat_rate": "25"
        },
        "73.11.11": {
            "name_hr": "Usluge reklamnih agencija",
            "name_en": "Advertising agency services",
            "parent": "73.11",
            "vat_rate": "25"
        },
        "74.10.11": {
            "name_hr": "Usluge industrijskog dizajna",
            "name_en": "Industrial design services",
            "parent": "74.10",
            "vat_rate": "25"
        },
        "74.10.12": {
            "name_hr": "Usluge grafičkog dizajna",
            "name_en": "Graphic design services",
            "parent": "74.10",
            "vat_rate": "25"
        },
        "74.20.11": {
            "name_hr": "Usluge fotografiranja",
            "name_en": "Photography services",
            "parent": "74.20",
            "vat_rate": "25"
        },
        "47.00.01": {
            "name_hr": "Maloprodaja prehrambenih proizvoda",
            "name_en": "Retail sale of food products",
            "parent": "47.00",
            "vat_rate": "25"
        },
        "56.10.11": {
            "name_hr": "Usluge restorana",
            "name_en": "Restaurant services",
            "parent": "56.10",
            "vat_rate": "13"
        },
        "49.32.11": {
            "name_hr": "Usluge taksi prijevoza",
            "name_en": "Taxi services",
            "parent": "49.32",
            "vat_rate": "13"
        },
        "55.10.10": {
            "name_hr": "Hotelske i slične usluge smještaja",
            "name_en": "Hotel accommodation services",
            "parent": "55.10",
            "vat_rate": "13"
        },
        "58.11.11": {
            "name_hr": "Usluge izdavanja knjiga",
            "name_en": "Book publishing services",
            "parent": "58.11",
            "vat_rate": "5"
        },
        "58.13.10": {
            "name_hr": "Usluge izdavanja novina",
            "name_en": "Newspaper publishing services",
            "parent": "58.13",
            "vat_rate": "5"
        },
    }


async def calculate_tax(items: List[dict]) -> dict:
    """
    Calculate VAT/tax breakdown with Decimal precision.

    CRITICAL: This is the ONLY approved method for tax calculations.
    NEVER allow LLM to perform arithmetic on monetary values.

    Uses Croatian VAT rates:
    - 25%: Standard rate (most goods and services)
    - 13%: Reduced rate (food service, accommodation, transport)
    - 5%: Super-reduced rate (bread, milk, books, newspapers)
    - 0%: Zero rate (exports, certain exempt services)

    Args:
        items: List of items, each containing:
            - net_amount: Decimal or str/float (will be converted)
            - vat_rate: "25", "13", "5", or "0"
            - description: Optional description

    Returns:
        Dictionary containing:
            - subtotals: List of tax subtotals per rate
            - total_net: Total before tax
            - total_tax: Total tax amount
            - total_gross: Total including tax
            - currency: Currency code (always EUR)

    Example:
        result = await calculate_tax([
            {"net_amount": "1000.00", "vat_rate": "25"},
            {"net_amount": "500.00", "vat_rate": "13"}
        ])
        # Returns: {
        #   "subtotals": [
        #     {"vat_rate": "25", "taxable_amount": "1000.00", "tax_amount": "250.00"},
        #     {"vat_rate": "13", "taxable_amount": "500.00", "tax_amount": "65.00"}
        #   ],
        #   "total_net": "1500.00",
        #   "total_tax": "315.00",
        #   "total_gross": "1815.00"
        # }
    """
    try:
        if not items:
            return {
                "success": False,
                "subtotals": [],
                "pdv_breakdown": [],
                "total_net": "0.00",
                "total_tax": "0.00",
                "total_gross": "0.00",
                "currency": "EUR",
                "error": "No items provided"
            }

        # Group by VAT rate
        rate_totals: Dict[str, Decimal] = {}

        for item in items:
            # Parse net amount to Decimal
            net_str = str(item.get("net_amount", 0))
            net_amount = Decimal(net_str).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

            # Get VAT rate
            vat_rate = str(item.get("vat_rate", "25"))
            if vat_rate not in ["25", "13", "5", "0"]:
                logger.warning(f"Unknown VAT rate {vat_rate}, defaulting to 25%")
                vat_rate = "25"

            # Accumulate by rate
            if vat_rate not in rate_totals:
                rate_totals[vat_rate] = Decimal('0')
            rate_totals[vat_rate] += net_amount

        # Calculate subtotals
        subtotals = []
        total_net = Decimal('0')
        total_tax = Decimal('0')

        for rate, taxable in sorted(rate_totals.items(), reverse=True):
            rate_decimal = Decimal(rate) / Decimal('100')
            tax = (taxable * rate_decimal).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

            subtotals.append({
                "vat_rate": rate,
                "taxable_amount": str(taxable),
                "tax_amount": str(tax)
            })

            total_net += taxable
            total_tax += tax

        total_gross = total_net + total_tax

        # Convert subtotals to pdv_breakdown format for FINA
        pdv_breakdown = []
        for st in subtotals:
            pdv_breakdown.append({
                "stopa": f"{st['vat_rate']}.00",
                "osnovica": st['taxable_amount'],
                "iznos": st['tax_amount']
            })

        result = {
            "success": True,
            "subtotals": subtotals,
            "pdv_breakdown": pdv_breakdown,  # FINA format
            "total_net": str(total_net),
            "total_tax": str(total_tax),
            "total_gross": str(total_gross),
            "currency": "EUR"
        }

        logger.info(
            f"Tax calculation: net={total_net}, tax={total_tax}, gross={total_gross}"
        )

        return result

    except Exception as e:
        logger.error(f"Tax calculation error: {e}")
        return {
            "success": False,
            "subtotals": [],
            "pdv_breakdown": [],
            "total_net": "0.00",
            "total_tax": "0.00",
            "total_gross": "0.00",
            "currency": "EUR",
            "error": f"Calculation error: {str(e)}"
        }


async def normalize_unit(unit: str) -> dict:
    """
    Convert unit description to UN/ECE Recommendation 20 code.

    UN/ECE Rec 20 defines standard codes for units of measure used in
    international trade documentation including UBL invoices.

    Args:
        unit: Unit description in Croatian or English (e.g., "komad", "sat", "kg")

    Returns:
        Dictionary containing:
            - input: str - Original input
            - code: str - UN/ECE Rec 20 code
            - name: str - Standard English name

    Example:
        result = await normalize_unit("sat")
        # Returns: {"input": "sat", "code": "HUR", "name": "Hour"}
    """
    try:
        unit_clean = unit.strip().lower() if unit else ""

        # Map of codes to names
        code_names = {
            "H87": "Piece",
            "HUR": "Hour",
            "DAY": "Day",
            "MON": "Month",
            "ANN": "Year",
            "KGM": "Kilogram",
            "GRM": "Gram",
            "TNE": "Tonne",
            "MTR": "Metre",
            "MTK": "Square metre",
            "MTQ": "Cubic metre",
            "LTR": "Litre",
            "KWH": "Kilowatt hour",
            "PK": "Package",
            "BX": "Box",
        }

        code = normalize_unit_code(unit_clean)
        name = code_names.get(code, "Unknown")

        return {
            "input": unit if unit else "",
            "code": code,
            "name": name
        }

    except Exception as e:
        logger.error(f"Unit normalization error: {e}")
        return {
            "input": unit if unit else "",
            "code": "H87",
            "name": "Piece",
            "error": str(e)
        }


async def check_invoice_number_format(invoice_number: str) -> dict:
    """
    Validate Croatian invoice number format.

    Croatian fiscalization requires invoice numbers in format: XXX/PP/NU
    - XXX: Sequential number (resets yearly)
    - PP: Business premises code (oznaka poslovnog prostora)
    - NU: Cash register number (oznaka naplatnog uredaja)

    Args:
        invoice_number: Invoice number to validate

    Returns:
        Dictionary containing:
            - valid: bool - Format is correct
            - invoice_number: str - The number checked
            - sequential: Optional[str] - Sequential part
            - premises: Optional[str] - Premises code
            - register: Optional[str] - Register number
            - error_message: Optional[str] - Error if invalid

    Example:
        result = await check_invoice_number_format("001/URED/1")
        # Returns: {"valid": true, "sequential": "001", "premises": "URED", "register": "1"}
    """
    try:
        num = invoice_number.strip() if invoice_number else ""

        # Parse format XXX/PP/NU
        match = re.match(r'^(\d+)/([^/]+)/(\d+)$', num)

        if not match:
            return {
                "valid": False,
                "invoice_number": num,
                "sequential": None,
                "premises": None,
                "register": None,
                "error_message": "Format must be: XXX/PP/NU (e.g., 001/URED/1)"
            }

        sequential = match.group(1)
        premises = match.group(2)
        register = match.group(3)

        return {
            "valid": True,
            "invoice_number": num,
            "sequential": sequential,
            "premises": premises,
            "register": register,
            "error_message": None
        }

    except Exception as e:
        logger.error(f"Invoice number validation error: {e}")
        return {
            "valid": False,
            "invoice_number": invoice_number if invoice_number else "",
            "sequential": None,
            "premises": None,
            "register": None,
            "error_message": str(e)
        }


async def verify_tax_calculation(
    items: List[dict],
    claimed_total_net: str,
    claimed_total_tax: str,
    claimed_total_gross: str
) -> dict:
    """
    Independently verify tax calculations by recalculating and comparing.

    Used by Validator agent to ensure Pripremac's calculations are correct.
    Any discrepancy results in INVALID status.

    Args:
        items: List of line items with net_amount and vat_rate
        claimed_total_net: Claimed total net amount
        claimed_total_tax: Claimed total tax amount
        claimed_total_gross: Claimed total gross amount

    Returns:
        Dictionary containing:
            - valid: bool - All calculations match
            - discrepancies: List of mismatches found
            - recalculated: dict - Independently calculated values

    Example:
        result = await verify_tax_calculation(
            items=[{"net_amount": "1000.00", "vat_rate": "25"}],
            claimed_total_net="1000.00",
            claimed_total_tax="250.00",
            claimed_total_gross="1250.00"
        )
        # Returns: {"valid": true, "discrepancies": [], ...}
    """
    try:
        # Recalculate independently
        recalc = await calculate_tax(items)

        if "error" in recalc:
            return {
                "valid": False,
                "discrepancies": [f"Calculation error: {recalc['error']}"],
                "recalculated": recalc
            }

        discrepancies = []

        # Compare net
        if recalc["total_net"] != claimed_total_net:
            discrepancies.append({
                "field": "total_net",
                "expected": recalc["total_net"],
                "actual": claimed_total_net,
                "difference": str(
                    Decimal(recalc["total_net"]) - Decimal(claimed_total_net)
                )
            })

        # Compare tax
        if recalc["total_tax"] != claimed_total_tax:
            discrepancies.append({
                "field": "total_tax",
                "expected": recalc["total_tax"],
                "actual": claimed_total_tax,
                "difference": str(
                    Decimal(recalc["total_tax"]) - Decimal(claimed_total_tax)
                )
            })

        # Compare gross
        if recalc["total_gross"] != claimed_total_gross:
            discrepancies.append({
                "field": "total_gross",
                "expected": recalc["total_gross"],
                "actual": claimed_total_gross,
                "difference": str(
                    Decimal(recalc["total_gross"]) - Decimal(claimed_total_gross)
                )
            })

        is_valid = len(discrepancies) == 0

        if not is_valid:
            logger.warning(f"Tax verification failed: {discrepancies}")
        else:
            logger.info("Tax verification passed")

        return {
            "valid": is_valid,
            "discrepancies": discrepancies,
            "recalculated": recalc
        }

    except Exception as e:
        logger.error(f"Tax verification error: {e}")
        return {
            "valid": False,
            "discrepancies": [f"Verification error: {str(e)}"],
            "recalculated": {}
        }


# ============================================================================
# XML CONSTRUCTION TOOLS (Phase 2 - IMPLEMENTED)
# ============================================================================

async def build_ubl_invoice(invoice_data: dict) -> dict:
    """
    Generate FINA RacunZahtjev XML for Croatian fiscalization.

    Creates a FINA-compliant RacunZahtjev XML document according to:
    - FINA CIS specification (http://www.apis-it.hr/fin/2012/types/f73)
    - Croatian fiscalization requirements

    CRITICAL: This is a deterministic tool. No LLM involvement in XML generation.
    IMPORTANT: ZKI must be calculated BEFORE calling this function!

    Args:
        invoice_data: Dictionary containing invoice data with keys:
            - invoice_number: str (format: XXX/PP/NU) - REQUIRED
            - zki: str - ZKI code (must call calculate_zki first!) - REQUIRED
            - issue_date: date or str (YYYY-MM-DD) - REQUIRED
            - issue_time: str (HH:MM:SS) - optional, defaults to "12:00:00"
            - supplier: dict with oib - REQUIRED
            - tax_breakdown: dict with subtotals, total_gross - REQUIRED
            - payment_means_code: str - optional ("10"=cash, "30"=transfer, "48"=card)
            - operator_oib: str - optional, defaults to supplier OIB
            - is_late_delivery: bool - optional, defaults to False
            - special_purpose: str - optional

    Returns:
        Dictionary containing:
            - success: bool
            - xml: str - Generated FINA XML string (UTF-8 with declaration)
            - error: Optional error message

    Example:
        # First calculate ZKI
        zki_result = await calculate_zki(...)

        # Then build XML with ZKI
        result = await build_ubl_invoice({
            "invoice_number": "001/DEMO/1",
            "zki": zki_result["zki"],
            "issue_date": "2026-01-29",
            "supplier": {"oib": "47034854402"},
            "tax_breakdown": {"total_gross": "1875.00", "subtotals": [...]}
        })
    """
    try:
        from tools.api_implementations.fina_xml_builder import build_racun_zahtjev
        from datetime import datetime

        # Extract ZKI (REQUIRED!)
        zki = invoice_data.get("zki")
        if not zki:
            return {
                "success": False,
                "xml": None,
                "error": "ZKI is required! Call calculate_zki first and include 'zki' in invoice_data."
            }

        # Parse invoice number (format: 001/DEMO/1)
        invoice_number = invoice_data.get("invoice_number", "")
        parts = invoice_number.split("/")
        if len(parts) != 3:
            return {
                "success": False,
                "xml": None,
                "error": f"Invalid invoice_number format: '{invoice_number}'. Expected: XXX/PP/NU (e.g., 001/DEMO/1)"
            }

        broj_racuna = parts[0]
        oznaka_pp = parts[1]
        oznaka_nu = parts[2]

        # Get supplier OIB
        supplier = invoice_data.get("supplier", {})
        oib = supplier.get("oib", "")
        if not oib:
            return {
                "success": False,
                "xml": None,
                "error": "Supplier OIB is required in invoice_data['supplier']['oib']"
            }

        # Parse datetime
        issue_date = invoice_data.get("issue_date", "")
        issue_time = invoice_data.get("issue_time", "12:00:00")

        if isinstance(issue_date, str):
            dt = datetime.fromisoformat(f"{issue_date}T{issue_time}")
        else:
            dt = issue_date  # Assume it's already datetime

        # VAT breakdown
        tax_breakdown = invoice_data.get("tax_breakdown", {})
        pdv = []
        for subtotal in tax_breakdown.get("subtotals", []):
            vat_rate = subtotal.get("vat_rate", "0")
            if float(vat_rate) > 0:
                pdv.append({
                    "stopa": str(vat_rate),
                    "osnovica": str(subtotal.get("taxable_amount", "0.00")),
                    "iznos": str(subtotal.get("tax_amount", "0.00"))
                })

        # Total amount
        total = str(tax_breakdown.get("total_gross", "0.00"))

        # Payment method mapping (UBL codes -> FINA codes)
        payment_code = invoice_data.get("payment_means_code", "30")
        nacin_placanja_map = {
            "10": "G",  # Gotovina (Cash)
            "30": "T",  # Transakcijski račun (Credit transfer)
            "48": "K",  # Kartica (Card payment)
        }
        nacin_placanja = nacin_placanja_map.get(str(payment_code), "O")  # Default: Ostalo

        # Operator OIB (default to supplier OIB if not provided)
        oib_operatera = invoice_data.get("operator_oib", oib)

        # Build FINA RacunZahtjev XML
        xml = build_racun_zahtjev(
            oib=oib,
            u_sustavu_pdv=True,  # Assume VAT registered
            datum_vrijeme=dt,
            oznaka_slijednosti="P",  # P = Paragon (real-time), N = Naknadna (late)
            broj_racuna=broj_racuna,
            oznaka_poslovnog_prostora=oznaka_pp,
            oznaka_naplatnog_uredaja=oznaka_nu,
            ukupan_iznos=total,
            nacin_placanja=nacin_placanja,
            oib_operatera=oib_operatera,
            zki=zki,
            pdv=pdv if pdv else None,
            naknadna_dostava=invoice_data.get("is_late_delivery", False),
            posebna_namjena=invoice_data.get("special_purpose", None)
        )

        logger.info(f"FINA RacunZahtjev XML generated: {len(xml)} bytes")

        return {
            "success": True,
            "xml": xml,
            "error": None
        }

    except Exception as e:
        logger.error(f"FINA XML generation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "xml": None,
            "error": f"XML generation failed: {str(e)}"
        }


async def validate_xsd(xml: str, schema_path: Optional[str] = None) -> dict:
    """
    Validate XML against EN 16931 + HR-FISK 2.0 XSD schemas.

    Performs two levels of validation:
    1. Well-formedness check (valid XML syntax)
    2. Schema validation against UBL 2.1 / EN 16931 XSD

    CRITICAL: This is the final validation gate before signing.
    Any error here MUST block the signing process.

    Args:
        xml: XML string to validate
        schema_path: Optional path to custom XSD schema file

    Returns:
        Dictionary containing:
            - valid: bool - True if all validations pass
            - errors: List of error dicts with line, column, message, element
            - schema_version: Version of schema used for validation
            - error_count: Number of errors found

    Example:
        result = await validate_xsd(xml_string)
        if not result["valid"]:
            for error in result["errors"]:
                print(f"Line {error['line']}: {error['message']}")
    """
    try:
        from tools.api_implementations.xml_validator import validate_xsd as _validate_xsd

        result = _validate_xsd(xml, schema_path)

        if result["valid"]:
            logger.info("XSD validation passed")
        else:
            logger.warning(f"XSD validation failed with {result['error_count']} errors")

        return result

    except Exception as e:
        logger.error(f"XSD validation error: {e}")
        return {
            "valid": False,
            "errors": [{"line": 0, "column": 0, "message": str(e), "element": None}],
            "schema_version": "unknown",
            "error_count": 1
        }


async def canonicalize_xml(xml: str, exclusive: bool = True, with_comments: bool = False) -> dict:
    """
    Apply C14N (XML Canonicalization) to XML document.

    Canonicalization ensures consistent byte representation of XML,
    which is REQUIRED before digital signing (XAdES-BES).

    Supports:
    - Exclusive XML Canonicalization 1.0 (exc-c14n) - default for XAdES
    - Canonical XML 1.0 (c14n)

    CRITICAL: Always canonicalize before signing to ensure
    signature verification works across different XML processors.

    Args:
        xml: XML string to canonicalize
        exclusive: Use exclusive canonicalization (default True for XAdES)
        with_comments: Include comments in output (default False)

    Returns:
        Dictionary containing:
            - success: bool
            - canonical_xml: str - Canonicalized XML
            - error: Optional error message
            - method: "exc-c14n" or "c14n"
            - with_comments: bool

    Example:
        result = await canonicalize_xml(xml_string)
        if result["success"]:
            canonical = result["canonical_xml"]
            # Now safe to sign
    """
    try:
        from tools.api_implementations.xml_validator import canonicalize_xml as _canonicalize

        result = _canonicalize(xml, exclusive=exclusive, with_comments=with_comments)

        if result["success"]:
            logger.info(f"XML canonicalized using {result['method']}")
        else:
            logger.error(f"Canonicalization failed: {result['error']}")

        return result

    except Exception as e:
        logger.error(f"Canonicalization error: {e}")
        return {
            "success": False,
            "canonical_xml": None,
            "error": f"Canonicalization failed: {str(e)}"
        }


# ============================================================================
# SIGNING TOOLS (Phase 3 - IMPLEMENTED)
# ============================================================================

# Certificate cache - stores loaded certificates in memory during session
_certificate_cache: Dict[str, Any] = {}


async def load_certificate(
    source: str,
    password: Optional[str] = None,
    source_type: str = "file",
    project_id: Optional[str] = None,
    cache_key: Optional[str] = None
) -> dict:
    """
    Load .p12 certificate from file or Google Secret Manager.

    Security: Certificate is loaded to memory only, never logged or written to disk.
    Certificates are cached in memory for the session duration.

    Args:
        source: File path or Secret Manager secret name
        password: Password for .p12 file (or password secret name if using Secret Manager)
        source_type: "file" or "secret_manager"
        project_id: GCP project ID (required for Secret Manager)
        cache_key: Optional key for caching certificate (defaults to source)

    Returns:
        Dictionary containing:
            - success: bool
            - certificate_loaded: bool
            - certificate_info: dict with serial, issuer, subject, validity
            - expires_at: Certificate expiry date
            - is_valid: Whether certificate is currently valid
            - cache_key: Key to reference this certificate in signing
            - error: Optional error message

    Example:
        # From file
        result = await load_certificate(
            source="/path/to/cert.p12",
            password="secret123",
            source_type="file"
        )

        # From Secret Manager
        result = await load_certificate(
            source="fina-cert-prod",
            password="fina-cert-password",  # password secret name
            source_type="secret_manager",
            project_id="my-gcp-project"
        )
    """
    try:
        from tools.api_implementations.xades_signer import (
            load_certificate as _load_cert,
            CertificateInfo
        )

        # Determine cache key
        key = cache_key or source

        # Check cache first
        if key in _certificate_cache:
            cert_info = _certificate_cache[key]
            logger.info(f"Using cached certificate: {key}")
            return {
                "success": True,
                "certificate_loaded": True,
                "certificate_info": cert_info.to_dict(),
                "expires_at": cert_info.valid_to.isoformat() if cert_info.valid_to else None,
                "is_valid": cert_info.is_valid(),
                "cache_key": key,
                "error": None
            }

        # Load certificate
        result = _load_cert(
            source=source,
            password=password or "",
            source_type=source_type,
            project_id=project_id
        )

        if not result["success"]:
            return {
                "success": False,
                "certificate_loaded": False,
                "certificate_info": None,
                "expires_at": None,
                "is_valid": False,
                "cache_key": None,
                "error": result.get("error", "Unknown error")
            }

        # Cache the certificate
        cert_handle = result["cert_handle"]
        _certificate_cache[key] = cert_handle

        logger.info(f"Certificate loaded and cached: {key}")

        return {
            "success": True,
            "certificate_loaded": True,
            "certificate_info": result["certificate_info"],
            "expires_at": result["certificate_info"].get("valid_to"),
            "is_valid": result["certificate_info"].get("is_valid", False),
            "cache_key": key,
            "error": None
        }

    except ImportError as e:
        logger.error(f"Missing cryptography library: {e}")
        return {
            "success": False,
            "certificate_loaded": False,
            "certificate_info": None,
            "expires_at": None,
            "is_valid": False,
            "cache_key": None,
            "error": f"Missing required library: {e}. Install with: pip install cryptography pyOpenSSL"
        }
    except Exception as e:
        logger.error(f"Certificate loading error: {e}")
        return {
            "success": False,
            "certificate_loaded": False,
            "certificate_info": None,
            "expires_at": None,
            "is_valid": False,
            "cache_key": None,
            "error": f"Certificate loading failed: {str(e)}"
        }


async def sign_xades(
    xml: str,
    cert_cache_key: str,
    signature_id: Optional[str] = None
) -> dict:
    """
    Apply XAdES-BES digital signature to XML.

    Uses RSA-SHA256 algorithm as required by Croatian fiscalization.
    Certificate must be pre-loaded using load_certificate.

    CRITICAL: This is a deterministic tool. Signature is created using
    standard XAdES-BES format with:
    - Exclusive XML Canonicalization 1.0
    - SHA-256 digest
    - RSA-SHA256 signature
    - SigningCertificate signed property

    Args:
        xml: XML document to sign (will be canonicalized internally)
        cert_cache_key: Cache key from load_certificate result
        signature_id: Optional custom signature ID

    Returns:
        Dictionary containing:
            - success: bool
            - signed_xml: str - XML with embedded ds:Signature element
            - signature_id: str - ID of the signature element
            - signing_time: str - ISO timestamp of signing
            - certificate_subject: str - Subject of signing certificate
            - error: Optional error message

    Example:
        # First load certificate
        cert = await load_certificate(source="/path/to/cert.p12", password="secret")

        # Then sign
        result = await sign_xades(
            xml=invoice_xml,
            cert_cache_key=cert["cache_key"]
        )
        signed_xml = result["signed_xml"]
    """
    try:
        from tools.api_implementations.xades_signer import sign_xades_bes

        # Get certificate from cache
        if cert_cache_key not in _certificate_cache:
            return {
                "success": False,
                "signed_xml": None,
                "signature_id": None,
                "signing_time": None,
                "certificate_subject": None,
                "error": f"Certificate not found in cache. Load it first with load_certificate(). Key: {cert_cache_key}"
            }

        cert_info = _certificate_cache[cert_cache_key]

        # Check certificate validity
        if not cert_info.is_valid():
            logger.warning(f"Certificate {cert_cache_key} is expired or not yet valid")
            return {
                "success": False,
                "signed_xml": None,
                "signature_id": None,
                "signing_time": None,
                "certificate_subject": cert_info.subject,
                "error": "Certificate is expired or not yet valid"
            }

        # Sign the document
        result = sign_xades_bes(xml, cert_info, signature_id)

        if result["success"]:
            logger.info(f"XML signed successfully with certificate: {cert_info.subject}")
        else:
            logger.error(f"XAdES signing failed: {result.get('error')}")

        return result

    except ImportError as e:
        logger.error(f"Missing signing library: {e}")
        return {
            "success": False,
            "signed_xml": None,
            "signature_id": None,
            "signing_time": None,
            "certificate_subject": None,
            "error": f"Missing required library: {e}. Install with: pip install cryptography lxml"
        }
    except Exception as e:
        logger.error(f"XAdES signing error: {e}")
        return {
            "success": False,
            "signed_xml": None,
            "signature_id": None,
            "signing_time": None,
            "certificate_subject": None,
            "error": f"Signing failed: {str(e)}"
        }


async def calculate_zki(
    oib: str,
    invoice_datetime: str,
    invoice_number: str,
    business_unit: str,
    device_number: str,
    total_amount: str,
    cert_cache_key: str
) -> dict:
    """
    Calculate ZKI (Zaštitni Kod Izdavatelja - Protective Code of Issuer).

    ZKI is a mandatory security code for Croatian fiscalization that proves
    the invoice was created by the registered taxpayer.

    Calculation steps:
    1. Concatenate: OIB + DateTime + InvoiceNumber + BusinessUnit + DeviceNumber + TotalAmount
    2. Sign with RSA-SHA1 using issuer's private key
    3. MD5 hash the signature
    4. Format as 32 hex characters with dashes every 8 chars

    CRITICAL: This is a deterministic tool. ZKI MUST be calculated exactly
    according to FINA specification. Any deviation will cause rejection.

    Args:
        oib: Issuer's OIB (11 digits)
        invoice_datetime: Invoice date and time (ISO format or dd.mm.yyyy HH:MM:SS)
        invoice_number: Invoice sequential number
        business_unit: Business unit identifier (oznaka poslovnog prostora)
        device_number: Cash register device number (oznaka naplatnog uređaja)
        total_amount: Total invoice amount (will be formatted to 2 decimals)
        cert_cache_key: Cache key from load_certificate

    Returns:
        Dictionary containing:
            - success: bool
            - zki: str - ZKI in format XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
            - error: Optional error message

    Example:
        result = await calculate_zki(
            oib="12345678903",
            invoice_datetime="2026-01-15T10:30:00",
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount="1250.00",
            cert_cache_key="my-cert"
        )
        # Returns: {"success": true, "zki": "A1B2C3D4-E5F6G7H8-I9J0K1L2-M3N4O5P6"}
    """
    try:
        from tools.api_implementations.xades_signer import calculate_zki_code

        # Get certificate from cache
        if cert_cache_key not in _certificate_cache:
            return {
                "success": False,
                "zki": None,
                "error": f"Certificate not found in cache. Load it first with load_certificate(). Key: {cert_cache_key}"
            }

        cert_info = _certificate_cache[cert_cache_key]

        result = calculate_zki_code(
            oib=oib,
            invoice_datetime=invoice_datetime,
            invoice_number=invoice_number,
            business_unit=business_unit,
            device_number=device_number,
            total_amount=total_amount,
            cert_handle=cert_info
        )

        if result["success"]:
            logger.info(f"ZKI calculated: {result['zki']}")
        else:
            logger.error(f"ZKI calculation failed: {result.get('error')}")

        return result

    except ImportError as e:
        logger.error(f"Missing cryptography library: {e}")
        return {
            "success": False,
            "zki": None,
            "error": f"Missing required library: {e}. Install with: pip install cryptography"
        }
    except Exception as e:
        logger.error(f"ZKI calculation error: {e}")
        return {
            "success": False,
            "zki": None,
            "error": f"ZKI calculation failed: {str(e)}"
        }


async def verify_xml_signature(xml: str) -> dict:
    """
    Verify XAdES signature in signed XML document.

    Used for validating received signed documents or verifying own signatures.

    Args:
        xml: Signed XML document

    Returns:
        Dictionary containing:
            - valid: bool - Signature is present and well-formed
            - signer: str - Certificate subject (signer identity)
            - signing_time: str - When document was signed
            - error: Optional error message
            - note: Additional information about verification

    Example:
        result = await verify_xml_signature(signed_xml)
        if result["valid"]:
            print(f"Signed by: {result['signer']} at {result['signing_time']}")
    """
    try:
        from tools.api_implementations.xades_signer import verify_signature

        result = verify_signature(xml)

        if result["valid"]:
            logger.info(f"Signature verified: {result['signer']}")
        else:
            logger.warning(f"Signature verification failed: {result.get('error')}")

        return result

    except ImportError as e:
        logger.error(f"Missing library: {e}")
        return {
            "valid": False,
            "signer": None,
            "signing_time": None,
            "error": f"Missing required library: {e}"
        }
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return {
            "valid": False,
            "signer": None,
            "signing_time": None,
            "error": f"Verification failed: {str(e)}"
        }


# ============================================================================
# COMMUNICATION TOOLS (Phase 4 - IMPLEMENTED)
# ============================================================================

async def send_fina_soap(
    signed_xml: str,
    environment: str = "sandbox",
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    ca_cert_path: Optional[str] = None
) -> dict:
    """
    Send signed invoice to FINA via SOAP.

    Includes circuit breaker pattern and exponential retry.

    CRITICAL: This is the final step in fiscalization. The signed XML
    is sent to FINA CIS and a JIR (Jedinstveni Identifikator Računa)
    is returned on success.

    Endpoints:
        - Sandbox: https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest
        - Production: https://cis.porezna-uprava.hr:8449/FiskalizacijaService

    Args:
        signed_xml: XAdES signed XML document
        environment: "sandbox" or "production"
        cert_path: Path to client certificate for mTLS
        key_path: Path to private key for mTLS
        ca_cert_path: Path to CA certificate for SSL verification (e.g., demo2014_root_ca.cer)

    Returns:
        Dictionary containing:
            - success: bool
            - jir: Optional JIR (Jedinstveni Identifikator Računa)
            - zki: ZKI from response
            - message_id: Request tracking ID
            - timestamp: Response timestamp
            - errors: List of FINA error codes with messages
            - raw_response: str - Raw SOAP response
            - circuit_breaker_status: Current circuit breaker state

    Example:
        result = await send_fina_soap(
            signed_xml=signed_invoice,
            environment="sandbox",
            ca_cert_path="demo2014_root_ca.cer"
        )
        if result["success"]:
            jir = result["jir"]  # e.g., "abc123-def456-ghi789"
    """
    try:
        from tools.api_implementations.fina_soap_client import send_to_fina

        result = send_to_fina(
            signed_xml=signed_xml,
            environment=environment,
            cert_path=cert_path,
            key_path=key_path,
            ca_cert_path=ca_cert_path
        )

        if result["success"]:
            logger.info(f"FINA fiscalization successful, JIR: {result['jir']}")
        else:
            logger.warning(f"FINA fiscalization failed: {result.get('errors')}")

        return result

    except ImportError as e:
        logger.error(f"Missing SOAP library: {e}")
        return {
            "success": False,
            "jir": None,
            "zki": None,
            "message_id": None,
            "timestamp": None,
            "errors": [{"code": "IMPORT_ERROR", "message": f"Missing library: {e}"}],
            "raw_response": None,
            "circuit_breaker_status": None
        }
    except Exception as e:
        logger.error(f"FINA SOAP error: {e}")
        return {
            "success": False,
            "jir": None,
            "zki": None,
            "message_id": None,
            "timestamp": None,
            "errors": [{"code": "ERROR", "message": str(e)}],
            "raw_response": None,
            "circuit_breaker_status": None
        }


async def parse_fina_response(soap_response: str) -> dict:
    """
    Parse FINA SOAP response to extract JIR or error codes.

    Used for manual response parsing or re-processing stored responses.

    Args:
        soap_response: Raw SOAP response XML from FINA

    Returns:
        Dictionary containing:
            - success: bool - True if JIR present and no errors
            - jir: Optional JIR
            - zki: Optional ZKI
            - timestamp: Response timestamp
            - errors: List of error dicts with code and message

    Example:
        result = await parse_fina_response(raw_soap_xml)
        if result["success"]:
            print(f"JIR: {result['jir']}")
        else:
            for err in result["errors"]:
                print(f"Error {err['code']}: {err['message']}")
    """
    try:
        from tools.api_implementations.fina_soap_client import parse_fina_response as _parse

        result = _parse(soap_response)

        if result["success"]:
            logger.info(f"FINA response parsed, JIR: {result['jir']}")
        else:
            logger.warning(f"FINA response parsing: {result.get('errors')}")

        return result

    except ImportError as e:
        logger.error(f"Missing XML library: {e}")
        return {
            "success": False,
            "jir": None,
            "zki": None,
            "timestamp": None,
            "errors": [{"code": "IMPORT_ERROR", "message": f"Missing library: {e}"}]
        }
    except Exception as e:
        logger.error(f"FINA response parsing error: {e}")
        return {
            "success": False,
            "jir": None,
            "zki": None,
            "timestamp": None,
            "errors": [{"code": "PARSE_ERROR", "message": str(e)}]
        }


async def generate_qr_code(
    jir: str,
    zki: str,
    invoice_datetime: str,
    total_amount: str,
    oib: str
) -> dict:
    """
    Generate QR code for invoice verification.

    QR code contains URL to Porezna Uprava verification portal where
    customers can verify the invoice was properly fiscalized.

    URL format: https://porezna.gov.hr/provjera-racuna?jir=XXX&zki=YYY&...

    Args:
        jir: JIR from FINA response
        zki: ZKI code (will have dashes removed)
        invoice_datetime: Invoice date/time (ISO format)
        total_amount: Total invoice amount
        oib: Issuer's OIB

    Returns:
        Dictionary containing:
            - success: bool
            - qr_code_base64: str - Base64 encoded PNG image
            - verification_url: str - URL encoded in QR
            - error: Optional error message

    Example:
        result = await generate_qr_code(
            jir="abc123-def456",
            zki="A1B2C3D4-E5F6G7H8-I9J0K1L2-M3N4O5P6",
            invoice_datetime="2026-01-15T10:30:00",
            total_amount="1250.00",
            oib="12345678903"
        )
        # result["qr_code_base64"] contains PNG image data
    """
    try:
        from tools.api_implementations.fina_soap_client import generate_verification_qr

        result = generate_verification_qr(
            jir=jir,
            zki=zki,
            invoice_datetime=invoice_datetime,
            total_amount=total_amount,
            oib=oib
        )

        if result["success"]:
            logger.info(f"QR code generated for JIR: {jir}")
        else:
            logger.warning(f"QR code generation failed: {result.get('error')}")

        return result

    except ImportError as e:
        logger.error(f"Missing QR library: {e}")
        return {
            "success": False,
            "qr_code_base64": None,
            "verification_url": None,
            "error": f"Missing library: {e}. Install with: pip install qrcode[pil]"
        }
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        return {
            "success": False,
            "qr_code_base64": None,
            "verification_url": None,
            "error": str(e)
        }


async def get_circuit_breaker_status() -> dict:
    """
    Get current circuit breaker status for FINA communication.

    Circuit breaker prevents cascading failures by stopping requests
    to FINA when the service is failing.

    Returns:
        Dictionary containing:
            - state: "closed", "open", or "half_open"
            - failure_count: Number of consecutive failures
            - failure_threshold: Failures needed to open circuit
            - last_failure: ISO timestamp of last failure
            - recovery_timeout_seconds: Time before testing recovery

    Example:
        status = await get_circuit_breaker_status()
        if status["state"] == "open":
            print("FINA service unavailable, try later")
    """
    try:
        from tools.api_implementations.fina_soap_client import get_circuit_breaker_status as _get_status

        return _get_status()

    except ImportError:
        return {
            "state": "unknown",
            "failure_count": 0,
            "failure_threshold": 5,
            "last_failure": None,
            "recovery_timeout_seconds": 60
        }


# ============================================================================
# LEDGER AND QUEUE TOOLS (Phase 4 - IMPLEMENTED)
# ============================================================================

async def check_invoice_ledger(
    invoice_number: str,
    supplier_oib: str,
    use_firestore: bool = False
) -> dict:
    """
    Check if invoice already exists in ledger (idempotency check).

    CRITICAL: This MUST be called before any fiscalization attempt
    to prevent duplicate JIR requests to FINA.

    Args:
        invoice_number: Invoice number to check (format: XXX/PP/NU)
        supplier_oib: Supplier's OIB
        use_firestore: Use Firestore (True) or in-memory (False)

    Returns:
        Dictionary containing:
            - exists: bool - True if already fiscalized
            - jir: Optional existing JIR
            - zki: Optional ZKI
            - status: Current status (success, pending, retrying, expired)
            - timestamp: When originally fiscalized

    Example:
        # Always check before fiscalizing
        check = await check_invoice_ledger("001/URED/1", "12345678903")
        if check["exists"]:
            print(f"Already fiscalized with JIR: {check['jir']}")
            return check["jir"]  # Return existing JIR
    """
    try:
        from tools.api_implementations.fiskalizacija_ledger import check_invoice_ledger as _check

        result = _check(
            invoice_number=invoice_number,
            supplier_oib=supplier_oib,
            use_firestore=use_firestore
        )

        if result["exists"]:
            logger.info(f"Invoice {invoice_number} found in ledger, JIR: {result.get('jir')}")
        else:
            logger.debug(f"Invoice {invoice_number} not in ledger")

        return result

    except ImportError as e:
        logger.error(f"Missing ledger library: {e}")
        return {
            "exists": False,
            "jir": None,
            "zki": None,
            "status": None,
            "timestamp": None,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Ledger check error: {e}")
        return {
            "exists": False,
            "jir": None,
            "zki": None,
            "status": None,
            "timestamp": None,
            "error": str(e)
        }


async def save_invoice_ledger(
    invoice_number: str,
    supplier_oib: str,
    jir: str,
    zki: str,
    signed_xml: str,
    fina_response: str,
    total_amount: Optional[str] = None,
    use_firestore: bool = False
) -> dict:
    """
    Save successful fiscalization to ledger.

    Records the complete fiscalization for:
    - Idempotency (prevent duplicate requests)
    - Audit trail
    - Compliance (Croatian law requires 11-year retention)

    Args:
        invoice_number: Invoice number
        supplier_oib: Supplier's OIB
        jir: JIR from FINA
        zki: ZKI code
        signed_xml: Complete signed XML document
        fina_response: Raw FINA SOAP response
        total_amount: Invoice total amount
        use_firestore: Use Firestore (True) or in-memory (False)

    Returns:
        Dictionary containing:
            - success: bool
            - document_id: str - Storage document ID
            - error: Optional error message

    Example:
        result = await save_invoice_ledger(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            jir="abc123-def456",
            zki="A1B2C3D4-...",
            signed_xml=signed_xml,
            fina_response=raw_response,
            total_amount="1250.00"
        )
    """
    try:
        from tools.api_implementations.fiskalizacija_ledger import save_to_ledger

        result = save_to_ledger(
            invoice_number=invoice_number,
            supplier_oib=supplier_oib,
            jir=jir,
            zki=zki,
            signed_xml=signed_xml,
            fina_response=fina_response,
            total_amount=total_amount,
            use_firestore=use_firestore
        )

        if result["success"]:
            logger.info(f"Invoice {invoice_number} saved to ledger, JIR: {jir}")
        else:
            logger.error(f"Failed to save invoice to ledger: {result.get('error')}")

        return result

    except ImportError as e:
        logger.error(f"Missing ledger library: {e}")
        return {
            "success": False,
            "document_id": None,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Ledger save error: {e}")
        return {
            "success": False,
            "document_id": None,
            "error": str(e)
        }


async def add_to_retry_queue(
    invoice_number: str,
    supplier_oib: str,
    signed_xml: str,
    zki: str,
    error_message: str,
    use_firestore: bool = False
) -> dict:
    """
    Add failed fiscalization to retry queue.

    Croatian law requires fiscalization within 48 hours. This queue
    manages automatic retries with exponential backoff.

    Retry schedule: 1m, 2m, 4m, 8m, 16m, 32m, 60m (capped)

    Args:
        invoice_number: Invoice number
        supplier_oib: Supplier's OIB
        signed_xml: Complete signed XML (ready for retry)
        zki: ZKI code
        error_message: Error that caused failure
        use_firestore: Use Firestore (True) or in-memory (False)

    Returns:
        Dictionary containing:
            - success: bool
            - queue_position: int - Position in queue
            - next_retry: str - ISO datetime of next retry
            - deadline: str - 48h deadline (ISO datetime)
            - attempt_count: int - Number of attempts so far
            - error: Optional error message

    Example:
        # After FINA failure
        result = await add_to_retry_queue(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            signed_xml=signed_xml,
            zki="A1B2C3D4-...",
            error_message="Connection timeout"
        )
        print(f"Will retry at {result['next_retry']}, deadline {result['deadline']}")
    """
    try:
        from tools.api_implementations.fiskalizacija_ledger import add_to_retry

        result = add_to_retry(
            invoice_number=invoice_number,
            supplier_oib=supplier_oib,
            signed_xml=signed_xml,
            zki=zki,
            error_message=error_message,
            use_firestore=use_firestore
        )

        if result["success"]:
            logger.info(
                f"Invoice {invoice_number} added to retry queue, "
                f"attempt {result['attempt_count']}, next retry {result['next_retry']}"
            )
        else:
            logger.error(f"Failed to add to retry queue: {result.get('error')}")

        return result

    except ImportError as e:
        logger.error(f"Missing ledger library: {e}")
        return {
            "success": False,
            "queue_position": None,
            "next_retry": None,
            "deadline": None,
            "attempt_count": None,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Retry queue error: {e}")
        return {
            "success": False,
            "queue_position": None,
            "next_retry": None,
            "deadline": None,
            "attempt_count": None,
            "error": str(e)
        }


async def get_pending_retries(use_firestore: bool = False) -> dict:
    """
    Get all invoices due for retry.

    Used by retry scheduler to process pending fiscalizations.

    Args:
        use_firestore: Use Firestore (True) or in-memory (False)

    Returns:
        Dictionary containing:
            - success: bool
            - pending: List of retry entries
            - count: Number of pending retries
            - error: Optional error message

    Example:
        result = await get_pending_retries()
        for entry in result["pending"]:
            await retry_fiscalization(entry)
    """
    try:
        from tools.api_implementations.fiskalizacija_ledger import get_ledger_service

        service = get_ledger_service(use_firestore=use_firestore)
        pending = service.get_pending_retries()

        return {
            "success": True,
            "pending": pending,
            "count": len(pending),
            "error": None
        }

    except Exception as e:
        logger.error(f"Error getting pending retries: {e}")
        return {
            "success": False,
            "pending": [],
            "count": 0,
            "error": str(e)
        }


async def get_retry_queue_stats(use_firestore: bool = False) -> dict:
    """
    Get retry queue statistics.

    Args:
        use_firestore: Use Firestore (True) or in-memory (False)

    Returns:
        Dictionary with:
            - success: bool
            - total: Total entries in queue
            - pending: Entries waiting for retry
            - expired: Entries past 48h deadline
    """
    try:
        from tools.api_implementations.fiskalizacija_ledger import get_ledger_service

        service = get_ledger_service(use_firestore=use_firestore)
        stats = service.get_queue_statistics()

        return {
            "success": True,
            **stats  # Spread operator to include all stats fields
        }

    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        return {
            "success": False,
            "total": 0,
            "pending": 0,
            "expired": 0,
            "error": str(e)
        }


# ============================================================================
# NKD CLASSIFICATION TOOLS (Phase 5 - IMPLEMENTED)
# ============================================================================

async def search_nkd(
    query: str,
    limit: int = 5,
    level: Optional[str] = None
) -> dict:
    """
    Search NKD 2025 classification by text description.

    Use this to find the correct NKD code for invoice items.
    The LLM should suggest NKD codes based on item descriptions.

    Args:
        query: Search text (e.g., "ugradnja stolarije", "prodaja piva")
        limit: Maximum results (default 5)
        level: Filter by level: "podrazred" (5 digits), "razred" (4 digits), etc.

    Returns:
        Dictionary containing:
            - success: bool
            - results: List of matching NKD entries
            - count: Number of results
            - query: Original query

    Example:
        result = await search_nkd("ugradnja PVC prozora")
        # Returns matches like 43.32.0 - Ugradnja stolarije
    """
    try:
        from tools.api_implementations.nkd_service import get_nkd_service

        service = get_nkd_service()
        entries = service.search(query, limit=limit, level=level)

        return {
            "success": True,
            "results": [e.to_dict() for e in entries],
            "count": len(entries),
            "query": query
        }

    except Exception as e:
        logger.error(f"NKD search error: {e}")
        return {
            "success": False,
            "results": [],
            "count": 0,
            "query": query,
            "error": str(e)
        }


async def get_nkd_code(code: str) -> dict:
    """
    Get NKD entry by exact code.

    Args:
        code: NKD code (e.g., "43.32.0", "43.32", "F")

    Returns:
        Dictionary containing:
            - success: bool
            - entry: NKD entry data (code, name, level)
            - hierarchy: Full path from section to code
            - error: Optional error message

    Example:
        result = await get_nkd_code("43.32.0")
        # Returns: F > 43 > 43.3 > 43.32 > 43.32.0 - Ugradnja stolarije
    """
    try:
        from tools.api_implementations.nkd_service import get_nkd_service

        service = get_nkd_service()
        entry = service.get(code)

        if entry:
            hierarchy = service.get_hierarchy(code)
            return {
                "success": True,
                "entry": entry.to_dict(),
                "hierarchy": hierarchy,
                "error": None
            }
        else:
            return {
                "success": False,
                "entry": None,
                "hierarchy": [],
                "error": f"NKD code {code} not found"
            }

    except Exception as e:
        logger.error(f"NKD lookup error: {e}")
        return {
            "success": False,
            "entry": None,
            "hierarchy": [],
            "error": str(e)
        }


async def suggest_nkd_for_item(description: str) -> dict:
    """
    Suggest NKD codes for an invoice item description.

    IMPORTANT: Use this for every invoice line item to determine
    the correct NKD classification for Fiskalizacija 2.0.

    Args:
        description: Item description from invoice

    Returns:
        Dictionary containing:
            - success: bool
            - suggestions: List of NKD suggestions with hierarchy
            - best_match: Top suggestion (if any)
            - requires_confirmation: Whether user should confirm

    Example:
        result = await suggest_nkd_for_item("Ugradnja PVC stolarije - prozori")
        # suggestions[0] = {"code": "43.32.0", "name": "Ugradnja stolarije", ...}
    """
    try:
        from tools.api_implementations.nkd_service import get_nkd_service

        service = get_nkd_service()
        suggestions = service.search_for_invoice_item(description)

        return {
            "success": True,
            "suggestions": suggestions,
            "best_match": suggestions[0] if suggestions else None,
            "requires_confirmation": True,  # Always require human confirmation
            "item_description": description
        }

    except Exception as e:
        logger.error(f"NKD suggestion error: {e}")
        return {
            "success": False,
            "suggestions": [],
            "best_match": None,
            "requires_confirmation": True,
            "item_description": description,
            "error": str(e)
        }


async def validate_company_nkd(nkd_code: str) -> dict:
    """
    Check if NKD activity is registered for the company.

    CRITICAL: Call this before fiscalizing to ensure the activity
    is registered. Unregistered activities may cause legal issues.

    Args:
        nkd_code: NKD code to validate

    Returns:
        Dictionary containing:
            - is_registered: bool
            - nkd_code: The checked code
            - nkd_name: Activity name
            - warning: Warning message if not registered
            - suggestion: Suggested action

    Example:
        result = await validate_company_nkd("43.32.0")
        if not result["is_registered"]:
            # Warn user about unregistered activity
    """
    try:
        from tools.api_implementations.nkd_service import get_nkd_service
        from config.company_config import get_company_config

        service = get_nkd_service()

        # Load company's registered activities
        config = get_company_config()
        service.set_company_activities(config.registered_nkd)

        is_registered, warning = service.is_activity_registered(nkd_code)
        entry = service.get(nkd_code)

        return {
            "is_registered": is_registered,
            "nkd_code": nkd_code,
            "nkd_name": entry.name if entry else None,
            "warning": warning,
            "suggestion": "Registrirajte djelatnost prije izdavanja računa" if not is_registered else None
        }

    except Exception as e:
        logger.error(f"Company NKD validation error: {e}")
        return {
            "is_registered": True,  # Don't block on error
            "nkd_code": nkd_code,
            "nkd_name": None,
            "warning": f"Validation error: {e}",
            "suggestion": None
        }


# ============================================================================
# HUMAN-IN-THE-LOOP TOOLS (Phase 5 - IMPLEMENTED)
# ============================================================================

async def create_fiscalization_confirmation(
    invoice_data: dict,
    validate_nkd: bool = True
) -> dict:
    """
    Create human confirmation request before fiscalization.

    CRITICAL: Always call this before send_fina_soap to get user approval.
    This prevents errors from LLM hallucinations and ensures data accuracy.

    The confirmation includes:
    - Full invoice preview
    - NKD validation for each line
    - Amount verification
    - Warning for unregistered activities
    - Deposit refund summary

    Args:
        invoice_data: Complete invoice data dictionary
        validate_nkd: Whether to validate NKD codes (default True)

    Returns:
        Dictionary containing:
            - confirmation_id: ID to reference this confirmation
            - display_text: Human-readable preview for user
            - has_critical_warnings: Whether there are blocking issues
            - has_unregistered_activities: Whether any NKD is unregistered
            - can_proceed: Whether fiscalization can proceed
            - data: Full confirmation data

    Example:
        conf = await create_fiscalization_confirmation(invoice_data)
        print(conf["display_text"])  # Show to user
        if conf["can_proceed"]:
            # Wait for user approval, then fiscalize
    """
    try:
        from tools.api_implementations.hitl_confirmation import (
            get_hitl_service,
            create_fiscalization_confirmation as _create
        )
        from tools.api_implementations.nkd_service import get_nkd_service

        nkd_service = None
        if validate_nkd:
            try:
                from config.company_config import get_company_config
                nkd_service = get_nkd_service()
                config = get_company_config()
                nkd_service.set_company_activities(config.registered_nkd)
            except Exception:
                pass  # Continue without NKD validation

        result = _create(invoice_data, nkd_service)

        logger.info(f"Created confirmation {result['confirmation_id']}")
        return result

    except Exception as e:
        logger.error(f"Confirmation creation error: {e}")
        return {
            "confirmation_id": None,
            "display_text": f"Error creating confirmation: {e}",
            "has_critical_warnings": True,
            "has_unregistered_activities": False,
            "can_proceed": False,
            "error": str(e)
        }


async def approve_fiscalization(
    confirmation_id: str,
    approved_by: str = "user"
) -> dict:
    """
    Approve pending fiscalization after user review.

    Call this after user confirms the invoice preview.

    Args:
        confirmation_id: ID from create_fiscalization_confirmation
        approved_by: Identifier of who approved

    Returns:
        Dictionary containing:
            - success: bool
            - status: "approved" or error
            - can_fiscalize: Whether to proceed with fiscalization

    Example:
        # After user clicks "Potvrdi"
        result = await approve_fiscalization(conf_id)
        if result["can_fiscalize"]:
            await send_fina_soap(signed_xml)
    """
    try:
        from tools.api_implementations.hitl_confirmation import approve_fiscalization as _approve

        result = _approve(confirmation_id, approved_by)

        if result["success"]:
            result["can_fiscalize"] = True
            logger.info(f"Confirmation {confirmation_id} approved")
        else:
            result["can_fiscalize"] = False

        return result

    except Exception as e:
        logger.error(f"Approval error: {e}")
        return {
            "success": False,
            "status": "error",
            "can_fiscalize": False,
            "error": str(e)
        }


async def reject_fiscalization(
    confirmation_id: str,
    reason: str = ""
) -> dict:
    """
    Reject pending fiscalization.

    Call this if user wants to cancel or modify the invoice.

    Args:
        confirmation_id: ID from create_fiscalization_confirmation
        reason: Optional reason for rejection

    Returns:
        Dictionary with rejection status
    """
    try:
        from tools.api_implementations.hitl_confirmation import reject_fiscalization as _reject

        result = _reject(confirmation_id, reason)
        logger.info(f"Confirmation {confirmation_id} rejected: {reason}")
        return result

    except Exception as e:
        logger.error(f"Rejection error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# DEPOSIT REFUND (POVRATNA NAKNADA) TOOLS (Phase 5 - IMPLEMENTED)
# ============================================================================

async def create_deposit_refund(
    quantity: int,
    description: Optional[str] = None
) -> dict:
    """
    Create deposit refund (povratna naknada) for invoice.

    Use this for beverages with returnable packaging (bottles, cans).
    The deposit is a pass-through item - NOT subject to VAT.

    Current rate: 0.10 EUR per unit (from 1.1.2025)

    Args:
        quantity: Number of returnable units (bottles, cans)
        description: Optional description

    Returns:
        Dictionary containing:
            - deposit_refund: Deposit data for invoice
            - total_amount: Total deposit amount
            - note: Explanation of treatment

    Example:
        # For 30 bottles of beer
        deposit = await create_deposit_refund(30, "Staklene boce piva 0.5L")
        # total_amount = 3.00 EUR
    """
    try:
        from tools.api_implementations.deposit_refund import create_deposit_refund_data

        result = create_deposit_refund_data(
            quantity=quantity,
            description=description
        )

        logger.info(f"Created deposit refund: {quantity} units = {result['total_amount']} EUR")
        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Deposit refund error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def get_deposit_rate() -> dict:
    """
    Get current deposit rate information.

    Returns:
        Dictionary with:
            - amount_per_unit: Current rate (0.10 EUR)
            - applies_to: Types of packaging covered
            - recipient: Where the money goes (FZOEU)
            - vat_treatment: How it's treated for VAT

    Example:
        rate = await get_deposit_rate()
        # amount_per_unit = "0.10", applies_to = ["Plastična ambalaža...", ...]
    """
    try:
        from tools.api_implementations.deposit_refund import get_current_deposit_rate

        return {
            "success": True,
            **get_current_deposit_rate()
        }

    except Exception as e:
        logger.error(f"Deposit rate error: {e}")
        return {
            "success": False,
            "amount_per_unit": "0.10",
            "currency": "EUR",
            "error": str(e)
        }


# ============================================================================
# PDF GENERATION (Phase 6 - NEW)
# ============================================================================

async def generate_invoice_pdf(invoice_data: dict, jir: str, zki: str, qr_code_base64: str) -> dict:
    """
    Generate a professional PDF invoice from invoice data using ReportLab.

    This function creates a Croatian-compliant invoice PDF with:
    - Company and customer details
    - Itemized list with VAT breakdown
    - Fiscal information (JIR, ZKI)
    - QR code for verification

    Args:
        invoice_data: Dictionary containing invoice details:
            - supplier: {name, oib, address, city, postal_code, phone, email, iban}
            - customer: {name, oib, address, city, postal_code}
            - invoice_number: str
            - issue_date: str (YYYY-MM-DD)
            - issue_time: str (HH:MM:SS)
            - due_date: str (YYYY-MM-DD)
            - payment_means_code: str
            - items: [{description, quantity, unit_code, unit_price, vat_rate, line_total}]
            - tax_breakdown: {subtotals: [{vat_rate, taxable_amount, tax_amount}], total_net, total_gross}
            - business_unit: str (oznaka poslovnog prostora)
            - device_number: str (oznaka naplatnog uređaja)
            - operator_oib: str
        jir: Jedinstveni Identifikator Računa from FINA
        zki: Zaštitni Kod Izdavatelja
        qr_code_base64: Base64-encoded QR code image

    Returns:
        Dictionary with:
            - success: bool
            - pdf_bytes: bytes (if success=True)
            - pdf_path: str (if saved to file)
            - error: str (if success=False)

    Example:
        pdf_result = await generate_invoice_pdf(
            invoice_data=invoice_data,
            jir="94450703-8e84-4c4f-94f6-4586a025ed7b",
            zki="abc123def456",
            qr_code_base64="iVBORw0KGgo..."
        )
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os
        import base64
        from io import BytesIO

        logger.info(f"Generating PDF for invoice {invoice_data.get('invoice_number')}")

        # Register Unicode font for Croatian characters (č, ć, đ, š, ž)
        # Try to use DejaVu Sans (common on most systems) or fallback to system fonts
        try:
            # Windows: Try Arial (has Unicode support)
            font_path_arial = "C:\\Windows\\Fonts\\arial.ttf"
            font_path_arial_bold = "C:\\Windows\\Fonts\\arialbd.ttf"

            if os.path.exists(font_path_arial):
                pdfmetrics.registerFont(TTFont('ArialUnicode', font_path_arial))
                pdfmetrics.registerFont(TTFont('ArialUnicode-Bold', font_path_arial_bold))
                unicode_font = 'ArialUnicode'
                unicode_font_bold = 'ArialUnicode-Bold'
                logger.info("Registered Arial Unicode font for Croatian characters")
            else:
                # Fallback to Helvetica (won't show Croatian chars properly, but won't crash)
                unicode_font = 'Helvetica'
                unicode_font_bold = 'Helvetica-Bold'
                logger.warning("Arial not found, using Helvetica (Croatian characters may not display correctly)")
        except Exception as font_error:
            logger.warning(f"Font registration failed: {font_error}, using default Helvetica")
            unicode_font = 'Helvetica'
            unicode_font_bold = 'Helvetica-Bold'

        # Parse invoice number for fiscal data
        invoice_number = invoice_data.get("invoice_number", "")
        parts = invoice_number.split("/")
        broj_racuna = parts[0] if len(parts) > 0 else ""
        oznaka_pp = parts[1] if len(parts) > 1 else ""
        oznaka_nu = parts[2] if len(parts) > 2 else ""

        # Extract data
        supplier = invoice_data.get("supplier", {})
        customer = invoice_data.get("customer", {})
        items = invoice_data.get("items", [])
        tax_breakdown = invoice_data.get("tax_breakdown", {})

        # Payment means mapping
        payment_means_map = {
            "10": "Gotovina",
            "30": "Transakcijski račun",
            "48": "Kartica",
            "other": "Ostalo"
        }
        payment_code = invoice_data.get("payment_means_code", "30")
        payment_means = payment_means_map.get(str(payment_code), payment_means_map["other"])

        # Create output directory
        output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output", "invoices")
        os.makedirs(output_dir, exist_ok=True)
        pdf_filename = f"invoice_{invoice_number.replace('/', '_')}_{jir[:8]}.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)

        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        # Container for PDF elements
        story = []

        # Styles (with Unicode font support)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=unicode_font_bold,
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=unicode_font_bold,
            fontSize=12,
            textColor=colors.HexColor('#2c3e50'),
            spaceBefore=10,
            spaceAfter=10
        )
        normal_style = ParagraphStyle(
            'NormalUnicode',
            parent=styles['Normal'],
            fontName=unicode_font,
            fontSize=10
        )
        small_style = ParagraphStyle(
            'SmallUnicode',
            parent=styles['Normal'],
            fontName=unicode_font,
            fontSize=8
        )

        # Title
        story.append(Paragraph("RAČUN", title_style))
        story.append(Spacer(1, 0.5*cm))

        # Header table (Supplier info + Invoice details)
        header_data = [
            [
                Paragraph(f"<b>{supplier.get('name', '')}</b><br/>"
                         f"{supplier.get('address', '')}<br/>"
                         f"{supplier.get('postal_code', '')} {supplier.get('city', '')}<br/>"
                         f"<b>OIB:</b> {supplier.get('oib', '')}", normal_style),
                Paragraph(f"<b>Broj računa:</b> {invoice_number}<br/>"
                         f"<b>Datum:</b> {invoice_data.get('issue_date', '')}<br/>"
                         f"<b>Vrijeme:</b> {invoice_data.get('issue_time', '12:00:00')}<br/>"
                         f"<b>Način plaćanja:</b> {payment_means}", normal_style)
            ]
        ]
        header_table = Table(header_data, colWidths=[9*cm, 8*cm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.5*cm))

        # Customer info
        story.append(Paragraph("<b>KUPAC:</b>", heading_style))
        customer_text = f"{customer.get('name', 'Fizička osoba')}"
        if customer.get('oib'):
            customer_text += f"<br/>OIB: {customer.get('oib')}"
        if customer.get('address'):
            customer_text += f"<br/>{customer.get('address')}"
        if customer.get('city'):
            customer_text += f"<br/>{customer.get('postal_code', '')} {customer.get('city')}"
        story.append(Paragraph(customer_text, normal_style))
        story.append(Spacer(1, 0.5*cm))

        # Items table
        story.append(Paragraph("<b>STAVKE:</b>", heading_style))

        items_data = [['R.br.', 'Opis', 'Količina', 'J.M.', 'Cijena', 'PDV %', 'Ukupno']]
        for i, item in enumerate(items, start=1):
            items_data.append([
                str(i),
                str(item.get('description', '')),
                str(item.get('quantity', '')),
                str(item.get('unit_code', 'kom')),
                f"{float(item.get('unit_price', 0)):.2f} €",
                f"{float(item.get('vat_rate', 0)):.0f}%",
                f"{float(item.get('line_total', 0)):.2f} €"
            ])

        items_table = Table(items_data, colWidths=[1*cm, 7*cm, 2*cm, 1.5*cm, 2*cm, 1.5*cm, 2*cm])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), unicode_font_bold),
            ('FONTNAME', (0, 1), (-1, -1), unicode_font),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 0.5*cm))

        # Totals table
        totals_data = [
            ['Ukupno bez PDV-a:', f"{float(tax_breakdown.get('total_net', 0)):.2f} €"]
        ]
        for sub in tax_breakdown.get("subtotals", []):
            if float(sub.get("vat_rate", 0)) > 0:
                totals_data.append([
                    f"PDV {float(sub.get('vat_rate', 0)):.0f}% (na {float(sub.get('taxable_amount', 0)):.2f} €):",
                    f"{float(sub.get('tax_amount', 0)):.2f} €"
                ])
        totals_data.append([
            Paragraph("<b>UKUPNO ZA PLATITI:</b>", normal_style),
            Paragraph(f"<b>{float(tax_breakdown.get('total_gross', 0)):.2f} €</b>", normal_style)
        ])

        totals_table = Table(totals_data, colWidths=[10*cm, 7*cm])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#2c3e50')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f0f0')),
            ('TOPPADDING', (0, -1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
        ]))
        story.append(totals_table)
        story.append(Spacer(1, 0.8*cm))

        # Fiscal info + QR code
        story.append(Paragraph("<b>PODACI O FISKALIZACIJI:</b>", heading_style))

        # Decode QR code from base64
        qr_image = None
        if qr_code_base64:
            try:
                logger.info(f"Decoding QR code (base64 length: {len(qr_code_base64)} chars)")
                qr_bytes = base64.b64decode(qr_code_base64)
                logger.info(f"QR code decoded successfully ({len(qr_bytes)} bytes)")
                qr_buffer = BytesIO(qr_bytes)
                qr_image = Image(qr_buffer, width=3*cm, height=3*cm)
                logger.info("QR code image created successfully")
            except Exception as e:
                logger.error(f"Could not decode QR code: {e}", exc_info=True)
                # Create a placeholder text instead of crashing
                logger.warning("QR code will not be included in PDF")

        fiscal_text = (
            f"<b>JIR:</b> {jir}<br/>"
            f"<b>ZKI:</b> {zki}<br/><br/>"
            f"Operater: {invoice_data.get('operator_oib', supplier.get('oib', ''))}<br/>"
            f"Poslovni prostor: {invoice_data.get('business_unit', oznaka_pp)}<br/>"
            f"Naplatni uređaj: {invoice_data.get('device_number', oznaka_nu)}<br/><br/>"
            f"<font size=7>Račun je fiskaliziran sukladno Zakonu o fiskalizaciji u prometu gotovinom.</font>"
        )

        if qr_image:
            fiscal_data = [[Paragraph(fiscal_text, normal_style), qr_image]]
            fiscal_table = Table(fiscal_data, colWidths=[14*cm, 3*cm])
            fiscal_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(fiscal_table)
        else:
            story.append(Paragraph(fiscal_text, normal_style))

        # Build PDF
        doc.build(story)

        # Read PDF bytes
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        logger.info(f"PDF generated successfully: {pdf_path} ({len(pdf_bytes)} bytes)")

        return {
            "success": True,
            "pdf_bytes": pdf_bytes,
            "pdf_path": pdf_path,
            "pdf_filename": pdf_filename,
            "size_bytes": len(pdf_bytes),
            "error": None
        }

    except Exception as e:
        logger.error(f"PDF generation error: {e}", exc_info=True)
        return {
            "success": False,
            "pdf_bytes": None,
            "pdf_path": None,
            "error": str(e)
        }


# ============================================================================
# COMPLETE FISCALIZATION EXECUTION (Phase 7 - ORCHESTRATOR INTEGRATION)
# ============================================================================

def _normalize_invoice_for_pdf(invoice_data: dict) -> dict:
    """
    Normalize invoice data to the format expected by generate_invoice_pdf.

    Converts flat fields (supplier_oib, supplier_name) to nested structure
    (supplier: {oib, name, address, ...}).

    This ensures PDF generation works regardless of input format.
    """
    from datetime import datetime

    # Start with a copy to avoid modifying original
    normalized = dict(invoice_data)

    # Normalize supplier data
    if 'supplier' not in normalized or not isinstance(normalized.get('supplier'), dict):
        normalized['supplier'] = {
            'name': invoice_data.get('supplier_name', 'LUX TECH D.O.O.'),
            'oib': invoice_data.get('supplier_oib', ''),
            'address': invoice_data.get('supplier_address', 'Leskovački brijeg 2'),
            'city': invoice_data.get('supplier_city', 'Hrvatski Leskovac'),
            'postal_code': invoice_data.get('supplier_postal_code', '10257'),
            'email': invoice_data.get('supplier_email', 'tomislav.luxtech@gmail.com'),
            'phone': invoice_data.get('supplier_phone', '+385914575757'),
            'iban': invoice_data.get('supplier_iban', ''),
        }

    # Normalize customer data
    if 'customer' not in normalized or not isinstance(normalized.get('customer'), dict):
        normalized['customer'] = {
            'name': invoice_data.get('customer_name', 'Fizička osoba'),
            'oib': invoice_data.get('customer_oib', ''),
            'address': invoice_data.get('customer_address', ''),
            'city': invoice_data.get('customer_city', ''),
            'postal_code': invoice_data.get('customer_postal_code', ''),
        }

    # Normalize dates
    if 'issue_date' not in normalized:
        invoice_dt = invoice_data.get('invoice_datetime')
        if invoice_dt:
            if isinstance(invoice_dt, str):
                try:
                    dt = datetime.fromisoformat(invoice_dt.replace('Z', '+00:00'))
                    normalized['issue_date'] = dt.strftime('%Y-%m-%d')
                    normalized['issue_time'] = dt.strftime('%H:%M:%S')
                except:
                    normalized['issue_date'] = datetime.now().strftime('%Y-%m-%d')
                    normalized['issue_time'] = datetime.now().strftime('%H:%M:%S')
            elif isinstance(invoice_dt, datetime):
                normalized['issue_date'] = invoice_dt.strftime('%Y-%m-%d')
                normalized['issue_time'] = invoice_dt.strftime('%H:%M:%S')
        else:
            normalized['issue_date'] = datetime.now().strftime('%Y-%m-%d')
            normalized['issue_time'] = datetime.now().strftime('%H:%M:%S')

    # Normalize items - ensure line_total is calculated
    items = normalized.get('items', [])
    total_net = 0.0
    total_vat = 0.0

    for item in items:
        quantity = float(item.get('quantity', 1))
        unit_price = float(item.get('unit_price', 0))
        vat_rate = float(item.get('vat_rate', 25))

        line_net = quantity * unit_price
        line_vat = line_net * (vat_rate / 100)
        line_total = line_net + line_vat

        item['line_total'] = line_total
        item['unit_code'] = item.get('unit_code', 'kom')

        total_net += line_net
        total_vat += line_vat

    normalized['items'] = items

    # Normalize tax_breakdown
    if 'tax_breakdown' not in normalized or not isinstance(normalized.get('tax_breakdown'), dict):
        total_gross = total_net + total_vat

        # Group by VAT rate
        vat_groups = {}
        for item in items:
            vat_rate = str(int(float(item.get('vat_rate', 25))))
            if vat_rate not in vat_groups:
                vat_groups[vat_rate] = {'taxable': 0.0, 'tax': 0.0}
            quantity = float(item.get('quantity', 1))
            unit_price = float(item.get('unit_price', 0))
            line_net = quantity * unit_price
            line_vat = line_net * (float(vat_rate) / 100)
            vat_groups[vat_rate]['taxable'] += line_net
            vat_groups[vat_rate]['tax'] += line_vat

        subtotals = []
        for rate, amounts in vat_groups.items():
            subtotals.append({
                'vat_rate': float(rate),
                'taxable_amount': amounts['taxable'],
                'tax_amount': amounts['tax']
            })

        normalized['tax_breakdown'] = {
            'total_net': total_net,
            'total_gross': total_gross,
            'subtotals': subtotals
        }

    # Payment means code mapping
    payment_method = invoice_data.get('payment_method', 'G')
    payment_map = {'G': '10', 'K': '48', 'T': '30', 'O': '97'}
    normalized['payment_means_code'] = payment_map.get(payment_method, '30')

    # Business unit and device from invoice number
    invoice_number = normalized.get('invoice_number', '1/1/1')
    parts = invoice_number.split('/')
    normalized['business_unit'] = parts[1] if len(parts) > 1 else '1'
    normalized['device_number'] = parts[2] if len(parts) > 2 else '1'

    # Operator OIB
    normalized['operator_oib'] = invoice_data.get('operator_oib', normalized['supplier']['oib'])

    return normalized


async def execute_fiscalization(
    invoice_data: dict
) -> dict:
    """
    Execute complete fiscalization workflow using the hybrid orchestrator.

    This is the MAIN ENTRY POINT for fiscalization from the Smart Orchestrator.
    It coordinates the complete pipeline:
        1. Data preparation (validates OIB, formats data)
        2. Validation (quality gate)
        3. Human-in-the-loop confirmation (ALWAYS prompts user before execution)
        4. Deterministic execution (sign + send to FINA)
        5. PDF generation

    CRITICAL: This function uses the Deterministic Executor for the critical path
    (signing and SOAP communication) - NO LLM involvement in cryptographic operations.

    CRITICAL: HITL (Human-in-the-Loop) confirmation is MANDATORY. The user MUST
    confirm before the invoice is sent to FINA. This cannot be skipped or auto-approved.

    Args:
        invoice_data: Dictionary containing invoice details:
            - invoice_number: str (format: "XXX/PP/NU" e.g., "001/1/1")
            - supplier_oib: str (11-digit OIB, validated)
            - supplier_name: str
            - customer_name: str (optional, for B2C can be empty)
            - customer_oib: str (optional, for B2C can be empty)
            - total_amount: str or Decimal (gross amount including VAT - auto-calculated from items if not provided)
            - payment_method: str ("G"=cash, "K"=card, "T"=transfer, "O"=other)
            - items: list of dicts with:
                - description: str
                - quantity: float
                - unit_price: float
                - vat_rate: float (0, 5, 13, or 25)
                - kpd_code: str (optional, e.g., "62.10.11")
            - pdv_breakdown: list of dicts (optional, auto-calculated if not provided):
                - stopa: str (VAT rate, e.g., "25.00")
                - osnovica: str (taxable base)
                - iznos: str (VAT amount)
            - invoice_datetime: str (ISO format, optional - defaults to now)
            - operator_oib: str (optional, defaults to supplier_oib)
            - is_late_delivery: bool (optional, default False)

    Returns:
        Dictionary with:
            - success: bool - Whether fiscalization succeeded
            - status: str - One of: "success", "needs_review", "validation_failed",
                          "execution_failed", "retry_queued"
            - jir: str - Jedinstveni Identifikator Računa (if successful)
            - zki: str - Zaštitni Kod Izdavatelja
            - verification_url: str - URL for verification on Porezna website
            - pdf_path: str - Path to generated PDF invoice
            - qr_code_base64: str - Base64 encoded QR code
            - error_message: str - Error details if failed
            - timing: dict - Execution timing breakdown

    Example:
        # Simple B2C invoice (gotovina/cash)
        result = await execute_fiscalization({
            "invoice_number": "001/1/1",
            "supplier_oib": "47034854402",
            "supplier_name": "LUX TECH D.O.O.",
            "total_amount": "125.00",
            "payment_method": "G",
            "items": [
                {"description": "IT Consulting", "quantity": 1, "unit_price": 100.00, "vat_rate": 25}
            ]
        })

        # Returns:
        # {
        #     "success": True,
        #     "jir": "a1b2c3d4-...",
        #     "zki": "ABCD1234...",
        #     "verification_url": "https://porezna.gov.hr/rn?jir=...",
        #     "pdf_path": "output/invoices/invoice_001_1_1_a1b2c3d4.pdf"
        # }
    """
    import os
    import asyncio
    from pathlib import Path

    logger.info(f"=== EXECUTE FISCALIZATION ===")
    logger.info(f"Invoice: {invoice_data.get('invoice_number', 'UNKNOWN')}")
    logger.info(f"Amount: {invoice_data.get('total_amount', 'UNKNOWN')} EUR")

    try:
        # Get certificate configuration
        project_root = Path(__file__).parent.parent.parent
        cert_path = str(project_root / os.environ.get('FINA_CERT_PATH', '47034854402.F1.1.p12'))
        cert_password = os.environ.get('FINA_CERT_PASSWORD')
        if not cert_password:
            return {
                "success": False,
                "status": "config_error",
                "error_message": "FINA_CERT_PASSWORD environment variable is required but not set.",
                "jir": None,
            }
        use_sandbox = os.environ.get('FINA_SANDBOX', 'true').lower() == 'true'

        logger.info(f"Certificate: {cert_path}")
        logger.info(f"Sandbox mode: {use_sandbox}")

        # Validate certificate exists
        if not os.path.exists(cert_path):
            return {
                "success": False,
                "status": "execution_failed",
                "error_message": f"Certificate not found: {cert_path}",
                "jir": None,
                "zki": None
            }

        # HITL is ALWAYS required in production - only env var can override (for automated testing)
        # The LLM agent must NEVER bypass HITL confirmation
        if 'AUTO_APPROVE_HITL' not in os.environ:
            os.environ['AUTO_APPROVE_HITL'] = 'false'
        logger.info(f"HITL mode: {'auto-approve (testing)' if os.environ.get('AUTO_APPROVE_HITL') == 'true' else 'user confirmation required'}")

        # Enrich invoice data with supplier info if not provided
        if not invoice_data.get('supplier_oib'):
            supplier_result = await get_supplier_data()
            if supplier_result.get('success'):
                supplier = supplier_result['supplier']
                invoice_data['supplier_oib'] = supplier['oib']
                invoice_data['supplier_name'] = invoice_data.get('supplier_name') or supplier['name']
                invoice_data['operator_oib'] = invoice_data.get('operator_oib') or supplier['oib']
                logger.info(f"Enriched with supplier data: OIB={supplier['oib']}")

        # Auto-generate invoice number if not provided
        if not invoice_data.get('invoice_number'):
            number_result = await generate_invoice_number()
            if number_result.get('success'):
                invoice_data['invoice_number'] = number_result['invoice_number']
                logger.info(f"Auto-generated invoice number: {invoice_data['invoice_number']}")

        # Calculate PDV breakdown if not provided
        if not invoice_data.get('pdv_breakdown') and invoice_data.get('items'):
            # Convert items to format expected by calculate_tax
            # calculate_tax expects net_amount, we might have unit_price * quantity
            tax_items = []
            for item in invoice_data['items']:
                quantity = float(item.get('quantity', 1))
                unit_price = float(item.get('unit_price', 0))
                net_amount = item.get('net_amount', quantity * unit_price)
                tax_items.append({
                    'net_amount': str(net_amount),
                    'vat_rate': str(int(float(item.get('vat_rate', 25)))),
                    'description': item.get('description', '')
                })

            tax_result = await calculate_tax(tax_items)
            if tax_result.get('success'):
                invoice_data['pdv_breakdown'] = tax_result.get('pdv_breakdown', [])
                invoice_data['total_amount'] = tax_result.get('total_gross')
                logger.info(f"Calculated tax: {invoice_data['total_amount']} EUR")

        # Import and run the orchestrator (async-compatible)
        from agents.adk_agents.fiskalizacija_orchestrator import (
            FiskalizacijaOrchestrator,
            InvoiceInput,
        )

        orchestrator = FiskalizacijaOrchestrator(
            cert_path=cert_path,
            cert_password=cert_password,
            use_sandbox=use_sandbox,
            skip_llm=True  # Use basic validation (LLM agents for later phase)
        )

        input_data = InvoiceInput(
            structured_data=invoice_data,
            cert_path=cert_path,
            cert_password=cert_password,
            use_sandbox=use_sandbox
        )

        # Run async processing
        orchestrator_result = await orchestrator.process_invoice(input_data)

        # Generate PDF if successful
        if orchestrator_result.success and orchestrator_result.jir:
            try:
                # Normalize invoice_data to PDF-expected format
                pdf_invoice_data = _normalize_invoice_for_pdf(invoice_data)

                pdf_result = await generate_invoice_pdf(
                    invoice_data=pdf_invoice_data,
                    jir=orchestrator_result.jir,
                    zki=orchestrator_result.zki,
                    qr_code_base64=orchestrator_result.qr_code_base64 or ""
                )
                if pdf_result.get('success'):
                    orchestrator_result.pdf_path = pdf_result.get('pdf_path')
                    logger.info(f"PDF generated: {orchestrator_result.pdf_path}")
            except Exception as pdf_error:
                logger.error(f"PDF generation error: {pdf_error}")

        # Convert to dict
        result = orchestrator_result.to_dict()

        # Format response
        response = {
            "success": result.get('success', False),
            "status": result.get('status', 'unknown'),
            "jir": result.get('jir'),
            "zki": result.get('zki'),
            "verification_url": result.get('verification_url'),
            "pdf_path": result.get('pdf_path'),
            "qr_code_base64": result.get('qr_code_base64'),
            "error_message": result.get('error_message'),
            "timing": {
                "preparation_ms": result.get('preparation_time_ms', 0),
                "validation_ms": result.get('validation_time_ms', 0),
                "execution_ms": result.get('execution_time_ms', 0),
                "total_ms": result.get('total_time_ms', 0)
            }
        }

        if response['success']:
            logger.info(f"[OK] Fiscalization successful! JIR: {response['jir']}")
        else:
            logger.error(f"[ERROR] Fiscalization failed: {response['error_message']}")

        return response

    except Exception as e:
        logger.error(f"Fiscalization execution error: {e}", exc_info=True)
        return {
            "success": False,
            "status": "execution_failed",
            "error_message": str(e),
            "jir": None,
            "zki": None
        }


# ============================================================================
# EXPORTS - All tools that should be available to agents
# ============================================================================

__all__ = [
    # Validation and Preparation (Phase 1 - IMPLEMENTED)
    "get_supplier_data",
    "generate_invoice_number",
    "validate_oib",
    "lookup_vies",
    "search_kpd_code",
    "validate_kpd_code",
    "calculate_tax",
    "normalize_unit",
    "check_invoice_number_format",
    "verify_tax_calculation",

    # XML Construction (Phase 2 - IMPLEMENTED)
    "build_ubl_invoice",
    "validate_xsd",
    "canonicalize_xml",

    # Signing (Phase 3 - IMPLEMENTED)
    "load_certificate",
    "sign_xades",
    "calculate_zki",
    "verify_xml_signature",

    # Communication (Phase 4 - IMPLEMENTED)
    "send_fina_soap",
    "parse_fina_response",
    "generate_qr_code",
    "get_circuit_breaker_status",

    # Ledger and Queue (Phase 4 - IMPLEMENTED)
    "check_invoice_ledger",
    "save_invoice_ledger",
    "add_to_retry_queue",
    "get_pending_retries",
    "get_retry_queue_stats",

    # NKD Classification (Phase 5 - IMPLEMENTED)
    "search_nkd",
    "get_nkd_code",
    "suggest_nkd_for_item",
    "validate_company_nkd",

    # Human-in-the-Loop (Phase 5 - IMPLEMENTED)
    "create_fiscalization_confirmation",
    "approve_fiscalization",
    "reject_fiscalization",

    # Deposit Refund (Phase 5 - IMPLEMENTED)
    "create_deposit_refund",
    "get_deposit_rate",

    # PDF Generation (Phase 6 - NEW)
    "generate_invoice_pdf",

    # Complete Fiscalization (Phase 7 - ORCHESTRATOR INTEGRATION)
    "execute_fiscalization",
]
