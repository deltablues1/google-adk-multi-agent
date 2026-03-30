"""
Outgoing Invoice Schema - Pydantic Models for OCR extraction of IZLAZNI racuni.

Used by bulk import to extract structured data from outgoing invoices
where Lux Tech d.o.o. is the SELLER.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class OutgoingLineItem(BaseModel):
    description: str = Field(..., description="Naziv artikla/usluge")
    quantity: Optional[float] = Field(None, description="Kolicina")
    unit_price: Optional[float] = Field(None, description="Jedinicna cijena bez PDV-a")
    amount: float = Field(..., description="Ukupna cijena stavke")

    model_config = ConfigDict(extra="ignore")


class OutgoingInvoice(BaseModel):
    """
    OCR extraction schema for OUTGOING invoices (izlazni racuni).
    Lux Tech d.o.o. is the SELLER — extract BUYER (customer) data.
    """

    # Buyer (customer) info
    buyer_name: str = Field(
        ...,
        description="Naziv kupca/primatelja racuna. Ako nije citljivo, vrati 'Unknown'."
    )
    buyer_oib: Optional[str] = Field(
        None,
        description="OIB kupca (11 znamenki). Ako nije vidljivo, ostavi None."
    )
    buyer_address: Optional[str] = Field(
        None,
        description="Adresa kupca. Ako nije vidljivo, ostavi None."
    )

    # Invoice metadata
    invoice_number: str = Field(
        ...,
        description="Broj racuna (npr. 1/URED/1, RA-2024-001). OBAVEZNO."
    )
    invoice_date: str = Field(
        ...,
        description="Datum racuna u ISO 8601 formatu (YYYY-MM-DD)."
    )
    due_date: Optional[str] = Field(
        None,
        description="Datum dospijeca u YYYY-MM-DD formatu. Ako nije vidljivo, ostavi None."
    )
    delivery_date: Optional[str] = Field(
        None,
        description="Datum isporuke/izvrsenja usluge u YYYY-MM-DD. Ako nije vidljivo, ostavi None."
    )

    # Payment info
    payment_method: Optional[str] = Field(
        None,
        description="Nacin placanja: G(gotovina), K(kartica), T(transakcija/virman), O(ostalo)."
    )
    payment_reference: Optional[str] = Field(
        None,
        description="Poziv na broj primatelja (HR model + broj)."
    )

    # Amounts
    total_without_vat: float = Field(
        ...,
        description="Ukupan iznos BEZ PDV-a (osnovica/porezna osnovica)."
    )
    vat_rate: Optional[float] = Field(
        None,
        description="Stopa PDV-a u postocima (npr. 25.0). Ako ima vise stopa, glavna."
    )
    total_vat: float = Field(
        default=0.0,
        description="Ukupan iznos PDV-a."
    )
    grand_total: float = Field(
        ...,
        description="Ukupan iznos ZA PLATITI (s PDV-om)."
    )
    currency: str = Field(
        default="EUR",
        description="Valuta (EUR, HRK). Default: EUR."
    )

    # Fiscalization (if visible)
    jir: Optional[str] = Field(
        None,
        description="JIR (Jedinstveni Identifikator Racuna) - 36 znakova UUID. Samo za B2C."
    )
    zki: Optional[str] = Field(
        None,
        description="ZKI (Zastitni Kod Izdavatelja) - 32 hex znaka. Samo za B2C."
    )

    # Line items
    items: List[OutgoingLineItem] = Field(
        default_factory=list,
        description="Lista stavki s racuna. Ako nisu citljive, vrati praznu listu []."
    )

    # Invoice type detection
    invoice_type: str = Field(
        default="b2c",
        description=(
            "Tip racuna na temelju kupca: "
            "'b2c' ako je kupac fizicka osoba ili nema OIB, "
            "'b2b' ako kupac ima OIB (pravna osoba), "
            "'b2g' ako je kupac drzavna institucija."
        )
    )

    # OCR metadata
    confidence_score: float = Field(
        ...,
        description="Pouzdanost ekstrakcije (0.0 - 1.0)."
    )
    extraction_notes: Optional[str] = Field(
        None,
        description="Biljeske o ekstrakciji — procjene, nejasnoce."
    )

    # Validators
    @field_validator('invoice_date', 'due_date', 'delivery_date')
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            for fmt in ["%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d"]:
                try:
                    dt = datetime.strptime(v, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            logger.warning(f"Could not parse date: {v}")
            return v

    @field_validator('grand_total')
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Grand total must be > 0, got {v}")
        return v

    @field_validator('confidence_score')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator('invoice_type')
    @classmethod
    def validate_invoice_type(cls, v: str) -> str:
        valid = ["b2c", "b2b", "b2g", "eu", "int"]
        if v not in valid:
            return "b2c"
        return v

    @field_validator('currency')
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        if v.upper() == "HRK":
            return "HRK"
        return "EUR"

    model_config = ConfigDict(extra="ignore")
