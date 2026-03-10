"""
Company Configuration for Fiskalizacija

This file contains company-specific settings:
- Registered NKD activities
- Business premises (poslovni prostori)
- Cash registers (naplatni uređaji)
- Certificate paths
- Default settings

IMPORTANT: Update this file with your company's actual data before production use.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BusinessPremise:
    """
    Poslovni prostor (Business Premise) configuration.

    Required for fiscalization - must be registered with Tax Authority.
    """
    code: str  # Oznaka poslovnog prostora (e.g., "URED", "TRGOVINA1")
    name: str  # Descriptive name
    address: str  # Full address
    city: str
    postal_code: str
    is_active: bool = True


@dataclass
class CashRegister:
    """
    Naplatni uređaj (Cash Register) configuration.

    Each cash register must be registered for fiscalization.
    """
    code: str  # Oznaka naplatnog uređaja (e.g., "1", "2")
    business_premise_code: str  # Which premise this register belongs to
    description: str = ""
    is_active: bool = True


@dataclass
class CompanyConfig:
    """
    Complete company configuration for fiscalization.
    """
    # Basic info
    name: str
    oib: str
    address: str
    city: str
    postal_code: str
    country_code: str = "HR"

    # Contact
    email: str = ""
    phone: str = ""

    # Registered NKD activities
    registered_nkd: List[str] = field(default_factory=list)

    # Business premises
    business_premises: List[BusinessPremise] = field(default_factory=list)

    # Cash registers
    cash_registers: List[CashRegister] = field(default_factory=list)

    # Certificate settings
    certificate_path: Optional[str] = None
    certificate_password_env: str = "FINA_CERT_PASSWORD"  # Environment variable name

    # Fiscalization settings
    environment: str = "sandbox"  # "sandbox" or "production"
    use_firestore: bool = False  # Use Firestore for ledger (True for production)

    # Default VAT rate
    default_vat_rate: str = "25"

    def get_premise(self, code: str) -> Optional[BusinessPremise]:
        """Get business premise by code."""
        for premise in self.business_premises:
            if premise.code == code and premise.is_active:
                return premise
        return None

    def get_register(self, code: str, premise_code: str = None) -> Optional[CashRegister]:
        """Get cash register by code, optionally filtered by premise."""
        for register in self.cash_registers:
            if register.code == code and register.is_active:
                if premise_code is None or register.business_premise_code == premise_code:
                    return register
        return None

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.name:
            errors.append("Company name is required")

        if not self.oib or len(self.oib) != 11:
            errors.append("Valid OIB (11 digits) is required")

        if not self.business_premises:
            errors.append("At least one business premise is required")

        if not self.cash_registers:
            errors.append("At least one cash register is required")

        # Check that all registers reference valid premises
        premise_codes = {p.code for p in self.business_premises}
        for register in self.cash_registers:
            if register.business_premise_code not in premise_codes:
                errors.append(
                    f"Cash register {register.code} references unknown premise "
                    f"{register.business_premise_code}"
                )

        return errors

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "oib": self.oib,
            "address": self.address,
            "city": self.city,
            "postal_code": self.postal_code,
            "country_code": self.country_code,
            "email": self.email,
            "phone": self.phone,
            "registered_nkd": self.registered_nkd,
            "business_premises": [
                {
                    "code": p.code,
                    "name": p.name,
                    "address": p.address,
                    "city": p.city,
                    "postal_code": p.postal_code,
                    "is_active": p.is_active
                }
                for p in self.business_premises
            ],
            "cash_registers": [
                {
                    "code": r.code,
                    "business_premise_code": r.business_premise_code,
                    "description": r.description,
                    "is_active": r.is_active
                }
                for r in self.cash_registers
            ],
            "environment": self.environment,
            "default_vat_rate": self.default_vat_rate
        }


# ============================================================================
# EXAMPLE CONFIGURATION - Replace with your actual company data
# ============================================================================

# Example company configuration - UPDATE THIS FOR YOUR COMPANY
EXAMPLE_COMPANY_CONFIG = CompanyConfig(
    name="Primjer d.o.o.",
    oib="12345678903",
    address="Ulica primjera 1",
    city="Zagreb",
    postal_code="10000",
    country_code="HR",
    email="info@primjer.hr",
    phone="+385 1 234 5678",

    # Registered NKD activities - ADD YOUR REGISTERED ACTIVITIES
    registered_nkd=[
        "43.32.0",   # Ugradnja stolarije
        "43.21.0",   # Elektroinstalacijski radovi
        "47.52.0",   # Trgovina na malo željeznom robom, bojama i staklom
        "11.05.0",   # Proizvodnja piva (primjer za pivovaru)
    ],

    # Business premises - ADD YOUR ACTUAL PREMISES
    business_premises=[
        BusinessPremise(
            code="URED",
            name="Glavni ured",
            address="Ulica primjera 1",
            city="Zagreb",
            postal_code="10000"
        ),
        BusinessPremise(
            code="SKLADISTE",
            name="Skladište",
            address="Industrijska 10",
            city="Zagreb",
            postal_code="10000"
        ),
    ],

    # Cash registers - ADD YOUR ACTUAL REGISTERS
    cash_registers=[
        CashRegister(
            code="1",
            business_premise_code="URED",
            description="Glavna blagajna"
        ),
        CashRegister(
            code="2",
            business_premise_code="SKLADISTE",
            description="Blagajna skladište"
        ),
    ],

    # Certificate settings
    certificate_path=None,  # Set path to your .p12 certificate
    certificate_password_env="FINA_CERT_PASSWORD",

    # Environment
    environment="sandbox",  # Change to "production" for live
    use_firestore=False,    # Change to True for production

    # Default VAT
    default_vat_rate="25"
)


# ============================================================================
# LUX TECH D.O.O. - ACTIVE CONFIGURATION
# ============================================================================

LUX_TECH_CONFIG = CompanyConfig(
    name="LUX TECH D.O.O.",
    oib="47034854402",
    address="Leskovački brijeg 2",
    city="Hrvatski Leskovac",
    postal_code="10257",
    country_code="HR",
    email="tomislav.luxtech@gmail.com",
    phone="+385914575757",

    # Registered NKD activities based on "Popis djelatnosti.pdf"
    # Pretežita + evidencijske djelatnosti
    registered_nkd=[
        # PRETEŽITA DJELATNOST
        "43.21",    # Elektroinstalacijski radovi

        # EVIDENCIJSKE DJELATNOSTI - Proizvodnja
        "11.01",    # Destiliranje, pročišćavanje i miješanje alkoholnih pića
        "11.07",    # Proizvodnja pića (sokovi)
        "10.32",    # Proizvodnja sokova od voća i povrća
        "10.39",    # Prerada i konzerviranje voća i povrća
        "10.89",    # Proizvodnja prehrambenih proizvoda
        "20.41",    # Proizvodnja sapuna, deterdženata, sredstava za čišćenje
        "22.29",    # Proizvodnja proizvoda od plastike
        "25.73",    # Proizvodnja alata
        "26.11",    # Proizvodnja elektroničkih komponenata i ploča
        "26.20",    # Proizvodnja računala i periferne opreme
        "26.30",    # Proizvodnja komunikacijske opreme
        "26.51",    # Proizvodnja instrumenata za mjerenje, ispitivanje
        "26.70",    # Proizvodnja elektroničkih i optičkih proizvoda
        "27.11",    # Proizvodnja elektromotora, generatora i transformatora
        "27.12",    # Proizvodnja uređaja za distribuciju i kontrolu el. energije
        "27.51",    # Proizvodnja aparata za kućanstvo
        "27.90",    # Proizvodnja ostale električne opreme

        # Građevinarstvo i instalacije
        "41.20",    # Projektiranje i građenje građevina
        "43.22",    # Uvođenje instalacija vodovoda, kanalizacije, plina
        "71.11",    # Arhitektonske djelatnosti / projektiranje
        "71.12",    # Inženjerstvo i tehničko savjetovanje

        # IT i digitalne usluge
        "62.01",    # Računalno programiranje / izrada web stranica
        "62.02",    # Savjetovanje u vezi s računalima
        "62.09",    # Ostale usluge informacijske tehnologije
        "63.11",    # Obrada podataka, hosting
        "63.12",    # Internetski portali

        # Mediji i audiovizualno
        "59.11",    # Proizvodnja filmova, videofilmova
        "59.12",    # Djelatnosti koje slijede nakon proizvodnje filmova
        "60.10",    # Emitiranje radijskog programa
        "60.20",    # Emitiranje televizijskog programa
        "58.11",    # Izdavanje knjiga
        "58.14",    # Izdavanje časopisa i periodičnih publikacija
        "18.11",    # Tiskanje novina
        "18.12",    # Ostalo tiskanje

        # Trgovina
        "46.90",    # Nespecijalizirana trgovina na veliko
        "47.19",    # Ostala trgovina na malo
        "47.62",    # Trgovina na malo novinama, knjigama (distribucija tiska)

        # Usluge
        "35.11",    # Proizvodnja električne energije
        "35.13",    # Distribucija električne energije
        "35.14",    # Trgovina električnom energijom
        "35.30",    # Opskrba toplinom/hladnoćom
        "36.00",    # Skupljanje, pročišćavanje i opskrba vodom
        "56.21",    # Djelatnosti keteringa (catering)
        "49.39",    # Prijevoz putnika

        # Dizajn i kreativne usluge
        "74.10",    # Specijalizirane dizajnerske djelatnosti (grafički, industrijski, interijer)
        "73.11",    # Agencije za promidžbu/reklamu
        "73.20",    # Istraživanje tržišta

        # Poslovne usluge
        "70.22",    # Savjetovanje u vezi s poslovanjem i upravljanjem
        "68.10",    # Kupnja i prodaja vlastitih nekretnina
        "68.31",    # Agencije za poslovanje nekretninama
        "68.32",    # Upravljanje nekretninama
        "78.10",    # Djelatnosti agencija za zapošljavanje
        "77.39",    # Iznajmljivanje strojeva i opreme

        # Tehničke i stručne usluge
        "71.20",    # Tehničko ispitivanje i analiza
        "72.19",    # Ostalo istraživanje i razvoj

        # Čišćenje i održavanje
        "81.21",    # Opće čišćenje zgrada
        "81.22",    # Ostale djelatnosti čišćenja
        "81.30",    # Usluge uređenja i održavanja krajolika

        # Socijalne usluge
        "87.30",    # Djelatnosti ustanova za starije i nemoćne
        "88.10",    # Djelatnosti socijalne skrbi bez smještaja za starije
        "88.99",    # Ostale djelatnosti socijalne skrbi

        # Ostalo
        "01.19",    # Uzgoj ostalih jednogodišnjih usjeva (poljoprivreda)
        "31.09",    # Proizvodnja ostalog namještaja
        "33.12",    # Popravak strojeva
        "61.10",    # Djelatnosti žičane telekomunikacije
        "61.90",    # Ostale telekomunikacijske djelatnosti
        "82.30",    # Organizacija sastanaka i sajmova
        "93.11",    # Upravljanje sportskim objektima
    ],

    # Business premises
    business_premises=[
        BusinessPremise(
            code="1",
            name="Sjedište tvrtke",
            address="Leskovački brijeg 2",
            city="Hrvatski Leskovac",
            postal_code="10257"
        ),
    ],

    # Cash registers
    cash_registers=[
        CashRegister(
            code="1",
            business_premise_code="1",
            description="Naplatni uređaj 1"
        ),
    ],

    # Certificate settings - FINA Demo certificate
    certificate_path="47034854402.F1.1.p12",
    certificate_password_env="FINA_CERT_PASSWORD",

    # Environment - SANDBOX for testing
    environment="sandbox",
    use_firestore=False,

    # Default VAT
    default_vat_rate="25"
)


# ============================================================================
# Active configuration - Set this to your company config
# ============================================================================

# Default to LUX TECH configuration
_active_config: Optional[CompanyConfig] = None


def get_company_config() -> CompanyConfig:
    """
    Get the active company configuration.

    Returns:
        CompanyConfig instance
    """
    global _active_config
    if _active_config is None:
        _active_config = LUX_TECH_CONFIG
    return _active_config


def set_company_config(config: CompanyConfig):
    """
    Set the active company configuration.

    Args:
        config: CompanyConfig instance
    """
    global _active_config
    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid company configuration: {', '.join(errors)}")
    _active_config = config


def load_company_config_from_dict(data: dict) -> CompanyConfig:
    """
    Load company configuration from dictionary.

    Args:
        data: Configuration dictionary

    Returns:
        CompanyConfig instance
    """
    premises = [
        BusinessPremise(**p) for p in data.get("business_premises", [])
    ]
    registers = [
        CashRegister(**r) for r in data.get("cash_registers", [])
    ]

    return CompanyConfig(
        name=data.get("name", ""),
        oib=data.get("oib", ""),
        address=data.get("address", ""),
        city=data.get("city", ""),
        postal_code=data.get("postal_code", ""),
        country_code=data.get("country_code", "HR"),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        registered_nkd=data.get("registered_nkd", []),
        business_premises=premises,
        cash_registers=registers,
        certificate_path=data.get("certificate_path"),
        certificate_password_env=data.get("certificate_password_env", "FINA_CERT_PASSWORD"),
        environment=data.get("environment", "sandbox"),
        use_firestore=data.get("use_firestore", False),
        default_vat_rate=data.get("default_vat_rate", "25")
    )


def load_company_config_from_json(path: str) -> CompanyConfig:
    """
    Load company configuration from JSON file.

    Args:
        path: Path to JSON configuration file

    Returns:
        CompanyConfig instance
    """
    import json
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return load_company_config_from_dict(data)
