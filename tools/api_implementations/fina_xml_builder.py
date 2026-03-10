"""
FINA XML Builder for Croatian Fiscalization

Builds XML messages according to FINA CIS specification:
- RacunZahtjev (Invoice Request)
- PoslovniProstorZahtjev (Business Premises Registration)

Schema: http://www.apis-it.hr/fin/2012/types/f73

This is a DETERMINISTIC tool - no LLM involvement.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import logging
import uuid

try:
    from lxml import etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

logger = logging.getLogger(__name__)

# FINA Namespace
FINA_NS = "http://www.apis-it.hr/fin/2012/types/f73"
FINA_NSMAP = {None: FINA_NS}


def _format_datetime(dt: datetime) -> str:
    """Format datetime as FINA expects: dd.mm.yyyyThh:mm:ss"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # FINA uses local Croatian time format
    return dt.strftime("%d.%m.%YT%H:%M:%S")


def _format_amount(amount) -> str:
    """Format amount with 2 decimal places."""
    if isinstance(amount, str):
        amount = Decimal(amount)
    return f"{amount:.2f}"


def build_racun_zahtjev(
    oib: str,
    u_sustavu_pdv: bool,
    datum_vrijeme: datetime,
    oznaka_slijednosti: str,  # "N" (naknadno) or "P" (paragon)
    broj_racuna: str,
    oznaka_poslovnog_prostora: str,
    oznaka_naplatnog_uredaja: str,
    ukupan_iznos: str,
    nacin_placanja: str,  # "G" (gotovina), "K" (kartica), "T" (transakcijski), "O" (ostalo)
    oib_operatera: str,
    zki: str,
    pdv: List[Dict[str, str]] = None,  # List of {"stopa": "25.00", "osnovica": "100.00", "iznos": "25.00"}
    naknadna_dostava: bool = False,
    posebna_namjena: str = None,
) -> str:
    """
    Build RacunZahtjev XML for FINA fiscalization.

    Args:
        oib: Company OIB (11 digits)
        u_sustavu_pdv: Is company in VAT system
        datum_vrijeme: Invoice date/time
        oznaka_slijednosti: "N" (naknadna) or "P" (paragon blok)
        broj_racuna: Invoice sequential number
        oznaka_poslovnog_prostora: Business premises code
        oznaka_naplatnog_uredaja: Cash register code
        ukupan_iznos: Total amount
        nacin_placanja: Payment method code
        oib_operatera: Operator OIB
        zki: ZKI code (calculated)
        pdv: VAT breakdown list
        naknadna_dostava: Is this a late submission
        posebna_namjena: Special purpose flag

    Returns:
        XML string for RacunZahtjev
    """
    if not LXML_AVAILABLE:
        raise ImportError("lxml required for XML building")

    # Create root element
    root = etree.Element(
        "RacunZahtjev",
        nsmap=FINA_NSMAP,
        Id=f"RacunZahtjev-{uuid.uuid4().hex[:8]}"
    )

    # Zaglavlje (Header)
    zaglavlje = etree.SubElement(root, "Zaglavlje")
    etree.SubElement(zaglavlje, "IdPoruke").text = str(uuid.uuid4())
    etree.SubElement(zaglavlje, "DatumVrijeme").text = _format_datetime(datetime.now(timezone.utc))

    # Racun (Invoice)
    racun = etree.SubElement(root, "Racun")

    # OIB
    etree.SubElement(racun, "Oib").text = oib

    # U sustavu PDV-a
    etree.SubElement(racun, "USustPdv").text = "true" if u_sustavu_pdv else "false"

    # Datum i vrijeme izdavanja
    etree.SubElement(racun, "DatVrijeme").text = _format_datetime(datum_vrijeme)

    # Oznaka slijednosti
    etree.SubElement(racun, "OznSlijed").text = oznaka_slijednosti

    # Broj računa
    br_rac = etree.SubElement(racun, "BrRac")
    etree.SubElement(br_rac, "BrOznRac").text = broj_racuna
    etree.SubElement(br_rac, "OznPosPr").text = oznaka_poslovnog_prostora
    etree.SubElement(br_rac, "OznNapUr").text = oznaka_naplatnog_uredaja

    # PDV breakdown (if applicable)
    if pdv and u_sustavu_pdv:
        pdv_elem = etree.SubElement(racun, "Pdv")
        for p in pdv:
            porez = etree.SubElement(pdv_elem, "Porez")
            etree.SubElement(porez, "Stopa").text = _format_amount(p["stopa"])
            etree.SubElement(porez, "Osnovica").text = _format_amount(p["osnovica"])
            etree.SubElement(porez, "Iznos").text = _format_amount(p["iznos"])

    # Ukupan iznos
    etree.SubElement(racun, "IznosUkupno").text = _format_amount(ukupan_iznos)

    # Način plaćanja
    etree.SubElement(racun, "NacinPlac").text = nacin_placanja

    # OIB operatera
    etree.SubElement(racun, "OibOper").text = oib_operatera

    # ZKI (must be lowercase per FINA schema)
    etree.SubElement(racun, "ZastKod").text = zki.replace("-", "").lower()

    # Naknadna dostava
    etree.SubElement(racun, "NakDost").text = "true" if naknadna_dostava else "false"

    # Posebna namjena (optional)
    if posebna_namjena:
        etree.SubElement(racun, "PosebNamj").text = posebna_namjena

    # Convert to string
    xml_str = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding='UTF-8'
    ).decode('utf-8')

    return xml_str


