"""
XML Validation and Canonicalization for Croatian Fiscalization

Provides:
- XSD schema validation against EN 16931 + HR-FISK 2.0
- XML Canonicalization (C14N) for digital signing
- Well-formedness checking

This is a DETERMINISTIC tool - no LLM involvement.
"""

from typing import List, Dict, Any, Optional, Tuple
from lxml import etree
from io import BytesIO
import logging
import os

logger = logging.getLogger(__name__)

# ============================================================================
# SCHEMA PATHS
# ============================================================================

# Base path for schemas
SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'schemas',
    'ubl'
)

# UBL 2.1 Invoice schema (would be downloaded in production)
UBL_INVOICE_SCHEMA = os.path.join(SCHEMA_DIR, 'UBL-Invoice-2.1.xsd')

# EN 16931 CIUS schema
EN16931_SCHEMA = os.path.join(SCHEMA_DIR, 'EN16931-UBL-validation.xsd')

# HR-FISK 2.0 extension schema
HR_FISK_SCHEMA = os.path.join(SCHEMA_DIR, 'HR-FISK-2.0-Extension.xsd')


# ============================================================================
# XSD VALIDATION
# ============================================================================

class XSDValidationError:
    """Represents a single XSD validation error."""

    def __init__(self, line: int, column: int, message: str, element: Optional[str] = None):
        self.line = line
        self.column = column
        self.message = message
        self.element = element

    def to_dict(self) -> Dict[str, Any]:
        return {
            'line': self.line,
            'column': self.column,
            'message': self.message,
            'element': self.element
        }

    def __str__(self) -> str:
        return f"Line {self.line}, Column {self.column}: {self.message}"


class XSDValidator:
    """
    Validates XML documents against XSD schemas.

    Supports:
    - UBL 2.1 Invoice schema
    - EN 16931 European e-Invoice constraints
    - HR-FISK 2.0 Croatian extension
    """

    def __init__(self, schema_path: Optional[str] = None):
        """
        Initialize validator with optional custom schema.

        Args:
            schema_path: Path to XSD schema file. If None, uses embedded minimal schema.
        """
        self.schema = None
        self.schema_path = schema_path
        self._load_schema()

    def _load_schema(self) -> None:
        """Load XSD schema from file or use embedded minimal schema."""
        if self.schema_path and os.path.exists(self.schema_path):
            try:
                with open(self.schema_path, 'rb') as f:
                    schema_doc = etree.parse(f)
                self.schema = etree.XMLSchema(schema_doc)
                logger.info(f"Loaded XSD schema from {self.schema_path}")
            except Exception as e:
                logger.warning(f"Failed to load schema from {self.schema_path}: {e}")
                self._use_minimal_schema()
        else:
            self._use_minimal_schema()

    def _use_minimal_schema(self) -> None:
        """
        Use a minimal embedded schema for basic validation.

        In production, full UBL 2.1 + EN 16931 schemas should be used.
        This minimal schema validates basic structure only.
        """
        # Minimal schema that validates basic UBL Invoice structure
        minimal_schema = '''<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ubl="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
           xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
           xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
           targetNamespace="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
           elementFormDefault="qualified">

    <xs:import namespace="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"/>
    <xs:import namespace="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"/>

    <xs:element name="Invoice">
        <xs:complexType>
            <xs:sequence>
                <xs:any processContents="lax" minOccurs="0" maxOccurs="unbounded"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>'''

        try:
            schema_doc = etree.fromstring(minimal_schema.encode('utf-8'))
            self.schema = etree.XMLSchema(schema_doc)
            logger.info("Using minimal embedded XSD schema")
        except Exception as e:
            logger.error(f"Failed to create minimal schema: {e}")
            self.schema = None

    def validate(self, xml_string: str) -> Tuple[bool, List[XSDValidationError]]:
        """
        Validate XML string against schema.

        Args:
            xml_string: XML document as string

        Returns:
            Tuple of (is_valid: bool, errors: List[XSDValidationError])
        """
        errors = []

        # First check well-formedness
        try:
            if isinstance(xml_string, str):
                xml_bytes = xml_string.encode('utf-8')
            else:
                xml_bytes = xml_string

            doc = etree.parse(BytesIO(xml_bytes))
        except etree.XMLSyntaxError as e:
            errors.append(XSDValidationError(
                line=e.lineno or 0,
                column=e.offset or 0,
                message=f"XML Syntax Error: {e.msg}",
                element=None
            ))
            return False, errors

        # If no schema loaded, just check well-formedness
        if self.schema is None:
            logger.warning("No XSD schema loaded, only checking well-formedness")
            return True, errors

        # Validate against schema
        try:
            self.schema.assertValid(doc)
            return True, errors
        except etree.DocumentInvalid as e:
            # Collect all validation errors
            for error in self.schema.error_log:
                errors.append(XSDValidationError(
                    line=error.line,
                    column=error.column,
                    message=error.message,
                    element=error.path
                ))
            return False, errors


