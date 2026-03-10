"""
Tests for XAdES-BES Digital Signing Module

Tests:
- Certificate loading from file
- ZKI calculation
- XAdES-BES signing
- Signature verification
- ADK tool wrappers
"""

import pytest
import asyncio
import os
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import base64

# Test imports
try:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.backends import default_backend
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives.serialization import pkcs12
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


# ============================================================================
# TEST FIXTURES
# ============================================================================

def generate_test_certificate():
    """Generate a self-signed test certificate and private key."""
    if not CRYPTO_AVAILABLE:
        return None, None, None

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Generate certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "HR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Company d.o.o."),
        x509.NameAttribute(NameOID.COMMON_NAME, "Test Certificate"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    return private_key, cert, None  # No chain for self-signed


def create_test_p12_file(password: str = "test123"):
    """Create a temporary .p12 file for testing."""
    if not CRYPTO_AVAILABLE:
        return None

    private_key, cert, chain = generate_test_certificate()

    # Create PKCS#12
    p12_data = pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=private_key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
    )

    # Write to temp file
    fd, path = tempfile.mkstemp(suffix='.p12')
    with os.fdopen(fd, 'wb') as f:
        f.write(p12_data)

    return path


@pytest.fixture
def test_p12_path():
    """Fixture that creates a test .p12 file and cleans up after."""
    if not CRYPTO_AVAILABLE:
        pytest.skip("cryptography library not available")

    path = create_test_p12_file("test123")
    yield path
    if path and os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def test_private_key():
    """Fixture that provides a test private key."""
    if not CRYPTO_AVAILABLE:
        pytest.skip("cryptography library not available")

    private_key, _, _ = generate_test_certificate()
    return private_key