def build_soap_envelope(racun_zahtjev_xml: str) -> str:
    """
    Wrap RacunZahtjev in SOAP envelope.

    Args:
        racun_zahtjev_xml: The RacunZahtjev XML (already signed)

    Returns:
        Complete SOAP envelope
    """
    # Remove XML declaration from inner XML
    import re
    inner_xml = re.sub(r'<\?xml[^?]*\?>\s*', '', racun_zahtjev_xml)

    soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        {inner_xml}
    </soapenv:Body>
</soapenv:Envelope>'''

    return soap_envelope


def build_echo_request() -> str:
    """Build a simple echo request to test connectivity."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:fis="http://www.apis-it.hr/fin/2012/types/f73">
    <soapenv:Body>
        <fis:EchoRequest>Test</fis:EchoRequest>
    </soapenv:Body>
</soapenv:Envelope>'''


def build_poslovni_prostor_zahtjev(
    oib: str,
    oznaka_poslovnog_prostora: str,
    radno_vrijeme: str,
    datum_pocetak: datetime,
    adresa_ulica: str = None,
    adresa_kucni_broj: str = None,
    adresa_kucni_broj_dodatak: str = None,
    adresa_naziv_naselja: str = None,
    adresa_naziv_opcine: str = None,
    adresa_broj_posta: str = None,
    ostali_tip_oznaka: str = None,  # For mobile/internet sales
    zatvaranje: bool = False,
    spec_namj: str = None,
) -> str:
    """
    Build PoslovniProstorZahtjev for registering business premises.

    Args:
        oib: Company OIB
        oznaka_poslovnog_prostora: Business premises code
        radno_vrijeme: Working hours description
        datum_pocetak: Start date
        adresa_*: Address components (for fixed location)
        ostali_tip_oznaka: For non-fixed locations (mobile, internet)
        zatvaranje: True if deregistering premises
        spec_namj: Special purpose

    Returns:
        XML string for PoslovniProstorZahtjev
    """
    if not LXML_AVAILABLE:
        raise ImportError("lxml required for XML building")

    root = etree.Element(
        "PoslovniProstorZahtjev",
        nsmap=FINA_NSMAP,
        Id=f"PoslovniProstorZahtjev-{uuid.uuid4().hex[:8]}"
    )

    # Zaglavlje
    zaglavlje = etree.SubElement(root, "Zaglavlje")
    etree.SubElement(zaglavlje, "IdPoruke").text = str(uuid.uuid4())
    etree.SubElement(zaglavlje, "DatumVrijeme").text = _format_datetime(datetime.now(timezone.utc))

    # PoslovniProstor
    pp = etree.SubElement(root, "PoslovniProstor")

    etree.SubElement(pp, "Oib").text = oib
    etree.SubElement(pp, "OznPoslProst").text = oznaka_poslovnog_prostora

    # Adresa or OstaliTipovi
    if adresa_ulica:
        adresa_obv = etree.SubElement(pp, "AdresniPodatak")
        adresa = etree.SubElement(adresa_obv, "Adresa")
        etree.SubElement(adresa, "Ulica").text = adresa_ulica
        etree.SubElement(adresa, "KucniBroj").text = adresa_kucni_broj or ""
        if adresa_kucni_broj_dodatak:
            etree.SubElement(adresa, "KucniBrojDodatak").text = adresa_kucni_broj_dodatak
        etree.SubElement(adresa, "BrojPoste").text = adresa_broj_posta or ""
        etree.SubElement(adresa, "Naselje").text = adresa_naziv_naselja or ""
        etree.SubElement(adresa, "Opcina").text = adresa_naziv_opcine or ""
    elif ostali_tip_oznaka:
        adresa_obv = etree.SubElement(pp, "AdresniPodatak")
        ostali = etree.SubElement(adresa_obv, "OstaliTipoviPP")
        etree.SubElement(ostali, "OstaliTipPP").text = ostali_tip_oznaka

    # Radno vrijeme
    etree.SubElement(pp, "RadnoVrijeme").text = radno_vrijeme

    # Datum početka primjene
    etree.SubElement(pp, "DatumPo662cPrimj").text = datum_pocetak.strftime("%d.%m.%Y")

    # Zatvaranje (optional)
    if zatvaranje:
        etree.SubElement(pp, "OznakaZatworenja").text = "Z"

    # Spec namjena (optional)
    if spec_namj:
        etree.SubElement(pp, "SpecNamj").text = spec_namj

    xml_str = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding='UTF-8'
    ).decode('utf-8')

    return xml_str


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_fiscalization_request(
    invoice_data: Dict[str, Any],
    zki: str,
    cert_info: Any = None
) -> Dict[str, Any]:
    """
    Create complete fiscalization request from invoice data.

    Args:
        invoice_data: Invoice details
        zki: Calculated ZKI
        cert_info: Certificate for signing (optional, can sign separately)

    Returns:
        Dictionary with unsigned and signed XML
    """
    # Extract data
    oib = invoice_data.get("supplier", {}).get("oib", "")
    invoice_number = invoice_data.get("invoice_number", "")
    parts = invoice_number.split("/")

    if len(parts) != 3:
        return {
            "success": False,
            "error": f"Invalid invoice number format: {invoice_number}. Expected: XXX/PP/NU"
        }

    broj_racuna = parts[0]
    oznaka_pp = parts[1]
    oznaka_nu = parts[2]

    # Parse datetime
    issue_date = invoice_data.get("issue_date", "")
    issue_time = invoice_data.get("issue_time", "12:00:00")

    if isinstance(issue_date, str):
        dt = datetime.fromisoformat(f"{issue_date}T{issue_time}")
    else:
        dt = issue_date

    # VAT breakdown
    tax_breakdown = invoice_data.get("tax_breakdown", {})
    pdv = []
    for subtotal in tax_breakdown.get("subtotals", []):
        if subtotal.get("vat_rate", "0") != "0":
            pdv.append({
                "stopa": subtotal["vat_rate"] + ".00",
                "osnovica": subtotal["taxable_amount"],
                "iznos": subtotal["tax_amount"]
            })

    # Total amount
    total = tax_breakdown.get("total_gross", "0.00")

    # Build RacunZahtjev
    try:
        racun_xml = build_racun_zahtjev(
            oib=oib,
            u_sustavu_pdv=True,  # Assume VAT registered
            datum_vrijeme=dt,
            oznaka_slijednosti="P",  # Paragon (real-time)
            broj_racuna=broj_racuna,
            oznaka_poslovnog_prostora=oznaka_pp,
            oznaka_naplatnog_uredaja=oznaka_nu,
            ukupan_iznos=total,
            nacin_placanja="G",  # Default: Gotovina
            oib_operatera=oib,  # Same as company for now
            zki=zki,
            pdv=pdv if pdv else None,
            naknadna_dostava=False
        )

        return {
            "success": True,
            "racun_xml": racun_xml,
            "broj_racuna": invoice_number,
            "zki": zki,
            "total": total
        }

    except Exception as e:
        logger.error(f"Failed to build fiscalization request: {e}")
        return {
            "success": False,
            "error": str(e)
        }