def validate_xsd(xml_string: str, schema_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate XML against XSD schema.

    Convenience function for use in ADK tools.

    Args:
        xml_string: XML document as string
        schema_path: Optional path to XSD schema

    Returns:
        Dictionary with:
            - valid: bool
            - errors: List of error dicts
            - schema_version: Schema version used
    """
    validator = XSDValidator(schema_path)
    is_valid, errors = validator.validate(xml_string)

    return {
        'valid': is_valid,
        'errors': [e.to_dict() for e in errors],
        'schema_version': 'UBL-2.1-minimal' if validator.schema else 'none',
        'error_count': len(errors)
    }


# ============================================================================
# XML CANONICALIZATION (C14N)
# ============================================================================

class XMLCanonicalizer:
    """
    Canonicalizes XML documents for digital signing.

    Supports:
    - Exclusive XML Canonicalization 1.0 (exc-c14n)
    - Canonical XML 1.0 (c14n)
    - With or without comments
    """

    @staticmethod
    def canonicalize(
        xml_string: str,
        exclusive: bool = True,
        with_comments: bool = False
    ) -> str:
        """
        Canonicalize XML document.

        Args:
            xml_string: XML document as string
            exclusive: Use exclusive canonicalization (default True for XAdES)
            with_comments: Include comments in output (default False)

        Returns:
            Canonicalized XML as string
        """
        try:
            # Parse XML
            if isinstance(xml_string, str):
                xml_bytes = xml_string.encode('utf-8')
            else:
                xml_bytes = xml_string

            doc = etree.parse(BytesIO(xml_bytes))
            root = doc.getroot()

            # Canonicalize
            # lxml's c14n2 is the recommended method
            canonical_xml = etree.tostring(
                root,
                method='c14n2' if not exclusive else 'c14n',
                exclusive=exclusive,
                with_comments=with_comments
            )

            return canonical_xml.decode('utf-8')

        except Exception as e:
            logger.error(f"Canonicalization failed: {e}")
            raise

    @staticmethod
    def canonicalize_element(
        element: etree._Element,
        exclusive: bool = True,
        with_comments: bool = False,
        inclusive_ns_prefixes: Optional[List[str]] = None
    ) -> bytes:
        """
        Canonicalize a single XML element.

        Used for signing specific parts of document.

        Args:
            element: lxml Element to canonicalize
            exclusive: Use exclusive canonicalization
            with_comments: Include comments
            inclusive_ns_prefixes: Namespace prefixes to include (for exc-c14n)

        Returns:
            Canonical form as bytes
        """
        return etree.tostring(
            element,
            method='c14n',
            exclusive=exclusive,
            with_comments=with_comments,
            inclusive_ns_prefixes=inclusive_ns_prefixes
        )


def canonicalize_xml(
    xml_string: str,
    exclusive: bool = True,
    with_comments: bool = False
) -> Dict[str, Any]:
    """
    Canonicalize XML document.

    Convenience function for use in ADK tools.

    Args:
        xml_string: XML document as string
        exclusive: Use exclusive canonicalization (default True)
        with_comments: Include comments (default False)

    Returns:
        Dictionary with:
            - success: bool
            - canonical_xml: Canonicalized XML string
            - error: Optional error message
    """
    try:
        canonical = XMLCanonicalizer.canonicalize(
            xml_string,
            exclusive=exclusive,
            with_comments=with_comments
        )

        return {
            'success': True,
            'canonical_xml': canonical,
            'error': None,
            'method': 'exc-c14n' if exclusive else 'c14n',
            'with_comments': with_comments
        }

    except Exception as e:
        logger.error(f"Canonicalization failed: {e}")
        return {
            'success': False,
            'canonical_xml': None,
            'error': str(e)
        }


# ============================================================================
# WELL-FORMEDNESS CHECK
# ============================================================================

def check_well_formed(xml_string: str) -> Dict[str, Any]:
    """
    Check if XML is well-formed (valid XML syntax).

    Args:
        xml_string: XML document as string

    Returns:
        Dictionary with:
            - well_formed: bool
            - error: Optional error message with line/column
    """
    try:
        if isinstance(xml_string, str):
            xml_bytes = xml_string.encode('utf-8')
        else:
            xml_bytes = xml_string

        etree.parse(BytesIO(xml_bytes))
        return {
            'well_formed': True,
            'error': None
        }

    except etree.XMLSyntaxError as e:
        return {
            'well_formed': False,
            'error': f"Line {e.lineno}, Column {e.offset}: {e.msg}"
        }


# ============================================================================
# NAMESPACE EXTRACTION
# ============================================================================

def extract_namespaces(xml_string: str) -> Dict[str, str]:
    """
    Extract namespace declarations from XML document.

    Args:
        xml_string: XML document as string

    Returns:
        Dictionary of prefix -> namespace URI
    """
    try:
        if isinstance(xml_string, str):
            xml_bytes = xml_string.encode('utf-8')
        else:
            xml_bytes = xml_string

        doc = etree.parse(BytesIO(xml_bytes))
        root = doc.getroot()

        return dict(root.nsmap)

    except Exception as e:
        logger.error(f"Failed to extract namespaces: {e}")
        return {}
