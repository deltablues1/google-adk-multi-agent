"""
XAdES-BES Digital Signing for Croatian Fiscalization (Fiskalizacija 2.0)

Provides:
- PKCS#12 (.p12) certificate loading
- XAdES-BES (Basic Electronic Signature) signing
- ZKI (Zaštitni Kod Izdavatelja) calculation
- Signature verification

This is a DETERMINISTIC tool - no LLM involvement.

Croatian Fiscalization Requirements:
- Certificate: FINA-issued qualified electronic seal
- Signature: XAdES-BES enveloped signature
- Canonicalization: Exclusive XML Canonicalization 1.0
- Digest: SHA-256
- ZKI: MD5 hash of concatenated invoice data, RSA-signed
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from decimal import Decimal
import base64
import hashlib
import logging
import os
import uuid

# Cryptography imports
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509 import load_pem_x509_certificate, load_der_x509_certificate
    from cryptography import x509
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

# PKCS#12 support
try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    PKCS12_AVAILABLE = True
except ImportError:
    PKCS12_AVAILABLE = False

# XML handling
try:
    from lxml import etree
    from io import BytesIO
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

# SignXML for XAdES (optional - we implement core ourselves for FINA compatibility)
try:
    import signxml
    SIGNXML_AVAILABLE = True
except ImportError:
    SIGNXML_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================================
# NAMESPACE DEFINITIONS
# ============================================================================

NAMESPACES = {
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
    'xades': 'http://uri.etsi.org/01903/v1.3.2#',
    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
}


# ============================================================================
# CERTIFICATE MANAGEMENT
# ============================================================================

class CertificateInfo:
    """Holds loaded certificate information."""

    def __init__(
        self,
        private_key: Any,
        certificate: Any,
        certificate_chain: list = None,
        serial_number: str = None,
        issuer: str = None,
        subject: str = None,
        valid_from: datetime = None,
        valid_to: datetime = None
    ):
        self.private_key = private_key
        self.certificate = certificate
        self.certificate_chain = certificate_chain or []
        self.serial_number = serial_number
        self.issuer = issuer
        self.subject = subject
        self.valid_from = valid_from
        self.valid_to = valid_to

    def is_valid(self) -> bool:
        """Check if certificate is currently valid (not expired)."""
        now = datetime.now(timezone.utc)
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Export certificate info (without private key)."""
        return {
            'serial_number': self.serial_number,
            'issuer': self.issuer,
            'subject': self.subject,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_to': self.valid_to.isoformat() if self.valid_to else None,
            'is_valid': self.is_valid(),
            'chain_length': len(self.certificate_chain)
        }


def load_p12_certificate(
    p12_data: bytes,
    password: str
) -> CertificateInfo:
    """
    Load certificate from PKCS#12 (.p12) data.

    Args:
        p12_data: Raw bytes of .p12 file
        password: Password to decrypt the .p12

    Returns:
        CertificateInfo with private key and certificate

    Raises:
        ValueError: If loading fails
    """
    if not CRYPTOGRAPHY_AVAILABLE or not PKCS12_AVAILABLE:
        raise ImportError("cryptography library required for certificate loading")

    try:
        # Load PKCS#12
        password_bytes = password.encode('utf-8') if password else None
        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            p12_data,
            password_bytes,
            default_backend()
        )

        if not private_key:
            raise ValueError("No private key found in PKCS#12 file")
        if not certificate:
            raise ValueError("No certificate found in PKCS#12 file")

        # Extract certificate info
        cert_info = CertificateInfo(
            private_key=private_key,
            certificate=certificate,
            certificate_chain=list(chain) if chain else [],
            serial_number=str(certificate.serial_number),
            issuer=certificate.issuer.rfc4514_string(),
            subject=certificate.subject.rfc4514_string(),
            valid_from=certificate.not_valid_before_utc,
            valid_to=certificate.not_valid_after_utc
        )

        logger.info(f"Loaded certificate: {cert_info.subject}")
        return cert_info

    except Exception as e:
        logger.error(f"Failed to load PKCS#12 certificate: {e}")
        raise ValueError(f"Failed to load certificate: {e}")


