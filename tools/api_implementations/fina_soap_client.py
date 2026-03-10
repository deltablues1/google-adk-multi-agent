"""
FINA SOAP Client for Croatian Fiscalization (Fiskalizacija 2.0)

Provides:
- SOAP communication with FINA CIS (Central Information System)
- mTLS (mutual TLS) authentication
- Circuit breaker pattern for resilience
- Response parsing (JIR extraction)
- Error handling with Croatian error codes

FINA Endpoints:
- Sandbox: https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest
- Production: https://cis.porezna-uprava.hr:8449/FiskalizacijaService

This is a DETERMINISTIC tool - no LLM involvement.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import logging
import time
import hashlib
import base64
import re

# HTTP/SOAP
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# XML handling
try:
    from lxml import etree
    from io import BytesIO
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

# QR Code
try:
    import qrcode
    import qrcode.image.svg
    QRCODE_AVAILABLE = True
except ImportError:
    qrcode = None
    QRCODE_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

class FINAEnvironment(Enum):
    """FINA service environments."""
    SANDBOX = "sandbox"
    PRODUCTION = "production"


FINA_ENDPOINTS = {
    FINAEnvironment.SANDBOX: "https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest",
    FINAEnvironment.PRODUCTION: "https://cis.porezna-uprava.hr:8449/FiskalizacijaService"
}

FINA_NAMESPACES = {
    'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
    'fis': 'http://www.apis-it.hr/fin/2012/types/f73',
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
}

# Croatian fiscalization error codes
FINA_ERROR_CODES = {
    # Format errors (s00xx)
    "s001": "Neispravan format XML poruke",
    "s002": "Neispravna XML shema",
    "s003": "Neispravan digitalni potpis",
    "s004": "Neispravna vremenska oznaka",
    "s005": "Certifikat nije valjan",

    # Business errors (p00xx)
    "p001": "Neispravan OIB",
    "p002": "OIB nije registriran za fiskalizaciju",
    "p003": "Poslovni prostor nije prijavljen",
    "p004": "Naplatni uređaj nije prijavljen",
    "p005": "Duplicirani broj računa",
    "p006": "Neispravan ZKI",
    "p007": "Račun već fiskaliziran",

    # System errors (t00xx)
    "t001": "Sustav trenutno nije dostupan",
    "t002": "Prekoračen broj zahtjeva",
    "t003": "Interna greška sustava",
}

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2  # seconds
RETRY_STATUS_CODES = [502, 503, 504]  # 500 removed - FINA uses 500 for business errors

# Circuit breaker configuration
CIRCUIT_BREAKER_THRESHOLD = 5  # failures before opening
CIRCUIT_BREAKER_TIMEOUT = 60  # seconds before half-open


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================

class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents cascading failures by stopping requests to a failing service.
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        recovery_timeout: int = CIRCUIT_BREAKER_TIMEOUT
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED

    def record_success(self) -> None:
        """Record a successful request."""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        logger.debug("Circuit breaker: success recorded, state=CLOSED")

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                f"Circuit breaker: OPEN after {self.failure_count} failures"
            )

    def can_execute(self) -> Tuple[bool, str]:
        """
        Check if a request can be executed.

        Returns:
            Tuple of (can_execute: bool, reason: str)
        """
        if self.state == CircuitBreakerState.CLOSED:
            return True, "Circuit closed"

        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker: HALF_OPEN, testing recovery")
                    return True, "Circuit half-open, testing"

            return False, f"Circuit breaker OPEN, retry after {self.recovery_timeout}s"

        # HALF_OPEN - allow one request to test
        return True, "Circuit half-open, testing"

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "recovery_timeout_seconds": self.recovery_timeout
        }


# Global circuit breaker instance
_circuit_breaker = CircuitBreaker()


# ============================================================================
# SOAP MESSAGE BUILDER
# ============================================================================

def build_fiscalization_request(
    signed_racun_zahtjev_xml: str,
    message_id: str = None
) -> str:
    """
    Build SOAP envelope for fiscalization request.

    The signed RacunZahtjev XML is wrapped in a SOAP envelope.
    The XML should already be signed with the correct FINA digital signature.

    Args:
        signed_racun_zahtjev_xml: Signed RacunZahtjev XML (with FINA signature)
        message_id: Optional message ID for tracking (not used in envelope)

    Returns:
        Complete SOAP envelope as string
    """
    # Remove XML declaration from inner XML if present
    inner_xml = re.sub(r'<\?xml[^?]*\?>\s*', '', signed_racun_zahtjev_xml)

    # Simple SOAP envelope - FINA expects the signed XML directly in Body
    soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
<soapenv:Body>
{inner_xml}
</soapenv:Body>
</soapenv:Envelope>'''

    return soap_envelope


# ============================================================================
# FINA SOAP CLIENT
# ============================================================================

class FINASoapClient:
    """
    SOAP client for FINA fiscalization service.

    Features:
    - mTLS authentication using client certificate
    - Circuit breaker for resilience
    - Automatic retry with exponential backoff
    - Response parsing
    """

    def __init__(
        self,
        environment: FINAEnvironment = FINAEnvironment.SANDBOX,
        cert_path: str = None,
        key_path: str = None,
        cert_password: str = None,
        ca_cert_path: str = None,
        timeout: int = 30
    ):
        """
        Initialize FINA SOAP client.

        Args:
            environment: SANDBOX or PRODUCTION
            cert_path: Path to client certificate (.pem or .p12)
            key_path: Path to private key (if separate from cert)
            cert_password: Password for encrypted key
            ca_cert_path: Path to CA certificate for SSL verification (e.g., demo2014_root_ca.cer)
            timeout: Request timeout in seconds
        """
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests library required for SOAP client")

        self.environment = environment
        self.endpoint = FINA_ENDPOINTS[environment]
        self.cert_path = cert_path
        self.key_path = key_path
        self.cert_password = cert_password
        self.ca_cert_path = ca_cert_path
        self.timeout = timeout

        # Create session with retry
        self.session = self._create_session()

        logger.info(f"FINA SOAP client initialized for {environment.value}")
        logger.info(f"Endpoint: {self.endpoint}")
        if ca_cert_path:
            logger.info(f"Using CA certificate: {ca_cert_path}")

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry configuration."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF_FACTOR,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=["POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Set client certificate for mTLS
        if self.cert_path:
            if self.key_path:
                session.cert = (self.cert_path, self.key_path)
            else:
                session.cert = self.cert_path

        return session

    def send_invoice(
        self,
        signed_xml: str,
        message_id: str = None
    ) -> Dict[str, Any]:
        """
        Send signed invoice to FINA for fiscalization.

        Args:
            signed_xml: XAdES-signed invoice XML
            message_id: Optional tracking ID

        Returns:
            Dictionary containing:
                - success: bool
                - jir: Optional JIR (Jedinstveni Identifikator Računa)
                - zki: ZKI from response
                - message_id: Message tracking ID
                - timestamp: Response timestamp
                - errors: List of error dicts
                - raw_response: Raw SOAP response
                - circuit_breaker_status: Current circuit breaker state
        """
        # Check circuit breaker
        can_execute, reason = _circuit_breaker.can_execute()
        if not can_execute:
            logger.warning(f"Circuit breaker blocked request: {reason}")
            return {
                "success": False,
                "jir": None,
                "zki": None,
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "errors": [{"code": "CB001", "message": reason}],
                "raw_response": None,
                "circuit_breaker_status": _circuit_breaker.get_status()
            }

        try:
            # Build SOAP message
            soap_message = build_fiscalization_request(signed_xml, message_id)

            # Log the raw SOAP envelope for debugging
            logger.debug("=" * 80)
            logger.debug("RAW SOAP REQUEST ENVELOPE:")
            logger.debug("=" * 80)
            logger.debug(soap_message)
            logger.debug("=" * 80)

            # Send request
            logger.info(f"Sending fiscalization request to {self.endpoint}")

            # Prepare mTLS certificate (client cert + key)
            cert_param = None
            if self.cert_path and self.key_path:
                cert_param = (self.cert_path, self.key_path)
                logger.info(f"Using mTLS with cert: {self.cert_path}, key: {self.key_path}")
            elif self.cert_path:
                cert_param = self.cert_path
                logger.info(f"Using certificate: {self.cert_path}")

            # Log request headers (SOAP 1.1 uses text/xml, not application/soap+xml)
            request_headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'http://www.apis-it.hr/fin/2012/types/f73/Fiskalizacija'
            }
            logger.debug("REQUEST HEADERS:")
            for header, value in request_headers.items():
                logger.debug(f"  {header}: {value}")

            response = self.session.post(
                self.endpoint,
                data=soap_message.encode('utf-8'),
                headers=request_headers,
                cert=cert_param,
                timeout=self.timeout,
                verify=self.ca_cert_path if self.ca_cert_path else True
            )

            logger.info(f"FINA response status: {response.status_code}")

            # Log response details
            logger.debug("=" * 80)
            logger.debug("RESPONSE HEADERS:")
            logger.debug("=" * 80)
            for header, value in response.headers.items():
                logger.debug(f"  {header}: {value}")
            logger.debug("=" * 80)
            logger.debug("RAW RESPONSE BODY:")
            logger.debug("=" * 80)
            logger.debug(response.text)
            logger.debug("=" * 80)

            # Check for HTTP error status codes
            if response.status_code >= 400:
                logger.error(f"HTTP error {response.status_code} from FINA")
                logger.error("=" * 80)
                logger.error("ERROR RESPONSE BODY:")
                logger.error("=" * 80)
                logger.error(response.text[:2000])  # Log first 2000 chars
                logger.error("=" * 80)

                # Return error result without parsing
                _circuit_breaker.record_failure()
                return {
                    "success": False,
                    "jir": None,
                    "zki": None,
                    "message_id": message_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "errors": [{"code": "t003", "message": f"HTTP {response.status_code}: {response.reason}"}],
                    "raw_response": response.text[:5000],
                    "circuit_breaker_status": _circuit_breaker.get_status()
                }

            # Parse response
            result = self._parse_response(response.text, message_id)

            # Update circuit breaker
            if result["success"]:
                _circuit_breaker.record_success()
            else:
                # Only record failure for system errors, not business errors
                if any(e.get("code", "").startswith("t") for e in result.get("errors", [])):
                    _circuit_breaker.record_failure()

            result["circuit_breaker_status"] = _circuit_breaker.get_status()
            return result

        except requests.exceptions.Timeout:
            logger.error("FINA request timeout")
            _circuit_breaker.record_failure()
            return {
                "success": False,
                "jir": None,
                "zki": None,
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "errors": [{"code": "t001", "message": "Request timeout"}],
                "raw_response": None,
                "circuit_breaker_status": _circuit_breaker.get_status()
            }

        except requests.exceptions.ConnectionError as e:
            logger.error(f"FINA connection error: {e}")
            _circuit_breaker.record_failure()
            return {
                "success": False,
                "jir": None,
                "zki": None,
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "errors": [{"code": "t001", "message": f"Connection error: {e}"}],
                "raw_response": None,
                "circuit_breaker_status": _circuit_breaker.get_status()
            }

        except Exception as e:
            logger.error(f"FINA request error: {e}")
            _circuit_breaker.record_failure()
            return {
                "success": False,
                "jir": None,
                "zki": None,
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "errors": [{"code": "t003", "message": str(e)}],
                "raw_response": None,
                "circuit_breaker_status": _circuit_breaker.get_status()
            }

    def _parse_response(
        self,
        soap_response: str,
        message_id: str = None
    ) -> Dict[str, Any]:
        """Parse FINA SOAP response."""
        try:
            if isinstance(soap_response, str):
                soap_bytes = soap_response.encode('utf-8')
            else:
                soap_bytes = soap_response

            doc = etree.parse(BytesIO(soap_bytes))
            root = doc.getroot()

            # Define namespaces for XPath
            ns = FINA_NAMESPACES

            # Check for SOAP Fault
            fault = root.find('.//soap:Fault', ns)
            if fault is not None:
                fault_string = fault.findtext('.//faultstring', default='Unknown error')
                return {
                    "success": False,
                    "jir": None,
                    "zki": None,
                    "message_id": message_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "errors": [{"code": "SOAP_FAULT", "message": fault_string}],
                    "raw_response": soap_response
                }

            # Extract JIR
            jir_elem = root.find('.//fis:Jir', ns)
            jir = jir_elem.text if jir_elem is not None else None

            # Extract ZKI
            zki_elem = root.find('.//fis:Zki', ns)
            zki = zki_elem.text if zki_elem is not None else None

            # Extract timestamp
            timestamp_elem = root.find('.//fis:DatumVrijeme', ns)
            timestamp = timestamp_elem.text if timestamp_elem is not None else None

            # Extract errors if any
            errors = []
            error_elems = root.findall('.//fis:Greska', ns)
            for err in error_elems:
                code = err.findtext('fis:SifraGreske', default='', namespaces=ns)
                msg = err.findtext('fis:PorukaGreske', default='', namespaces=ns)
                errors.append({
                    "code": code,
                    "message": msg or FINA_ERROR_CODES.get(code, 'Unknown error')
                })

            success = jir is not None and len(errors) == 0

            if success:
                logger.info(f"Fiscalization successful, JIR: {jir}")
            else:
                logger.warning(f"Fiscalization failed: {errors}")

            return {
                "success": success,
                "jir": jir,
                "zki": zki,
                "message_id": message_id,
                "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                "errors": errors,
                "raw_response": soap_response
            }

        except Exception as e:
            logger.error(f"Failed to parse FINA response: {e}")
            return {
                "success": False,
                "jir": None,
                "zki": None,
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "errors": [{"code": "PARSE_ERROR", "message": str(e)}],
                "raw_response": soap_response
            }


# ============================================================================
# RESPONSE PARSING
# ============================================================================

def parse_fina_response(soap_response: str) -> Dict[str, Any]:
    """
    Parse FINA SOAP response to extract JIR and errors.

    Convenience function for ADK tools.

    Args:
        soap_response: Raw SOAP response XML

    Returns:
        Dictionary with:
            - success: bool
            - jir: Optional JIR
            - zki: Optional ZKI
            - timestamp: Response timestamp
            - errors: List of error dicts with code and message
    """
    if not LXML_AVAILABLE:
        return {
            "success": False,
            "jir": None,
            "zki": None,
            "timestamp": None,
            "errors": [{"code": "IMPORT_ERROR", "message": "lxml not available"}]
        }

    client = FINASoapClient.__new__(FINASoapClient)
    return client._parse_response(soap_response)


# ============================================================================
# QR CODE GENERATION
# ============================================================================

def generate_verification_qr(
    jir: str = None,
    zki: str = None,
    invoice_datetime: str = None,
    total_amount: str = None,
    oib: str = None,
    use_jir: bool = True,
    min_size_cm: float = 2.0,
    dpi: int = 300
) -> Dict[str, Any]:
    """
    Generate QR code for invoice verification according to Croatian fiscalization rules.

    QR code contains URL to Porezna Uprava verification portal.

    Official URL format (per Porezna uprava technical specification v2.6):
        https://porezna.gov.hr/rn?jir=XXXXX&datv=YYYYMMDD_HHMM&izn=CCCCC
    or:
        https://porezna.gov.hr/rn?zki=XXXXX&datv=YYYYMMDD_HHMM&izn=CCCCC

    Requirements:
    - Minimum QR code size: 2cm x 2cm on printed receipt
    - Must contain: URL, JIR or ZKI, date/time, amount in cents
    - Date format: YYYYMMDD_HHMM (without seconds)
    - Amount: in cents (integer, no decimal separator)

    Args:
        jir: JIR from FINA response (36 characters with dashes)
        zki: ZKI code (32 hex characters, no dashes)
        invoice_datetime: Invoice date/time (ISO format or dd.mm.yyyy HH:MM:SS)
        total_amount: Total invoice amount in EUR (e.g., "125.00")
        oib: Issuer's OIB (not used in URL per spec, but kept for reference)
        use_jir: True to use JIR in URL, False to use ZKI
        min_size_cm: Minimum QR code size in centimeters (default 2.0)
        dpi: DPI for calculating pixel size (default 300 for print)

    Returns:
        Dictionary with:
            - success: bool
            - qr_code_base64: Base64-encoded PNG image
            - qr_code_svg: SVG version for scalable printing
            - verification_url: URL encoded in QR
            - pixel_size: Size in pixels for minimum print size
            - error: Optional error message
    """
    if not QRCODE_AVAILABLE:
        return {
            "success": False,
            "qr_code_base64": None,
            "qr_code_svg": None,
            "verification_url": None,
            "pixel_size": None,
            "error": "qrcode library not available. Install with: pip install qrcode[pil]"
        }

    try:
        # Validate required parameters
        if use_jir and not jir:
            return {
                "success": False,
                "qr_code_base64": None,
                "qr_code_svg": None,
                "verification_url": None,
                "pixel_size": None,
                "error": "JIR is required when use_jir=True"
            }
        if not use_jir and not zki:
            return {
                "success": False,
                "qr_code_base64": None,
                "qr_code_svg": None,
                "verification_url": None,
                "pixel_size": None,
                "error": "ZKI is required when use_jir=False"
            }

        # Parse datetime to required format: YYYYMMDD_HHMM
        if invoice_datetime:
            # Check if it's Croatian format (dd.mm.yyyy)
            if '.' in invoice_datetime[:10]:
                # Croatian format: dd.mm.yyyyTHH:MM:SS or dd.mm.yyyy HH:MM:SS
                clean_dt = invoice_datetime.replace('T', ' ')
                try:
                    dt = datetime.strptime(clean_dt, '%d.%m.%Y %H:%M:%S')
                except ValueError:
                    try:
                        dt = datetime.strptime(clean_dt, '%d.%m.%Y %H:%M')
                    except ValueError:
                        dt = datetime.strptime(clean_dt.split()[0], '%d.%m.%Y')
            elif 'T' in invoice_datetime:
                # ISO format
                dt = datetime.fromisoformat(invoice_datetime.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(invoice_datetime)
        else:
            dt = datetime.now()

        # Format: YYYYMMDD_HHMM (without seconds per spec)
        date_str = dt.strftime('%Y%m%d_%H%M')

        # Format amount in cents (integer, no decimal)
        # Convert EUR to cents
        amount_cents = int(Decimal(str(total_amount)) * 100)

        # Build verification URL per official spec
        # Base URL: https://porezna.gov.hr/rn
        base_url = "https://porezna.gov.hr/rn"

        if use_jir and jir:
            # JIR format in URL: with or without dashes (spec shows with dashes)
            identifier_param = f"jir={jir}"
        else:
            # ZKI format: 32 hex chars, lowercase, no dashes
            zki_clean = zki.replace("-", "").lower()
            identifier_param = f"zki={zki_clean}"

        verification_url = f"{base_url}?{identifier_param}&datv={date_str}&izn={amount_cents}"

        # Calculate minimum pixel size for 2cm at specified DPI
        # 2cm = 0.787 inches, at 300 DPI = ~236 pixels
        min_pixels = int((min_size_cm / 2.54) * dpi)

        # Generate QR code with appropriate size
        # Use higher error correction for better scanning on receipts
        qr = qrcode.QRCode(
            version=None,  # Auto-determine
            error_correction=qrcode.constants.ERROR_CORRECT_M,  # 15% error correction
            box_size=10,
            border=4  # Minimum 4 modules quiet zone per spec
        )
        qr.add_data(verification_url)
        qr.make(fit=True)

        # Create PNG image
        img = qr.make_image(fill_color="black", back_color="white")

        # Resize to minimum print size if needed
        current_size = img.size[0]
        if current_size < min_pixels:
            # Use NEAREST to keep sharp edges
            try:
                from PIL import Image
                img = img.resize((min_pixels, min_pixels), Image.NEAREST)
            except ImportError:
                pass  # Keep original size if PIL not available

        # Convert to base64 PNG
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode('ascii')

        # Generate SVG version for scalable printing
        try:
            from qrcode.image.svg import SvgPathImage
            qr_for_svg = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4
            )
            qr_for_svg.add_data(verification_url)
            qr_for_svg.make(fit=True)
            svg_img = qr_for_svg.make_image(image_factory=SvgPathImage)
            svg_buffer = BytesIO()
            svg_img.save(svg_buffer)
            qr_svg_str = svg_buffer.getvalue().decode('utf-8')
        except Exception:
            qr_svg_str = None

        logger.info(f"Generated QR code for {'JIR' if use_jir else 'ZKI'}: {jir if use_jir else zki}")

        return {
            "success": True,
            "qr_code_base64": qr_base64,
            "qr_code_svg": qr_svg_str,
            "verification_url": verification_url,
            "pixel_size": min_pixels,
            "min_size_cm": min_size_cm,
            "identifier_type": "JIR" if use_jir else "ZKI",
            "error": None
        }

    except Exception as e:
        logger.error(f"QR code generation failed: {e}")
        return {
            "success": False,
            "qr_code_base64": None,
            "qr_code_svg": None,
            "verification_url": None,
            "pixel_size": None,
            "error": str(e)
        }


# ============================================================================
# CONVENIENCE FUNCTIONS FOR ADK TOOLS
# ============================================================================

# Global client instance (lazy initialization)
_fina_client: Optional[FINASoapClient] = None


def get_fina_client(
    environment: str = "sandbox",
    cert_path: str = None,
    key_path: str = None,
    ca_cert_path: str = None
) -> FINASoapClient:
    """Get or create FINA SOAP client instance."""
    global _fina_client

    env = FINAEnvironment.PRODUCTION if environment == "production" else FINAEnvironment.SANDBOX

    if _fina_client is None or _fina_client.environment != env:
        _fina_client = FINASoapClient(
            environment=env,
            cert_path=cert_path,
            key_path=key_path,
            ca_cert_path=ca_cert_path
        )

    return _fina_client


def send_to_fina(
    signed_xml: str,
    environment: str = "sandbox",
    cert_path: str = None,
    key_path: str = None,
    ca_cert_path: str = None
) -> Dict[str, Any]:
    """
    Send signed invoice to FINA.

    Convenience function for ADK tools.

    Args:
        signed_xml: XAdES-signed invoice XML
        environment: "sandbox" or "production"
        cert_path: Path to client certificate
        key_path: Path to private key
        ca_cert_path: Path to CA certificate for SSL verification

    Returns:
        Dictionary with fiscalization result
    """
    client = get_fina_client(environment, cert_path, key_path, ca_cert_path)
    return client.send_invoice(signed_xml)


def get_circuit_breaker_status() -> Dict[str, Any]:
    """Get current circuit breaker status."""
    return _circuit_breaker.get_status()


def reset_circuit_breaker() -> None:
    """Reset circuit breaker to closed state."""
    global _circuit_breaker
    _circuit_breaker = CircuitBreaker()
    logger.info("Circuit breaker reset")