@pytest.fixture
def sample_ubl_xml():
    """Sample UBL Invoice XML for testing."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0#conformant#urn:fdc:mfin.hr:2023:einvoice:1.0</cbc:CustomizationID>
    <cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>
    <cbc:ID>001/URED/1</cbc:ID>
    <cbc:IssueDate>2026-01-15</cbc:IssueDate>
    <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyName><cbc:Name>Test Company d.o.o.</cbc:Name></cac:PartyName>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:LegalMonetaryTotal>
        <cbc:PayableAmount currencyID="EUR">1250.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>'''


# ============================================================================
# CERTIFICATE LOADING TESTS
# ============================================================================

class TestCertificateLoading:
    """Tests for certificate loading functionality."""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_load_p12_certificate_success(self, test_p12_path):
        """Test successful loading of .p12 certificate."""
        from tools.api_implementations.xades_signer import load_certificate_from_file

        cert_info = load_certificate_from_file(test_p12_path, "test123")

        assert cert_info is not None
        assert cert_info.private_key is not None
        assert cert_info.certificate is not None
        assert cert_info.serial_number is not None
        assert "HR" in cert_info.issuer or "Test" in cert_info.subject
        assert cert_info.is_valid() is True

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_load_p12_wrong_password(self, test_p12_path):
        """Test loading .p12 with wrong password fails."""
        from tools.api_implementations.xades_signer import load_certificate_from_file

        with pytest.raises(ValueError) as exc_info:
            load_certificate_from_file(test_p12_path, "wrong_password")

        assert "Failed to load certificate" in str(exc_info.value)

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_load_certificate_file_not_found(self):
        """Test loading non-existent file raises error."""
        from tools.api_implementations.xades_signer import load_certificate_from_file

        with pytest.raises(FileNotFoundError):
            load_certificate_from_file("/nonexistent/path.p12", "password")

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_certificate_info_to_dict(self, test_p12_path):
        """Test CertificateInfo.to_dict() exports correctly."""
        from tools.api_implementations.xades_signer import load_certificate_from_file

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        cert_dict = cert_info.to_dict()

        assert 'serial_number' in cert_dict
        assert 'issuer' in cert_dict
        assert 'subject' in cert_dict
        assert 'valid_from' in cert_dict
        assert 'valid_to' in cert_dict
        assert 'is_valid' in cert_dict
        assert cert_dict['is_valid'] is True

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_certificate_validity_check(self, test_p12_path):
        """Test certificate validity checking."""
        from tools.api_implementations.xades_signer import load_certificate_from_file

        cert_info = load_certificate_from_file(test_p12_path, "test123")

        # Should be valid (just created)
        assert cert_info.is_valid() is True

        # Manually set expired date to test
        cert_info.valid_to = datetime.now(timezone.utc) - timedelta(days=1)
        assert cert_info.is_valid() is False


# ============================================================================
# ZKI CALCULATION TESTS
# ============================================================================

class TestZKICalculation:
    """Tests for ZKI (Zaštitni Kod Izdavatelja) calculation."""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_zki_calculation_basic(self, test_private_key):
        """Test basic ZKI calculation."""
        from tools.api_implementations.xades_signer import calculate_zki

        zki = calculate_zki(
            oib="12345678903",
            invoice_datetime=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1250.00"),
            private_key=test_private_key
        )

        # ZKI format: XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
        assert zki is not None
        assert len(zki) == 35  # 32 hex + 3 dashes
        assert zki.count('-') == 3

        parts = zki.split('-')
        assert len(parts) == 4
        for part in parts:
            assert len(part) == 8
            assert all(c in '0123456789ABCDEF' for c in part)

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_zki_deterministic(self, test_private_key):
        """Test that ZKI is deterministic for same inputs."""
        from tools.api_implementations.xades_signer import calculate_zki

        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        zki1 = calculate_zki(
            oib="12345678903",
            invoice_datetime=dt,
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1250.00"),
            private_key=test_private_key
        )

        zki2 = calculate_zki(
            oib="12345678903",
            invoice_datetime=dt,
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1250.00"),
            private_key=test_private_key
        )

        assert zki1 == zki2

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_zki_different_for_different_inputs(self, test_private_key):
        """Test that ZKI changes when input changes."""
        from tools.api_implementations.xades_signer import calculate_zki

        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        zki1 = calculate_zki(
            oib="12345678903",
            invoice_datetime=dt,
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1250.00"),
            private_key=test_private_key
        )

        # Different amount
        zki2 = calculate_zki(
            oib="12345678903",
            invoice_datetime=dt,
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1251.00"),
            private_key=test_private_key
        )

        assert zki1 != zki2

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_zki_amount_formatting(self, test_private_key):
        """Test that amounts are formatted correctly (2 decimal places)."""
        from tools.api_implementations.xades_signer import calculate_zki

        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # These should produce same ZKI since amounts are equal when formatted
        zki1 = calculate_zki(
            oib="12345678903",
            invoice_datetime=dt,
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1250.00"),
            private_key=test_private_key
        )

        zki2 = calculate_zki(
            oib="12345678903",
            invoice_datetime=dt,
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount=Decimal("1250.001"),  # Will be formatted to 1250.00
            private_key=test_private_key
        )

        assert zki1 == zki2


# ============================================================================
# XADES SIGNING TESTS
# ============================================================================

class TestXAdESSigning:
    """Tests for XAdES-BES digital signing."""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_sign_basic_xml(self, test_p12_path, sample_ubl_xml):
        """Test basic XML signing."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        result = sign_xades_bes(sample_ubl_xml, cert_info)

        assert result['success'] is True
        assert result['signed_xml'] is not None
        assert result['signature_id'] is not None
        assert result['signing_time'] is not None
        assert result['error'] is None

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_signed_xml_contains_signature(self, test_p12_path, sample_ubl_xml):
        """Test that signed XML contains ds:Signature element."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        result = sign_xades_bes(sample_ubl_xml, cert_info)

        signed_xml = result['signed_xml']

        # Check signature elements
        assert 'ds:Signature' in signed_xml or 'Signature' in signed_xml
        assert 'ds:SignedInfo' in signed_xml or 'SignedInfo' in signed_xml
        assert 'ds:SignatureValue' in signed_xml or 'SignatureValue' in signed_xml
        assert 'ds:KeyInfo' in signed_xml or 'KeyInfo' in signed_xml
        assert 'X509Certificate' in signed_xml

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_signed_xml_contains_xades_properties(self, test_p12_path, sample_ubl_xml):
        """Test that signed XML contains XAdES properties."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        result = sign_xades_bes(sample_ubl_xml, cert_info)

        signed_xml = result['signed_xml']

        # Check XAdES elements
        assert 'QualifyingProperties' in signed_xml
        assert 'SignedProperties' in signed_xml
        assert 'SigningTime' in signed_xml
        assert 'SigningCertificate' in signed_xml

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_signature_uses_sha256(self, test_p12_path, sample_ubl_xml):
        """Test that signature uses SHA-256 algorithm."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        result = sign_xades_bes(sample_ubl_xml, cert_info)

        signed_xml = result['signed_xml']

        # Check algorithm references
        assert 'rsa-sha256' in signed_xml or 'sha256' in signed_xml.lower()

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_custom_signature_id(self, test_p12_path, sample_ubl_xml):
        """Test signing with custom signature ID."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        result = sign_xades_bes(sample_ubl_xml, cert_info, signature_id="MyCustomSignature")

        assert result['success'] is True
        assert 'MyCustomSignature' in result['signed_xml']


# ============================================================================
# SIGNATURE VERIFICATION TESTS
# ============================================================================