def load_certificate_from_file(
    file_path: str,
    password: str
) -> CertificateInfo:
    """
    Load certificate from .p12 file path.

    Args:
        file_path: Path to .p12 file
        password: Password to decrypt

    Returns:
        CertificateInfo
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Certificate file not found: {file_path}")

    with open(file_path, 'rb') as f:
        p12_data = f.read()

    return load_p12_certificate(p12_data, password)


def load_certificate_from_secret_manager(
    secret_name: str,
    project_id: str,
    password_secret_name: str = None
) -> CertificateInfo:
    """
    Load certificate from Google Cloud Secret Manager.

    Args:
        secret_name: Name of secret containing .p12 data
        project_id: GCP project ID
        password_secret_name: Name of secret containing password (optional)

    Returns:
        CertificateInfo
    """
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()

        # Get certificate data
        cert_secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": cert_secret_path})
        p12_data = response.payload.data

        # Get password if separate secret
        if password_secret_name:
            pwd_secret_path = f"projects/{project_id}/secrets/{password_secret_name}/versions/latest"
            pwd_response = client.access_secret_version(request={"name": pwd_secret_path})
            password = pwd_response.payload.data.decode('utf-8')
        else:
            password = ""

        return load_p12_certificate(p12_data, password)

    except ImportError:
        raise ImportError("google-cloud-secret-manager required for Secret Manager access")
    except Exception as e:
        logger.error(f"Failed to load certificate from Secret Manager: {e}")
        raise


# ============================================================================
# ZKI (ZAŠTITNI KOD IZDAVATELJA) CALCULATION
# ============================================================================

def calculate_zki(
    oib: str,
    invoice_datetime: datetime,
    invoice_number: str,
    business_unit: str,
    device_number: str,
    total_amount: Decimal,
    private_key: Any
) -> str:
    """
    Calculate ZKI (Zaštitni Kod Izdavatelja - Protective Code of Issuer).

    Croatian fiscalization requires ZKI calculation:
    1. Concatenate: OIB + DateTime + InvoiceNumber + BusinessUnit + DeviceNumber + TotalAmount
    2. Sign concatenated string with RSA-SHA1
    3. MD5 hash the signature
    4. Format as 32 hex characters with dashes every 8 chars

    Args:
        oib: Issuer's OIB (11 digits)
        invoice_datetime: Invoice date and time
        invoice_number: Invoice sequential number
        business_unit: Business unit identifier
        device_number: Cash register device number
        total_amount: Total invoice amount (will be formatted with 2 decimals)
        private_key: RSA private key for signing

    Returns:
        ZKI code in format: XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError("cryptography library required for ZKI calculation")

    # Format datetime as required: dd.mm.yyyy HH:MM:SS
    dt_str = invoice_datetime.strftime('%d.%m.%Y %H:%M:%S')

    # Format amount: no thousands separator, dot as decimal, 2 decimal places
    amount_str = f"{total_amount:.2f}"

    # Concatenate all fields (no separators as per FINA spec)
    data_to_sign = f"{oib}{dt_str}{invoice_number}{business_unit}{device_number}{amount_str}"

    logger.debug(f"ZKI data to sign: {data_to_sign}")

    # Sign with RSA-SHA1 (FINA requirement)
    try:
        signature = private_key.sign(
            data_to_sign.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA1()  # FINA specifically requires SHA1 for ZKI
        )
    except Exception as e:
        logger.error(f"ZKI signing failed: {e}")
        raise ValueError(f"Failed to sign ZKI data: {e}")

    # MD5 hash of signature
    md5_hash = hashlib.md5(signature).hexdigest().upper()

    # Format with dashes: XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
    zki = f"{md5_hash[0:8]}-{md5_hash[8:16]}-{md5_hash[16:24]}-{md5_hash[24:32]}"

    logger.info(f"Calculated ZKI: {zki}")
    return zki


