"""
Direct SOAP Test - bypasses agent system to test SOAP client directly
"""
import sys
import logging
from pathlib import Path

# Setup logging FIRST
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.insert(0, str(Path(__file__).parent))

from tools.api_implementations.fina_soap_client import FINASoapClient, FINAEnvironment

# Simple test XML (minimal but valid structure for testing SOAP communication)
TEST_SIGNED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<RacunZahtjev xmlns="http://www.apis-it.hr/fin/2012/types/f73">
  <Zaglavlje>
    <IdPoruke>test-message-001</IdPoruke>
    <DatumVrijeme>2026-01-29T13:00:00</DatumVrijeme>
  </Zaglavlje>
  <Racun>
    <Oib>47034854402</Oib>
    <USustPdv>true</USustPdv>
    <DatVrijeme>2026-01-29T13:00:00</DatVrijeme>
    <OznSlijed>P</OznSlijed>
    <BrRac>
      <BrOznRac>001</BrOznRac>
      <OznPosPr>DEMO</OznPosPr>
      <OznNapUr>1</OznNapUr>
    </BrRac>
    <Pdv>
      <Porez>
        <Stopa>25.00</Stopa>
        <Osnovica>1500.00</Osnovica>
        <Iznos>375.00</Iznos>
      </Porez>
    </Pdv>
    <IznosUkupno>1875.00</IznosUkupno>
    <NacinPlac>T</NacinPlac>
    <OibOper>47034854402</OibOper>
    <ZastKod>32962BA3-B642D78F-C7BCD8D7-E13580DB</ZastKod>
    <NakDost>false</NakDost>
  </Racun>
</RacunZahtjev>
"""

def main():
    print("="*80)
    print("DIRECT SOAP CLIENT TEST")
    print("="*80)
    print("\nThis test bypasses the agent system and directly calls FINA SOAP client")
    print("to see exactly what request/response looks like.\n")

    # Initialize SOAP client
    print("[1] Initializing FINA SOAP client...")
    client = FINASoapClient(
        environment=FINAEnvironment.SANDBOX,
        cert_path="client_cert.pem",
        key_path="client_key.pem",
        ca_cert_path="fina_demo_ca_bundle.pem",
        timeout=30
    )
    print("[OK] Client initialized\n")

    # Send request
    print("[2] Sending test XML to FINA DEMO...")
    print(f"    Endpoint: {client.endpoint}")
    print(f"    mTLS: client_cert.pem + client_key.pem")
    print(f"    CA Bundle: fina_demo_ca_bundle.pem\n")

    result = client.send_invoice(
        signed_xml=TEST_SIGNED_XML,
        message_id="test-direct-001"
    )

    print("\n" + "="*80)
    print("RESULT")
    print("="*80)
    print(f"Success: {result['success']}")
    print(f"JIR: {result['jir']}")
    print(f"Errors: {result.get('errors', [])}")
    if result.get('raw_response'):
        print(f"\nRaw Response (first 1000 chars):\n{result['raw_response'][:1000]}")
    print("="*80)

if __name__ == "__main__":
    main()