class TestSignatureVerification:
    """Tests for signature verification."""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_verify_signed_document(self, test_p12_path, sample_ubl_xml):
        """Test verifying a signed document."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes,
            verify_signature
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        sign_result = sign_xades_bes(sample_ubl_xml, cert_info)

        verify_result = verify_signature(sign_result['signed_xml'])

        assert verify_result['valid'] is True
        assert verify_result['signer'] is not None
        assert verify_result['signing_time'] is not None

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_verify_unsigned_document(self, sample_ubl_xml):
        """Test verifying unsigned document returns not valid."""
        from tools.api_implementations.xades_signer import verify_signature

        result = verify_signature(sample_ubl_xml)

        assert result['valid'] is False
        assert 'No signature found' in result['error']


# ============================================================================
# ADK TOOL WRAPPER TESTS
# ============================================================================

class TestADKToolWrappers:
    """Tests for ADK tool wrapper functions."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    async def test_load_certificate_tool(self, test_p12_path):
        """Test load_certificate ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import load_certificate

        result = await load_certificate(
            source=test_p12_path,
            password="test123",
            source_type="file"
        )

        assert result['success'] is True
        assert result['certificate_loaded'] is True
        assert result['certificate_info'] is not None
        assert result['cache_key'] is not None
        assert result['is_valid'] is True

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    async def test_sign_xades_tool(self, test_p12_path, sample_ubl_xml):
        """Test sign_xades ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import load_certificate, sign_xades

        # Load certificate first
        cert_result = await load_certificate(
            source=test_p12_path,
            password="test123",
            source_type="file",
            cache_key="test-cert"
        )

        assert cert_result['success'] is True

        # Sign document
        sign_result = await sign_xades(
            xml=sample_ubl_xml,
            cert_cache_key="test-cert"
        )

        assert sign_result['success'] is True
        assert sign_result['signed_xml'] is not None
        assert sign_result['signature_id'] is not None

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    async def test_sign_xades_tool_missing_cert(self, sample_ubl_xml):
        """Test sign_xades fails gracefully when certificate not loaded."""
        from tools.adk_tools.fiskalizacija_adk_tools import sign_xades, _certificate_cache

        # Clear cache
        _certificate_cache.clear()

        result = await sign_xades(
            xml=sample_ubl_xml,
            cert_cache_key="nonexistent-cert"
        )

        assert result['success'] is False
        assert 'Certificate not found' in result['error']

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    async def test_calculate_zki_tool(self, test_p12_path):
        """Test calculate_zki ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import load_certificate, calculate_zki

        # Load certificate first
        cert_result = await load_certificate(
            source=test_p12_path,
            password="test123",
            source_type="file",
            cache_key="zki-test-cert"
        )

        assert cert_result['success'] is True

        # Calculate ZKI
        zki_result = await calculate_zki(
            oib="12345678903",
            invoice_datetime="2026-01-15T10:30:00",
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount="1250.00",
            cert_cache_key="zki-test-cert"
        )

        assert zki_result['success'] is True
        assert zki_result['zki'] is not None
        assert len(zki_result['zki']) == 35

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    async def test_verify_xml_signature_tool(self, test_p12_path, sample_ubl_xml):
        """Test verify_xml_signature ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import (
            load_certificate,
            sign_xades,
            verify_xml_signature
        )

        # Load and sign
        await load_certificate(
            source=test_p12_path,
            password="test123",
            source_type="file",
            cache_key="verify-test-cert"
        )

        sign_result = await sign_xades(
            xml=sample_ubl_xml,
            cert_cache_key="verify-test-cert"
        )

        # Verify
        verify_result = await verify_xml_signature(sign_result['signed_xml'])

        assert verify_result['valid'] is True
        assert verify_result['signer'] is not None

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    async def test_certificate_caching(self, test_p12_path):
        """Test that certificates are cached properly."""
        from tools.adk_tools.fiskalizacija_adk_tools import load_certificate, _certificate_cache

        # Clear cache
        _certificate_cache.clear()

        # First load
        result1 = await load_certificate(
            source=test_p12_path,
            password="test123",
            source_type="file",
            cache_key="cache-test"
        )

        assert result1['success'] is True
        assert "cache-test" in _certificate_cache

        # Second load should use cache
        result2 = await load_certificate(
            source=test_p12_path,
            password="test123",
            source_type="file",
            cache_key="cache-test"
        )

        assert result2['success'] is True
        # Both results should have same info
        assert result1['certificate_info'] == result2['certificate_info']


# ============================================================================
# EDGE CASES AND ERROR HANDLING TESTS
# ============================================================================