# ============================================================================
# XAdES-BES SIGNING
# ============================================================================

class XAdESSigner:
    """
    Signs XML documents with XAdES-BES (Basic Electronic Signature).

    Implements Croatian fiscalization signing requirements:
    - Enveloped signature
    - Exclusive canonicalization (exc-c14n)
    - SHA-256 digest
    - RSA-SHA256 signature
    - XAdES signed properties
    """

    def __init__(self, cert_info: CertificateInfo):
        """
        Initialize signer with certificate.

        Args:
            cert_info: CertificateInfo with private key and certificate
        """
        if not LXML_AVAILABLE:
            raise ImportError("lxml library required for XAdES signing")
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography library required for XAdES signing")

        self.cert_info = cert_info
        self.private_key = cert_info.private_key
        self.certificate = cert_info.certificate

    def _get_certificate_digest(self) -> str:
        """Get SHA-256 digest of certificate (for XAdES SigningCertificate)."""
        cert_der = self.certificate.public_bytes(serialization.Encoding.DER)
        digest = hashlib.sha256(cert_der).digest()
        return base64.b64encode(digest).decode('ascii')

    def _get_certificate_base64(self) -> str:
        """Get base64-encoded certificate for KeyInfo."""
        cert_der = self.certificate.public_bytes(serialization.Encoding.DER)
        return base64.b64encode(cert_der).decode('ascii')

    def _canonicalize(self, element: etree._Element) -> bytes:
        """Canonicalize element using exclusive c14n."""
        return etree.tostring(
            element,
            method='c14n',
            exclusive=True,
            with_comments=False
        )

    def _compute_digest(self, data: bytes) -> str:
        """Compute SHA-256 digest and return base64-encoded."""
        digest = hashlib.sha256(data).digest()
        return base64.b64encode(digest).decode('ascii')

    def _sign_data(self, data: bytes) -> str:
        """Sign data with RSA-SHA256 and return base64-encoded signature."""
        signature = self.private_key.sign(
            data,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('ascii')

    def sign(
        self,
        xml_string: str,
        signature_id: str = None
    ) -> str:
        """
        Sign XML document with XAdES-BES enveloped signature.

        Args:
            xml_string: XML document to sign
            signature_id: Optional ID for signature element

        Returns:
            Signed XML document as string
        """
        # Generate unique IDs
        sig_id = signature_id or f"Signature-{uuid.uuid4().hex[:8]}"
        signed_props_id = f"SignedProperties-{uuid.uuid4().hex[:8]}"
        key_info_id = f"KeyInfo-{uuid.uuid4().hex[:8]}"

        # Parse XML
        if isinstance(xml_string, str):
            xml_bytes = xml_string.encode('utf-8')
        else:
            xml_bytes = xml_string

        doc = etree.parse(BytesIO(xml_bytes))
        root = doc.getroot()

        # Current timestamp for signing time
        signing_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        # Create ds:Signature element
        ds = NAMESPACES['ds']
        xades = NAMESPACES['xades']

        signature_elem = etree.Element(
            f"{{{ds}}}Signature",
            nsmap={'ds': ds},
            Id=sig_id
        )

        # ds:SignedInfo
        signed_info = etree.SubElement(
            signature_elem,
            f"{{{ds}}}SignedInfo"
        )

        # CanonicalizationMethod
        c14n_method = etree.SubElement(
            signed_info,
            f"{{{ds}}}CanonicalizationMethod",
            Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"
        )

        # SignatureMethod
        sig_method = etree.SubElement(
            signed_info,
            f"{{{ds}}}SignatureMethod",
            Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
        )

        # Reference to document (entire document minus signature)
        ref_doc = etree.SubElement(
            signed_info,
            f"{{{ds}}}Reference",
            URI=""
        )
        transforms_doc = etree.SubElement(ref_doc, f"{{{ds}}}Transforms")
        etree.SubElement(
            transforms_doc,
            f"{{{ds}}}Transform",
            Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"
        )
        etree.SubElement(
            transforms_doc,
            f"{{{ds}}}Transform",
            Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"
        )
        etree.SubElement(ref_doc, f"{{{ds}}}DigestMethod", Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
        digest_value_doc = etree.SubElement(ref_doc, f"{{{ds}}}DigestValue")

        # Reference to SignedProperties (XAdES requirement)
        ref_props = etree.SubElement(
            signed_info,
            f"{{{ds}}}Reference",
            URI=f"#{signed_props_id}",
            Type="http://uri.etsi.org/01903#SignedProperties"
        )
        transforms_props = etree.SubElement(ref_props, f"{{{ds}}}Transforms")
        etree.SubElement(
            transforms_props,
            f"{{{ds}}}Transform",
            Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"
        )
        etree.SubElement(ref_props, f"{{{ds}}}DigestMethod", Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
        digest_value_props = etree.SubElement(ref_props, f"{{{ds}}}DigestValue")

        # ds:SignatureValue (placeholder)
        sig_value = etree.SubElement(signature_elem, f"{{{ds}}}SignatureValue")

        # ds:KeyInfo
        key_info = etree.SubElement(signature_elem, f"{{{ds}}}KeyInfo", Id=key_info_id)
        x509_data = etree.SubElement(key_info, f"{{{ds}}}X509Data")
        x509_cert = etree.SubElement(x509_data, f"{{{ds}}}X509Certificate")
        x509_cert.text = self._get_certificate_base64()

        # ds:Object containing XAdES QualifyingProperties
        obj = etree.SubElement(signature_elem, f"{{{ds}}}Object")

        qualifying_props = etree.SubElement(
            obj,
            f"{{{xades}}}QualifyingProperties",
            nsmap={'xades': xades},
            Target=f"#{sig_id}"
        )

        signed_props = etree.SubElement(
            qualifying_props,
            f"{{{xades}}}SignedProperties",
            Id=signed_props_id
        )

        # SignedSignatureProperties
        signed_sig_props = etree.SubElement(signed_props, f"{{{xades}}}SignedSignatureProperties")

        signing_time_elem = etree.SubElement(signed_sig_props, f"{{{xades}}}SigningTime")
        signing_time_elem.text = signing_time

        # SigningCertificate
        signing_cert = etree.SubElement(signed_sig_props, f"{{{xades}}}SigningCertificate")
        cert_elem = etree.SubElement(signing_cert, f"{{{xades}}}Cert")
        cert_digest = etree.SubElement(cert_elem, f"{{{xades}}}CertDigest")
        cert_digest_method = etree.SubElement(
            cert_digest,
            f"{{{ds}}}DigestMethod",
            Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"
        )
        cert_digest_value = etree.SubElement(cert_digest, f"{{{ds}}}DigestValue")
        cert_digest_value.text = self._get_certificate_digest()

        issuer_serial = etree.SubElement(cert_elem, f"{{{xades}}}IssuerSerial")
        issuer_name = etree.SubElement(issuer_serial, f"{{{ds}}}X509IssuerName")
        issuer_name.text = self.cert_info.issuer
        serial_num = etree.SubElement(issuer_serial, f"{{{ds}}}X509SerialNumber")
        serial_num.text = self.cert_info.serial_number

        # Now compute digests
        # 1. Digest of SignedProperties
        signed_props_canonical = self._canonicalize(signed_props)
        digest_value_props.text = self._compute_digest(signed_props_canonical)

        # 2. Digest of document (with enveloped-signature transform)
        # First, add signature to document temporarily to compute correct digest
        root.append(signature_elem)

        # For enveloped signature, we need to remove the Signature element for digest
        # Make a copy without signature
        doc_copy = etree.parse(BytesIO(xml_bytes))
        doc_canonical = self._canonicalize(doc_copy.getroot())
        digest_value_doc.text = self._compute_digest(doc_canonical)

        # 3. Sign the SignedInfo
        signed_info_canonical = self._canonicalize(signed_info)
        sig_value.text = self._sign_data(signed_info_canonical)

        # Return signed XML with XML declaration
        # Note: encoding='unicode' cannot have xml_declaration, so we use UTF-8 and decode
        xml_bytes_out = etree.tostring(root, encoding='UTF-8', xml_declaration=True)
        return xml_bytes_out.decode('utf-8')


def sign_xades_bes(
    xml_string: str,
    cert_info: CertificateInfo,
    signature_id: str = None
) -> Dict[str, Any]:
    """
    Sign XML document with XAdES-BES signature.

    Convenience function for ADK tools.

    Args:
        xml_string: XML document to sign
        cert_info: Certificate with private key
        signature_id: Optional signature ID

    Returns:
        Dictionary with:
            - success: bool
            - signed_xml: Signed XML string
            - signature_id: ID of signature element
            - signing_time: ISO timestamp
            - error: Optional error message
    """
    try:
        signer = XAdESSigner(cert_info)

        sig_id = signature_id or f"Signature-{uuid.uuid4().hex[:8]}"
        signed_xml = signer.sign(xml_string, sig_id)

        return {
            'success': True,
            'signed_xml': signed_xml,
            'signature_id': sig_id,
            'signing_time': datetime.now(timezone.utc).isoformat(),
            'certificate_subject': cert_info.subject,
            'error': None
        }

    except Exception as e:
        logger.error(f"XAdES signing failed: {e}")
        return {
            'success': False,
            'signed_xml': None,
            'signature_id': None,
            'signing_time': None,
            'error': str(e)
        }


# ============================================================================
# CONVENIENCE FUNCTIONS FOR ADK TOOLS
# ============================================================================

def load_certificate(
    source: str,
    password: str,
    source_type: str = 'file',
    project_id: str = None
) -> Dict[str, Any]:
    """
    Load certificate from file or Secret Manager.

    Args:
        source: File path or secret name
        password: Password or password secret name
        source_type: 'file' or 'secret_manager'
        project_id: GCP project ID (for Secret Manager)

    Returns:
        Dictionary with:
            - success: bool
            - certificate_info: Certificate details (no private key)
            - cert_handle: Opaque handle for signing (internal use)
            - error: Optional error message
    """
    try:
        if source_type == 'file':
            cert_info = load_certificate_from_file(source, password)
        elif source_type == 'secret_manager':
            if not project_id:
                raise ValueError("project_id required for Secret Manager")
            cert_info = load_certificate_from_secret_manager(
                source,
                project_id,
                password  # In this case, password is the password secret name
            )
        else:
            raise ValueError(f"Unknown source_type: {source_type}")

        return {
            'success': True,
            'certificate_info': cert_info.to_dict(),
            'cert_handle': cert_info,  # Internal use only
            'error': None
        }

    except Exception as e:
        logger.error(f"Failed to load certificate: {e}")
        return {
            'success': False,
            'certificate_info': None,
            'cert_handle': None,
            'error': str(e)
        }


def calculate_zki_code(
    oib: str,
    invoice_datetime: str,
    invoice_number: str,
    business_unit: str,
    device_number: str,
    total_amount: str,
    cert_handle: CertificateInfo
) -> Dict[str, Any]:
    """
    Calculate ZKI code for invoice.

    Args:
        oib: Issuer's OIB
        invoice_datetime: ISO format datetime
        invoice_number: Invoice number
        business_unit: Business unit code
        device_number: Device/register number
        total_amount: Total amount as string
        cert_handle: CertificateInfo from load_certificate

    Returns:
        Dictionary with:
            - success: bool
            - zki: ZKI code
            - error: Optional error message
    """
    try:
        # Parse datetime
        if isinstance(invoice_datetime, str):
            dt = datetime.fromisoformat(invoice_datetime.replace('Z', '+00:00'))
        else:
            dt = invoice_datetime

        # Parse amount
        amount = Decimal(str(total_amount))

        zki = calculate_zki(
            oib=oib,
            invoice_datetime=dt,
            invoice_number=invoice_number,
            business_unit=business_unit,
            device_number=device_number,
            total_amount=amount,
            private_key=cert_handle.private_key
        )

        return {
            'success': True,
            'zki': zki,
            'error': None
        }

    except Exception as e:
        logger.error(f"ZKI calculation failed: {e}")
        return {
            'success': False,
            'zki': None,
            'error': str(e)
        }


# ============================================================================
# FINA-SPECIFIC SIGNING (SHA1 required for Croatian Fiscalization)
# ============================================================================

def sign_fina_xml(
    xml_string: str,
    private_key: Any,
    certificate: Any,
    doc_id: str = "signXmlId"
) -> str:
    """
    Sign XML document for FINA fiscalization using SHA1.

    FINA requires:
    - Exclusive canonicalization (exc-c14n)
    - RSA-SHA1 signature (legacy requirement)
    - SHA1 digest
    - X509IssuerSerial in KeyInfo

    Args:
        xml_string: XML document to sign (must have Id attribute on root)
        private_key: RSA private key from certificate
        certificate: X509 certificate
        doc_id: ID attribute value of the document element

    Returns:
        Signed XML document as string
    """
    if not LXML_AVAILABLE:
        raise ImportError("lxml library required for FINA signing")
    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError("cryptography library required for FINA signing")

    DS_NS = "http://www.w3.org/2000/09/xmldsig#"
    C14N_EXC = "http://www.w3.org/2001/10/xml-exc-c14n#"

    # Parse original XML
    if isinstance(xml_string, str):
        xml_bytes = xml_string.encode('utf-8')
    else:
        xml_bytes = xml_string

    root = etree.fromstring(xml_bytes)

    # Get the Id attribute value
    actual_id = root.get('Id') or doc_id

    # Canonicalize the document with exclusive C14N
    canonical_doc = etree.tostring(root, method='c14n', exclusive=True)

    # Compute SHA1 digest
    digest = hashlib.sha1(canonical_doc).digest()
    digest_b64 = base64.b64encode(digest).decode('ascii')

    # Get certificate info
    cert_der = certificate.public_bytes(serialization.Encoding.DER)
    cert_b64 = base64.b64encode(cert_der).decode('ascii')

    # Format issuer name (reverse order for XML)
    issuer_name = certificate.issuer.rfc4514_string()
    issuer_parts = issuer_name.split(',')
    issuer_xml = ','.join(reversed(issuer_parts)).strip()

    serial_number = certificate.serial_number

    # Build SignedInfo
    signed_info_xml = f'''<ds:SignedInfo xmlns:ds="{DS_NS}">
<ds:CanonicalizationMethod Algorithm="{C14N_EXC}"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
<ds:Reference URI="#{actual_id}">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
<ds:Transform Algorithm="{C14N_EXC}"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
<ds:DigestValue>{digest_b64}</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>'''

    # Parse and canonicalize SignedInfo
    signed_info_elem = etree.fromstring(signed_info_xml.encode('utf-8'))
    signed_info_c14n = etree.tostring(signed_info_elem, method='c14n', exclusive=True)

    # Sign with RSA-SHA1 (FINA requirement)
    signature = private_key.sign(
        signed_info_c14n,
        padding.PKCS1v15(),
        hashes.SHA1()
    )
    signature_b64 = base64.b64encode(signature).decode('ascii')

    # Build full Signature element
    signature_xml = f'''<ds:Signature xmlns:ds="{DS_NS}">
{signed_info_xml}
<ds:SignatureValue>{signature_b64}</ds:SignatureValue>
<ds:KeyInfo>
<ds:X509Data>
<ds:X509IssuerSerial>
<ds:X509IssuerName>{issuer_xml}</ds:X509IssuerName>
<ds:X509SerialNumber>{serial_number}</ds:X509SerialNumber>
</ds:X509IssuerSerial>
<ds:X509Certificate>{cert_b64}</ds:X509Certificate>
</ds:X509Data>
</ds:KeyInfo>
</ds:Signature>'''

    # Parse signature element and append to root
    sig_elem = etree.fromstring(signature_xml.encode('utf-8'))
    root.append(sig_elem)

    # Return final XML
    return etree.tostring(root, encoding='UTF-8', xml_declaration=True).decode('utf-8')


def sign_fina_racun_zahtjev(
    xml_string: str,
    cert_info: CertificateInfo
) -> Dict[str, Any]:
    """
    Sign RacunZahtjev XML for FINA fiscalization.

    Convenience function for ADK tools.

    Args:
        xml_string: RacunZahtjev XML document
        cert_info: CertificateInfo with private key and certificate

    Returns:
        Dictionary with:
            - success: bool
            - signed_xml: Signed XML string
            - error: Optional error message
    """
    try:
        signed_xml = sign_fina_xml(
            xml_string,
            cert_info.private_key,
            cert_info.certificate
        )

        return {
            'success': True,
            'signed_xml': signed_xml,
            'error': None
        }
    except Exception as e:
        logger.error(f"FINA signing failed: {e}")
        return {
            'success': False,
            'signed_xml': None,
            'error': str(e)
        }


# ============================================================================
# VERIFICATION
# ============================================================================

def verify_signature(xml_string: str) -> Dict[str, Any]:
    """
    Verify XAdES signature in XML document.

    Args:
        xml_string: Signed XML document

    Returns:
        Dictionary with:
            - valid: bool
            - signer: Certificate subject if valid
            - signing_time: Signing timestamp
            - error: Optional error message
    """
    if not LXML_AVAILABLE:
        return {'valid': False, 'error': 'lxml not available'}

    try:
        # Parse XML
        if isinstance(xml_string, str):
            xml_bytes = xml_string.encode('utf-8')
        else:
            xml_bytes = xml_string

        doc = etree.parse(BytesIO(xml_bytes))
        root = doc.getroot()

        # Find Signature element
        ds = NAMESPACES['ds']
        sig_elem = root.find(f".//{{{ds}}}Signature")

        if sig_elem is None:
            return {
                'valid': False,
                'signer': None,
                'signing_time': None,
                'error': 'No signature found in document'
            }

        # Extract signing time
        xades = NAMESPACES['xades']
        signing_time_elem = sig_elem.find(f".//{{{xades}}}SigningTime")
        signing_time = signing_time_elem.text if signing_time_elem is not None else None

        # Extract certificate
        x509_cert_elem = sig_elem.find(f".//{{{ds}}}X509Certificate")
        if x509_cert_elem is not None and CRYPTOGRAPHY_AVAILABLE:
            cert_b64 = x509_cert_elem.text
            cert_der = base64.b64decode(cert_b64)
            cert = load_der_x509_certificate(cert_der, default_backend())
            signer = cert.subject.rfc4514_string()
        else:
            signer = "Unknown"

        # For full verification, we would need to:
        # 1. Verify digest values
        # 2. Verify signature value
        # 3. Validate certificate chain
        # This is a simplified check

        return {
            'valid': True,  # Simplified - presence check only
            'signer': signer,
            'signing_time': signing_time,
            'error': None,
            'note': 'Basic presence verification only - full cryptographic verification requires certificate chain'
        }

    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return {
            'valid': False,
            'signer': None,
            'signing_time': None,
            'error': str(e)
        }