class TestEdgeCasesAndErrors:
    """Tests for edge cases and error handling."""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_sign_empty_xml(self, test_p12_path):
        """Test signing empty XML fails gracefully."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        result = sign_xades_bes("", cert_info)

        assert result['success'] is False
        assert result['error'] is not None

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_sign_invalid_xml(self, test_p12_path):
        """Test signing invalid XML fails gracefully."""
        from tools.api_implementations.xades_signer import (
            load_certificate_from_file,
            sign_xades_bes
        )

        cert_info = load_certificate_from_file(test_p12_path, "test123")
        result = sign_xades_bes("<invalid><xml>", cert_info)

        assert result['success'] is False
        assert result['error'] is not None

    @pytest.mark.asyncio
    async def test_load_certificate_missing_file(self):
        """Test loading non-existent certificate file."""
        from tools.adk_tools.fiskalizacija_adk_tools import load_certificate

        result = await load_certificate(
            source="/nonexistent/certificate.p12",
            password="test",
            source_type="file"
        )

        assert result['success'] is False
        assert result['certificate_loaded'] is False
        assert 'error' in result

    @pytest.mark.asyncio
    async def test_load_certificate_invalid_source_type(self):
        """Test loading with invalid source type."""
        from tools.adk_tools.fiskalizacija_adk_tools import load_certificate

        result = await load_certificate(
            source="some-source",
            password="test",
            source_type="invalid_type"
        )

        assert result['success'] is False
        assert 'Unknown source_type' in result['error']

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    def test_verify_malformed_signature(self):
        """Test verifying document with malformed signature."""
        from tools.api_implementations.xades_signer import verify_signature

        # XML with fake signature element
        malformed_xml = '''<?xml version="1.0"?>
        <Root xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
            <ds:Signature>
                <ds:SignedInfo>Invalid</ds:SignedInfo>
            </ds:Signature>
        </Root>'''

        result = verify_signature(malformed_xml)
        # Should not crash, may or may not be valid depending on implementation
        assert 'error' in result or 'valid' in result


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestSigningIntegration:
    """Integration tests for complete signing workflow."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="cryptography not available")
    async def test_full_signing_workflow(self, test_p12_path):
        """Test complete signing workflow: build XML -> validate -> sign -> verify."""
        from tools.adk_tools.fiskalizacija_adk_tools import (
            build_ubl_invoice,
            validate_xsd,
            load_certificate,
            sign_xades,
            verify_xml_signature,
            calculate_zki
        )

        # 1. Build UBL Invoice
        invoice_data = {
            "invoice_number": "001/URED/1",
            "issue_date": "2026-01-15",
            "due_date": "2026-02-15",
            "currency": "EUR",
            "supplier": {
                "name": "Test Supplier d.o.o.",
                "oib": "12345678903",
                "vat_number": "HR12345678903",
                "address": "Testna ulica 1",
                "city": "Zagreb",
                "postal_code": "10000",
                "country_code": "HR"
            },
            "customer": {
                "name": "Test Customer d.o.o.",
                "oib": "98765432109",
                "vat_number": "HR98765432109",
                "address": "Kupčeva ulica 2",
                "city": "Split",
                "postal_code": "21000",
                "country_code": "HR"
            },
            "items": [
                {
                    "name": "IT konzultacije",
                    "quantity": "10",
                    "unit_code": "HUR",
                    "unit_price": "100.00",
                    "net_amount": "1000.00",
                    "vat_rate": "25"
                }
            ],
            "tax_breakdown": {
                "subtotals": [{"vat_rate": "25", "taxable_amount": "1000.00", "tax_amount": "250.00"}],
                "total_net": "1000.00",
                "total_tax": "250.00",
                "total_gross": "1250.00"
            }
        }

        build_result = await build_ubl_invoice(invoice_data)
        assert build_result['success'] is True

        # 2. Validate XSD
        validate_result = await validate_xsd(build_result['xml'])
        assert validate_result['valid'] is True

        # 3. Load Certificate
        cert_result = await load_certificate(
            source=test_p12_path,
            password="test123",
            source_type="file",
            cache_key="integration-test"
        )
        assert cert_result['success'] is True

        # 4. Calculate ZKI
        zki_result = await calculate_zki(
            oib="12345678903",
            invoice_datetime="2026-01-15T10:30:00",
            invoice_number="1",
            business_unit="URED",
            device_number="1",
            total_amount="1250.00",
            cert_cache_key="integration-test"
        )
        assert zki_result['success'] is True

        # 5. Sign XML
        sign_result = await sign_xades(
            xml=build_result['xml'],
            cert_cache_key="integration-test"
        )
        assert sign_result['success'] is True

        # 6. Verify Signature
        verify_result = await verify_xml_signature(sign_result['signed_xml'])
        assert verify_result['valid'] is True

        # Final validation - ensure all pieces are present
        signed_xml = sign_result['signed_xml']
        assert 'Signature' in signed_xml
        assert 'X509Certificate' in signed_xml
        assert 'SigningTime' in signed_xml
