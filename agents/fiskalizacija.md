Sveobuhvatna studija tehničke i procesne implementacije sustava Fiskalizacija 2.0 i integracija u arhitekturu autonomnih agenata (Google ADK)
1. Izvršni sažetak i strateški okvir
Digitalna transformacija poreznih sustava u Europskoj uniji dosegla je kritičnu točku konvergencije tehnologije, zakonodavstva i poslovnih procesa. Republika Hrvatska, kroz projekt "Fiskalizacija 2.0", pozicionira se u avangardu ovih promjena, prelazeći s modela naknadne kontrole na model kliringa u stvarnom vremenu (Continuous Transaction Controls - CTC). Ova studija pruža iscrpnu analizu tehničkih, pravnih i implementacijskih aspekata novog sustava koji stupa na snagu u punom opsegu za B2B (Business-to-Business) segment 1. siječnja 2026. godine.1
U središtu ove analize nalazi se inovativni pristup implementaciji kroz prizmu autonomnih agenata temeljenih na Google Agent Development Kit (ADK). Tradicionalni ERP sustavi često su rigidni i zahtijevaju opsežnu rekonfiguraciju za usklađivanje s novim poreznim pravilima. Nasuprot tome, predložena arhitektura "Fiskalnog Agenta" koristi napredne mogućnosti velikih jezičnih modela (LLM) za semantičko razumijevanje poslovnih događaja, dok istovremeno osigurava strogu determinističku točnost kroz strukturirane alate (Tools) i protokole definirane ADK okvirom.4
Izvještaj detaljno razrađuje tranziciju s papirnatih i PDF računa na strukturirani XML format sukladan europskoj normi EN 16931 i sintaksi UBL 2.1.5 Poseban naglasak stavljen je na nacionalnu specifikaciju HR-FISK 2.0, koja definira specifična pravila validacije i obvezne podatkovne elemente nužne za uspješnu fiskalizaciju.7 Kroz prizmu Google ADK-a, demonstrirat ćemo kako se kompleksni regulatorni zahtjevi mogu apstrahirati u modularne, ponovno iskoristive agentske komponente koje komuniciraju putem Agent-to-Agent (A2A) protokola, stvarajući time otporan i skalabilan ekosustav za financijsko poslovanje budućnosti.
2. Regulatorni pejzaž i evolucija poreznog nadzora
2.1. Od Fiskalizacije 1.0 do Fiskalizacije 2.0: Promjena paradigme
Inicijalna faza fiskalizacije u Hrvatskoj, uvedena 2013. godine, fokusirala se primarno na gotovinski promet i suzbijanje sive ekonomije u maloprodaji (B2C). Sustav se temeljio na sinkronoj komunikaciji naplatnih uređaja s poslužiteljem Porezne uprave radi dobivanja Jedinstvenog identifikatora računa (JIR). Iako uspješan, ovaj model je ostavio značajan dio gospodarstva – transakcijsko poslovanje između pravnih subjekata – izvan dosega nadzora u realnom vremenu.2
Fiskalizacija 2.0 predstavlja fundamentalnu promjenu paradigme. Ne radi se samo o digitalizaciji papirnatog procesa, već o potpunoj redefiniciji "vjerodostojne isprave". Prema novom Zakonu o fiskalizaciji, jedini pravno valjani račun u B2B transakcijama bit će onaj izdan u elektroničkom, strojno čitljivom formatu, koji je prošao kroz centralnu platformu i dobio fiskalni status.1
Ključni ciljevi ove reforme su višestruki:
Zatvaranje PDV jaza (VAT Gap): Eliminacija kružnih prijevara i "nestajućih trgovaca" kroz trenutni uvid u obje strane transakcije (izlazni račun dobavljača i ulazni račun kupca).3
Automatizacija knjiženja: Standardizirani XML format omogućuje primateljima automatski uvoz podataka u ERP sustave, eliminirajući ručni unos i pogreške koje iz njega proizlaze.
Real-time analitika: Država dobiva makroekonomske pokazatelje u realnom vremenu, što omogućuje brže reakcije ekonomske politike.
2.2. Zakonodavni rokovi i prijelazna razdoblja
Implementacija je strukturirana u faze kako bi se omogućila prilagodba tehnoloških rješenja i poslovnih procesa. Razumijevanje ovih rokova ključno je za razvojni tim koji planira implementaciju agenata:

Faza
Razdoblje
Opis Aktivnosti
Implikacije za Razvoj Agenta
Priprema
Trenutno - 31.08.2025.
Razvoj tehničkih specifikacija, prilagodba ERP-ova, interni razvoj.
Faza dizajna arhitekture, treniranje modela na UBL shemama, razvoj alata (Tools) u ADK.
Sandbox
01.09.2025. - 31.12.2025.
Dobrovoljno testiranje sustava bez pravnih posljedica.
"Live" testiranje A2A komunikacije, stress-testiranje API poziva prema FINA-i, validacija edge-case scenarija. 1
Mandat B2B
01.01.2026.
Početak obveze za sve obveznike PDV-a. Fiskalizacija pratećih isprava.
Agent mora biti u produkciji, sposoban za autonomno potpisivanje i slanje. Visoka razina pouzdanosti (99.9%). 1
Ekspanzija
01.01.2027.
Uključivanje malih poreznih obveznika, paušalista i ne-PDV obveznika.
Skaliranje sustava za masovno korištenje, prilagodba UX-a za manje tehnološki pismene korisnike. 1

2.3. Dualnost izvještavanja: e-Račun i e-Izvještavanje
Zakonodavni okvir uvodi distinkciju između dva toka podataka koji se moraju generirati i poslati. Za arhitekta sustava, ovo je kritična točka jer zahtijeva različite strategije obrade podataka.8
Razmjena e-Računa (Clearing): Ovo je proces slanja cjelokupnog dokumenta (UBL XML) od izdavatelja prema kupcu putem posrednika (npr. FINA). Ovaj dokument sadrži sve komercijalne detalje, opise stavki, ugovorne reference i priloge. To je "poslovni" dio transakcije.
Fiskalizacija (Reporting): Paralelno s razmjenom, određeni podskup podataka (Fiskalna poruka) šalje se Poreznoj upravi radi ovjere. Ovi podaci služe isključivo za porezni nadzor. Sustav "eRačun za državu" djeluje kao centralna točka koja objedinjuje oba procesa, ali tehnički gledano, to su dvije različite operacije koje se mogu odvijati sinkrono ili asinkrono.11
Za našeg Fiskalnog Agenta to znači da mora biti sposoban generirati bogati dataset za kupca (s detaljnim opisima koje generira LLM) i strogi dataset za Poreznu upravu (s preciznim KPD šiframa i poreznim osnovicama).
3. Dubinska analiza tehničkih standarda: EN 16931 i UBL 2.1
Uspjeh implementacije autonomnog agenta ovisi o njegovoj sposobnosti da "razmišlja" unutar ograničenja strogih tehničkih standarda. U kontekstu Fiskalizacije 2.0, taj standard je EN 16931, implementiran kroz sintaksu UBL 2.1 (Universal Business Language).5
3.1. Anatomija UBL 2.1 e-Računa
UBL je XML format razvijen od strane OASIS-a, dizajniran da bude univerzalno primjenjiv u globalnoj trgovini. Međutim, njegova univerzalnost znači da je iznimno opsežan. Za potrebe hrvatske fiskalizacije, koristi se "Core Invoice Usage Specification" (CIUS) koji definira podskup elemenata koji su obvezni ili dopušteni.
Struktura UBL računa može se podijeliti na nekoliko logičkih cjelina koje naš Agent mora popuniti:
3.1.1. Zaglavlje i Identifikatori (Header & IDs)
Svaki XML dokument počinje definicijom standarda.
cbc:UBLVersionID: Mora biti fiksirano na 2.1.
cbc:CustomizationID: Ovdje se definira CIUS profil. Za Hrvatsku to će vjerojatno biti varijacija identifikatora poput urn:cen.eu:en16931:2017#compliant#urn:mfin.hr:ciusext:hr-fisk:2.0.6 Agent mora dinamički odabrati ispravan ID ovisno o tipu računa.
cbc:ID: Broj računa. Kritično je da Agent validira format broja prema Zakonu o fiskalizaciji (trodijelna oznaka: Broj/PoslovniProstor/NaplatniUređaj). LLM ne smije "izmisliti" format; mora koristiti alat za generiranje sekvencijalnog broja.
3.1.2. Strane u transakciji (Accounting Parties)
Mapiranje poslovnih subjekata u XML strukturu zahtijeva preciznost.
Supplier (Izdavatelj): cac:AccountingSupplierParty. Ključni element je cac:PartyTaxScheme/cbc:CompanyID gdje se upisuje OIB s prefiksom "HR".
Customer (Kupac): cac:AccountingCustomerParty. Agent mora imati logiku za razlikovanje domaćih (HR OIB), EU (VAT ID) i trećih (Tax ID) subjekata, jer to utječe na validaciju sheme.15
3.1.3. Linije Računa (Invoice Lines) i Klasifikacija
Najveći izazov za AI agenta je ispravna klasifikacija stavki.
cac:InvoiceLine: Svaka stavka.
cbc:InvoicedQuantity: Zahtijeva unitCode prema UN/ECE Rec 20 (npr. "H87" za komad, "KGM" za kilogram). Agent mora mapirati korisnikov unos "5 komada" u unitCode="H87".
KPD 2025 Klasifikacija: Fiskalizacija 2.0 uvodi obvezno korištenje Klasifikacije proizvoda po djelatnostima (KPD). U XML-u se to obično mapira u element cac:Item/cac:CommodityClassification/cbc:ItemClassificationCode.8
Insight za implementaciju: Ovdje LLM (npr. Gemini unutar ADK) pokazuje svoju pravu vrijednost. Dok klasični softver traži od korisnika da ručno odabere šifru "62.01.11 - Usluge projektiranja softvera", Agent može analizirati opis usluge "Izrada web stranice" i samostalno predložiti odgovarajuću KPD šifru s visokom vjerojatnošću točnosti, tražeći potvrdu samo u slučaju nesigurnosti.
3.1.4. Porezni Totali (Tax Totals)
Matematička točnost XML-a je binarna – ili je točan ili se odbija.
cac:TaxTotal: Ukupni porez.
cac:TaxSubtotal: Grupiranje po poreznim stopama (npr. osnovica za 25%, osnovica za 0%).
Sustav FINA-e validira da je Sum(TaxSubtotal) == TaxTotal s točnošću na dvije decimale. Agent ne smije koristiti LLM za aritmetiku ("Koliko je 100 * 0.25?"). Mora koristiti deterministički alat (Python decimal modul) za izračun.17
3.2. Specifičnosti HR-FISK 2.0 ekstenzija
Osim standardnih UBL polja, hrvatska specifikacija može zahtijevati specifične ekstenzije za potrebe fiskalnog nadzora, kao što su:
Poziv na broj zaduženja (Model i broj) u cac:PaymentMeans/cbc:PaymentID.
Oznaka načina plaćanja (Gotovina, Kartica, Transakcijski račun) koja mora biti usklađena s šifrarnikom Porezne uprave.
Fiskalni kodovi za oslobođenje od PDV-a (npr. prijenos porezne obveze) koji se upisuju u cac:TaxCategory/cbc:TaxExemptionReasonCode.16
4. Google Agent Development Kit (ADK): Arhitektura rješenja
Google ADK pruža robustan okvir za izgradnju agenata koji nisu samo "chatboti", već izvršni sustavi. Za potrebe financijskog agenta, ključne su tri komponente ADK-a: LlmAgent, Tools (Alati) i Workflows (Tijekovi rada).4
4.1. Konceptualni model "Fiskalnog Agenta"
Naš agent ne funkcionira kao monolitni blok koda, već kao orkestrator niza specijaliziranih alata. Arhitektura se može opisati kroz sljedeće slojeve:
Sloj Interakcije (Interaction Layer): Prima nestrukturirani input od korisnika ili drugog agenta (npr. "Fakturiraj klijentu X uslugu Y").
Kognitivni Sloj (Reasoning Layer): LlmAgent (pogonjen modelom Gemini 2.0 Flash ili Pro) analizira namjeru, ekstrahira entitete (Kupac, Iznos, Datum) i odlučuje koji alat pozvati.18
Sloj Izvršavanja (Execution Layer): Skup determinističkih funkcija (Tools) napisanih u Pythonu ili Go-u koje obavljaju stvarne operacije (validacija, generiranje XML-a, potpisivanje).
Sloj Komunikacije (Communication Layer): Upravlja A2A protokolom i vanjskim API pozivima prema FINA-i.4
4.2. Definiranje Alata (Tools) u ADK
Sigurnost i točnost su imperativi. LLM nikada ne smije izravno generirati XML kod jer je sklon halucinacijama (npr. izmišljanje nepostojećih tagova). Umjesto toga, LLM priprema podatke za funkciju koja generira XML.
Ovo je popis ključnih alata koje moramo implementirati u ADK:
Naziv Alata
Opis Funkcionalnosti
Tip Izlaza
lookup_partner_vies
Provjerava OIB u VIES bazi ili sudskom registru. Vraća točan naziv i adresu.
JSON Object
classify_kpd_code
Pomoćni alat koji mapira opisni tekst usluge u KPD 2025 šifru.
String (Code)
calculate_tax_breakdown
Prima neto iznose i stope, vraća precizne iznose poreza i ukupne totale (koristeći decimal biblioteku).
JSON Object
construct_ubl_xml
Prima validirani JSON objekt s podacima računa i vraća serijalizirani, validirani XML string.
XML String
sign_xades
Prima XML, kanonikalizira ga i digitalno potpisuje privatnim ključem (XAdES-BES).
Signed XML
transmit_fina_soap
Šalje omotnicu s e-računom na FINA web servis i čeka sinkroni odgovor.
Response Object

4.3. Implementacija LlmAgent konfiguracije
U Google ADK, konfiguracija agenta povezuje model s alatima i daje mu "osobnost" putem sistemskih instrukcija.

Python


# Primjer konfiguracije Fiskalnog Agenta u Google ADK (Python)

from google.adk import LlmAgent, Tool
from my_fiscal_tools import (
    lookup_partner_vies, 
    construct_ubl_xml, 
    sign_xades, 
    transmit_fina_soap
)

# Definiranje sistemskih instrukcija je ključno za ponašanje agenta
SYSTEM_INSTRUCTIONS = """
Ti si Fiskalni Agent, specijalizirani autonomni sustav za izdavanje e-računa sukladno zakonu Fiskalizacija 2.0 u Hrvatskoj.
Tvoja uloga je osigurati tehničku ispravnost i zakonitost svake transakcije.

PROTOKOL RADA:
1.  **Analiza Zahtjeva:** Kada dobiješ zahtjev za izdavanje računa, prvo identificiraj Kupca i Stavke.
2.  **Verifikacija Podataka:** NIKADA ne vjeruj korisničkom unosu za OIB ili adresu. UVIJEK koristi alat `lookup_partner_vies` za dohvat službenih podataka.
3.  **Klasifikacija:** Za svaku stavku, ako nije navedena KPD oznaka, pokušaj je inferirati iz opisa, ali traži potvrdu ako je pouzdanost niska.
4.  **Konstrukcija:** Koristi alat `construct_ubl_xml` za kreiranje dokumenta. Ne pokušavaj pisati XML ručno.
5.  **Sigurnost:** Prije slanja, dokument MORA biti potpisan alatom `sign_xades`.
6.  **Slanje:** Pošalji potpisan dokument putem `transmit_fina_soap`.
7.  **Izvještavanje:** Interpretiraj odgovor servisa (MessageAck). Ako je status 'ACCEPTED', potvrdi korisniku. Ako je 'MSG_NOT_VALID', analiziraj grešku i predloži ispravak.

RUKOVANJE GREŠKAMA:
Ako FINA servis vrati grešku, ne izmišljaj razlog. Citiraj ErrorMessage iz odgovora alata.
"""

fiscal_agent = LlmAgent(
    name="hr_fiscal_agent_v1",
    model="gemini-2.0-flash",  # Odabir modela optimiziranog za brzinu i praćenje instrukcija
    tools=[
        lookup_partner_vies,
        construct_ubl_xml,
        sign_xades,
        transmit_fina_soap
    ],
    instructions=SYSTEM_INSTRUCTIONS
)


5. Proces implementacije korak-po-korak
Implementacija ovakvog sustava u praksi zahtijeva rigorozan pristup. Analizirat ćemo ključne tehničke izazove u svakom koraku procesa.
5.1. Korak 1: Priprema i Validacija Podataka
Prije nego što se XML uopće počne generirati, podaci moraju biti "očišćeni". Najčešći razlog odbijanja e-računa su neispravni matični podaci.
Izazov: Korisnik kaže "Izdaj račun tvrtki Info-Tech". Postoji pet tvrtki s sličnim imenom.
Rješenje Agenta: Agent koristi lookup_partner_vies (ili API sudskog registra) za pretragu po imenu. Ako nađe više rezultata, LLM generira upit za razjašnjenje: "Pronašao sam Info-Tech d.o.o. iz Zagreba i Info-Tech j.d.o.o. iz Splita. Na kojeg mislite?". Tek kada dobije jedinstveni OIB, nastavlja dalje.
Također, agent mora provjeriti status poreznog obveznika. Ako partner nije u sustavu PDV-a, agent ne smije obračunati prijenos porezne obveze, čak i ako korisnik to zatraži.
5.2. Korak 2: Konstrukcija UBL 2.1 XML-a (Data Mapping)
Ovo je najkompleksniji dio. Python skripta unutar alata construct_ubl_xml mora mapirati jednostavne podatke u hijerarhijsku XML strukturu.
Prikaz kritičnog mapiranja (Tablica mapiranja):
Podatak (Business Term)
UBL 2.1 XML Putanja (XPath)
Napomena / Pravilo Validacije
Datum Izdavanja
/Invoice/cbc:IssueDate
Format YYYY-MM-DD. Ne smije biti u budućnosti.
OIB Izdavatelja
/Invoice/cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID
Prefiks "HR" obavezan. Shema VAT.
OIB Kupca
/Invoice/cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID
Ako je HR, prefiks "HR". Mora odgovarati podacima iz registra.
Valuta Računa
/Invoice/cbc:DocumentCurrencyCode
ISO 4217 kod (npr. "EUR").
Ukupni Iznos Bez PDV
/Invoice/cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount
Mora biti jednak zbroju svih linija.
Ukupni Iznos Za Platiti
/Invoice/cac:LegalMonetaryTotal/cbc:PayableAmount
Iznos s porezom.
KPD Oznaka Stavke
/Invoice/cac:InvoiceLine/cac:Item/cac:CommodityClassification/cbc:ItemClassificationCode
Prema šifrarniku KPD 2025. Atribut listID mora biti definiran.
Poziv na Broj
/Invoice/cac:PaymentMeans/cbc:PaymentID
Format HR68... (Model i poziv na broj).

5.3. Korak 3: Sigurnost i Digitalno Potpisivanje (PKI)
Fiskalizacija 2.0 zahtijeva integritet podataka. To se postiže digitalnim potpisom XML-a. Agent mora imati pristup privatnom ključu aplikacijskog certifikata (izdanog od FINA-e).
Sigurnosna Arhitektura:
Nikada ne pohranjujte privatni ključ u kod ili prompt agenta. Umjesto toga, koristite sigurne spremnike (npr. Google Secret Manager ili Azure Key Vault). Alat sign_xades trebao bi:
Dohvatiti ključ iz sigurnog spremnika u memoriju (samo za vrijeme trajanja operacije).
Izvršiti kanonikalizaciju XML-a (C14N) kako bi se osiguralo da formatiranje ne utječe na hash.
Kreirati SHA-256 sažetak (digest) dokumenta.
Potpisati sažetak RSA ključem (2048 bit ili jači).
Formirati ds:Signature strukturu prema XAdES-BES standardu i umetnuti je u XML (obično kao ekstenziju UBL-a). 6
5.4. Korak 4: Razmjena Podataka (SOAP Komunikacija)
Komunikacija s FINA sustavom odvija se putem SOAP protokola s WS-Security ekstenzijama (ili AS4 protokola za napredne korisnike). Agentov alat transmit_fina_soap djeluje kao klijent.
Tijek komunikacije:
Priprema Omotnice: Potpisani UBL XML se omata u SOAP omotnicu (Envelope). FINA specificira točan format zaglavlja (MsgHeader) koji sadrži MessageID, SenderId, ReceiverId.
Slanje (Request): Poziv metode SendB2BOutgoingInvoiceMsg.17
Zaprimanje Odgovora (Response): FINA vraća MessageAck.
Analiza Statusa:
Ako je AckStatus = ACCEPTED: Račun je uspješno zaprimljen, fiskaliziran i prosljeđuje se kupcu. Agent sprema MessageAckID kao dokaz.
Ako je AckStatus = MSG_NOT_VALID: Račun je odbijen. Odgovor sadrži niz Error objekata (kod i opis). Agent mora ovo parsirati i "prevesti" korisniku (npr. "Greška 205: Neispravan OIB kupca"). 17
6. Integracija u širi sustav: Agent-to-Agent (A2A) Protokol
Snaga Google ADK-a leži u mogućnosti povezivanja više agenata. Naš Fiskalni Agent ne mora biti onaj koji komunicira s krajnjim korisnikom. On može biti "pozadinski servis" kojeg koriste drugi agenti.
6.1. Ekspozicija Agenta (Exposing)
Koristeći ADK funkcionalnost to_a2a, pretvaramo našeg lokalnog agenta u mikroservis dostupan preko mreže.

Python


# Pseudo-kod za pokretanje A2A servera
from google.adk.a2a import to_a2a
import uvicorn

# fiscal_agent je instanca LlmAgent-a definirana ranije
a2a_app = to_a2a(fiscal_agent)

if __name__ == "__main__":
    # Pokreće agenta na portu 8000
    uvicorn.run(a2a_app, host="0.0.0.0", port=8000)


Ovim postupkom ADK automatski generira Agent Card (agent-card.json) na endpointu /.well-known/agent-card.json. Ovaj JSON dokument opisuje agenta: njegovo ime, opis, i što je najvažnije – shemu ulaznih i izlaznih podataka. 4
6.2. Konzumacija Agenta (Consuming)
Zamislimo "Prodajnog Agenta" (Sales Agent) koji vodi web trgovinu. Kada kupac završi kupnju, Prodajni Agent ne mora znati ništa o UBL-u ili SOAP-u. On jednostavno delegira zadatak Fiskalnom Agentu.
U ADK-u se to radi definiranjem RemoteA2aAgent:

Python


from google.adk import RemoteA2aAgent

# Prodajni agent definira fiskalnog agenta kao resurs
fiscal_remote = RemoteA2aAgent(
    name="fiscal_service",
    url="http://fiscal-agent-service:8000",
    description="Koristi se za finalizaciju narudžbe i izdavanje službenog e-računa."
)

# Prodajni agent sada može u svojim instrukcijama imati:
# "Kada korisnik potvrdi plaćanje, pošalji detalje narudžbe agentu 'fiscal_service' radi izdavanja računa."


Ova modularnost omogućuje timovima da neovisno razvijaju dijelove sustava. Tim za financije održava Fiskalnog Agenta i njegove alate (ažurira porezne stope, certifikate), dok tim za prodaju radi na Prodajnom Agentu, ne brinući o tome hoće li promjena PDV-a srušiti web shop.
7. Izazovi u praksi i strategije ublažavanja rizika
Implementacija ovakvog sustava nosi specifične rizike koje arhitektura mora adresirati.
7.1. Upravljanje Pogreškama i Nedostupnost Servisa (Resilience)
Državni servisi mogu biti privremeno nedostupni. Fiskalizacija 2.0 propisuje da se u slučaju prekida veze račun mora fiskalizirati naknadno (obično u roku od 48 sati), ali se kupcu mora izdati odmah s posebnom oznakom.
Rješenje Agenta:
Agent mora imati implementiran Circuit Breaker uzorak.
Ako transmit_fina_soap ne uspije zbog mrežne greške (timeout), agent ne ruši proces.
Umjesto toga, generira račun s oznakom "Izdano u vrijeme prekida veze" (prema specifikaciji).
Sprema potpisani XML u red čekanja (Queue) za ponovno slanje.
Poseban "Worker" proces (izvan LLM toka) periodički pokušava poslati račune iz reda čekanja dok servis ne postane dostupan.
7.2. "Halucinacije" Modela kod Klasifikacije
Najveći rizik kod korištenja AI za financije je netočna klasifikacija (npr. odabir krive KPD šifre što rezultira krivom poreznom stopom).
Strategija Ublažavanja (Human-in-the-loop):
Agent nikada ne bi trebao automatski poslati račun ako je pouzdanost klasifikacije niska. U promptu alata classify_kpd_code treba tražiti da model vrati i confidence_score.
Ako je confidence > 0.95: Automatsko procesiranje.
Ako je confidence < 0.95: Agent vraća odgovor korisniku: "Mislim da se ova usluga klasificira kao 'Računalno programiranje' (J6201), jeste li sigurni? Moguće alternative su..."
7.3. Sigurnost i GDPR
E-računi sadrže osobne podatke (imena, adrese fizičkih osoba u obrtima).
Data Minimization: Agent u svojoj "memoriji" (context window) ne smije čuvati povijest svih računa. Kontekst se mora čistiti nakon svake transakcije.
Audit Trail: Svaka akcija agenta (tko je zatražio račun, koji alat je pozvao, kakav je XML generirao) mora biti logirana u nepromjenjiv (immutable) log sustav radi potencijalne porezne revizije. ADK omogućuje logging hook-ove za praćenje izvršavanja alata.
8. Zaključak i preporuke
Implementacija e-računa u okviru Fiskalizacije 2.0 predstavlja jedan od najzahtjevnijih IT projekata za hrvatsko gospodarstvo u ovom desetljeću. Prijelaz na UBL 2.1 format i obveza real-time izvještavanja zahtijevaju napuštanje ad-hoc rješenja i prelazak na robusne, automatizirane sustave.
Analiza pokazuje da integracija Google ADK okvira nudi značajne prednosti pred tradicionalnim razvojem:
Fleksibilnost: LlmAgent može interpretirati nestrukturirane zahtjeve ("fakturiraj onaj ručak"), smanjujući administrativni teret za korisnike.
Modularnost: Korištenje A2A protokola omogućuje da fiskalna logika bude centralizirana i održavana na jednom mjestu, a dostupna svim dijelovima organizacije.
Skalabilnost: Jasna separacija između kognitivnog sloja (LLM) i izvršnog sloja (Tools) osigurava da sustav ostane deterministički točan u kritičnim operacijama (izračun poreza, potpisivanje), dok zadržava AI inteligenciju u interakciji i klasifikaciji.
Preporuka za implementaciju:
Organizacije bi trebale iskoristiti razdoblje "Sandboxa" (jesen 2025.) za intenzivno testiranje svojih agenata. Ključ uspjeha nije u tome da AI radi sve, već u tome da AI pametno orkestrira provjerene, sigurne alate koji jamče zakonsku usklađenost. Ovakav hibridni pristup – umjetna inteligencija vođena strogim pravilima – predstavlja budućnost financijskog softvera.
Citirani radovi
E-Invoicing CROATIA - MENOCARTA, pristupljeno studenoga 25, 2025, https://menocarta.net/en/einvoicing/einvoicing-croatia/
Fiskalizacija 2.0: Što se mijenja i kako se pripremiti (2026.)? - Fiskalopedija.hr, pristupljeno studenoga 25, 2025, https://fiskalopedija.hr/baza-znanja/fiskalizacija-20
E-Invoicing in Croatia (B2B, B2G E-Invoices & Fiscalization in 2026) - DDD Invoices, pristupljeno studenoga 25, 2025, https://dddinvoices.com/learn/e-invoicing-croatia
Index - Agent Development Kit - Google, pristupljeno studenoga 25, 2025, https://google.github.io/adk-docs/
EU Directive EN 16931: Standardised E-Invoicing Compliance - eClear, pristupljeno studenoga 25, 2025, https://eclear.com/knowledge/e-invoicing/eu-directive-en-16931/
Briefing Document & Podcast: Croatia – E-Invoicing, E-Reporting, and E-Transport – Scope and Timeline - VATupdate, pristupljeno studenoga 25, 2025, https://www.vatupdate.com/2025/10/25/e-invoicing-in-croatia-a-briefing-document/
Tehničke specifikacije za pripremu razmjene i fiskalizacije eRačuna - Porezna uprava, pristupljeno studenoga 25, 2025, https://porezna.gov.hr/fiskalizacija/bezgotovinski-racuni/bezgotovinski-racuni-novosti/o/tehnicke-specifikacije
Fiskalizacija 2.0 / eRačun - Porezna uprava, pristupljeno studenoga 25, 2025, https://porezna.gov.hr/fiskalizacija/bezgotovinski-racuni/fiskalizacija-bezgotovinskih-racuna
Tehnička specifikacija eRačuna - Fiskalizacija 2.0, pristupljeno studenoga 25, 2025, https://fiskalizacija2.hr/rjecnik-fiskalizacije-2-0/tehnicka-specifikacija-eracuna/
Fiskalizacija 2.0 i čarter - što donose nova pravila od 2026., pristupljeno studenoga 25, 2025, https://www.xn--arter-gya.hr/trendovi/fiskalizacija-i-carter-sto-donose-nova-pravila
eInvoicing in Croatia - European Commission, pristupljeno studenoga 25, 2025, https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108879/eInvoicing+in+Croatia
Croatia Confirms Mandatory B2B Electronic Invoice Launch for 2026: Fiscalization Project 2.0 | EDICOM Global, pristupljeno studenoga 25, 2025, https://edicomgroup.com/blog/croatia-electronic-invoicing-b2b
Universal Business Language - Wikipedia, pristupljeno studenoga 25, 2025, https://en.wikipedia.org/wiki/Universal_Business_Language
Universal Business Language Version 2.1 - Index of /, pristupljeno studenoga 25, 2025, https://docs.oasis-open.org/ubl/UBL-2.1.html
Field Mapping for UBL Format, pristupljeno studenoga 25, 2025, https://docs.oracle.com/en/industries/financial-services/revenue-management-billing/60000/ormb-online-help/Topics/C1_Field_Mapping_for_UBL_Format.html
UBL 2.0 and UBL 2.1 qualified information items - Index of / - OASIS Open, pristupljeno studenoga 25, 2025, https://docs.oasis-open.org/ubl/prd1-UBL-2.1/cva/UBL-DefaultDTQ-2.1.html
Technical specifications - Invoicing for web services - Fina, pristupljeno studenoga 25, 2025, https://www.fina.hr/digitalizacija-poslovanja/e-racun/tehnicka-specifikacija/technical-specifications-invoicing-for-web-services
LLM agents - Agent Development Kit - Google, pristupljeno studenoga 25, 2025, https://google.github.io/adk-docs/agents/llm-agents/
Technical specifications - for the government using other methods - Fina, pristupljeno studenoga 25, 2025, https://www.fina.hr/javne-usluge/e-racun-u-javnoj-nabavi/tehnicka-specifikacija/technical-specifications-for-the-government-using-other-methods
Web service for e-Invoice for business users with asynchronous processing - Fina, pristupljeno studenoga 25, 2025, https://www.fina.hr/digitalizacija-poslovanja/e-racun/tehnicka-specifikacija/technical-specification-web-service-for-e-invoice-for-business-users-with-asynchronous-processing


Tehnički Vodič za Implementaciju i Testiranje Sustava Fiskalizacija 2.0: Arhitektura, Protokoli i Validacija
1. Strateški Kontekst i Uvod u Ekosustav Fiskalizacije 2.0
1.1. Evolucija Poreznog Nadzora: Od Post-Audit do CTC Modela
Uvođenje sustava "Fiskalizacija 2.0" u Republici Hrvatskoj ne predstavlja samo tehnološku nadogradnju postojeće infrastrukture, već označava fundamentalnu promjenu paradigme u načinu na koji porezna tijela nadziru ekonomsku aktivnost. Dok se Fiskalizacija 1.0, uvedena 2013. godine, primarno fokusirala na maloprodaju i gotovinski promet (B2C) kroz model trenutne ovjere računa, Fiskalizacija 2.0 širi taj nadzor na cjelokupni B2B (Business-to-Business) segment.
Ovaj potez usklađen je s globalnim trendom prelaska s modela naknadne revizije (Post-Audit), gdje se porezne knjige provjeravaju mjesecima ili godinama nakon transakcije, na model kontinuirane kontrole transakcija (Continuous Transaction Controls - CTC). U CTC modelu, porezno tijelo dobiva uvid u podatke o transakciji u trenutku njezina nastanka ili neposredno nakon toga. Za razvojne inženjere i sistemske arhitekte, ovo znači da financijski softver više ne može biti izolirani "silos" podataka; on mora postati aktivni čvor u nacionalnoj mreži razmjene podataka u stvarnom vremenu.
Ključna razlika, a time i glavni izazov za testiranje, leži u dualnosti procesa. Fiskalizacija 2.0 sastoji se od dvije paralelne, ali tehnološki različite komponente:
e-Račun (Clearing): Standardizirana razmjena elektroničkih računa između poslovnih subjekata putem posrednika, temeljena na europskoj normi EN 16931.
e-Izvještavanje (Reporting): Slanje fiskalnih podataka Poreznoj upravi radi nadzora PDV-a.
Razumijevanje ove dualnosti ključno je za postavljanje testne strategije, jer zahtijeva validaciju dva različita toka podataka, dva različita protokola (AS4 i SOAP) i dva različita skupa validacijskih pravila.
1.2. Regulatorni Okvir i Rokovi kao Razvojni Parametri
Zakonodavni okvir postavlja čvrste granice unutar kojih se tehničko rješenje mora kretati. Za razvojne timove, najkritičniji datum je 1. rujna 2025., kada službeno započinje rad s testnom okolinom (Sandbox), dok puna produkcijska obveza stupa na snagu 1. siječnja 2026..1
Ovo prijelazno razdoblje od četiri mjeseca nije samo administrativni rok, već tehnička nužnost. Ono omogućuje "live" testiranje interoperabilnosti između različitih ERP sustava i informacijskih posrednika. Za razliku od internog testiranja, gdje kontrolirate obje strane transakcije, u ovom ekosustavu vaš softver mora ispravno interpretirati poruke generirane od strane desetaka različitih softverskih rješenja drugih proizvođača. Stoga je strategija testiranja u "Sandboxu" kritična faza razvoja, a ne opcionalna aktivnost.
Zahtjev korisnika za informacijama o tome "moraju li se koristiti pravi računi" adresira se upravo kroz koncept testne okoline. Korištenje produkcijskih računa za testiranje strogo je zabranjeno i pravno rizično jer bi generiralo lažne porezne obveze. Sustav je dizajniran tako da striktno odvaja testne podatke od produkcijskih, koristeći zasebne krajnje točke (endpoints) i certifikate, čime se osigurava integritet poreznog sustava.
2. Arhitektura Sustava i Infrastruktura Testne Okoline
Prije ulaska u kodiranje, nužno je razumjeti topologiju sustava s kojim se integrirate. Arhitektura Fiskalizacije 2.0 je distribuirana i oslanja se na centralizirani registar adresiranja, ali decentraliziranu razmjenu dokumenata.
2.1. Centralni Informacijski Sustav (CIS) i Njegove Komponente
Centralni informacijski sustav Porezne uprave (CIS) djeluje kao srce sustava, ali za razliku od Fiskalizacije 1.0, on nije jedina točka kontakta. Arhitektura se sastoji od tri ključna modula s kojima vaš softver mora komunicirati:
Sustav Fiskalizacije (Fiscalization Service):
Uloga: Zaprimanje podataka o računima radi poreznog nadzora.
Protokol: SOAP (Simple Object Access Protocol) preko HTTPS-a.
Interakcija: Sinkrona. Vaš sustav šalje zahtjev, CIS vraća JIR (Jedinstveni identifikator računa) ili grešku.
Adresar Metapodatkovnih Servisa (AMS):
Uloga: Centralni registar koji mapira OIB primatelja na njegovu tehničku pristupnu točku.
Protokol: REST (Representational State Transfer).
Interakcija: Vaš sustav pita "Gdje šaljem račun za OIB 12345678901?", a AMS vraća URL odgovarajućeg Metapodatkovnog servisa.
Metapodatkovni Servis (MPS):
Uloga: Pružanje detaljnih tehničkih parametara za slanje računa (npr. certifikat primatelja, podržani protokoli).
Protokol: REST.
Lokacija: MPS se može nalaziti na infrastrukturi Porezne uprave (za male obveznike) ili kod Informacijskih posrednika (za veće sustave).
2.2. Dualnost Okolina: Sandbox vs. Produkcija
Porezna uprava i APIS IT uspostavili su testnu okolinu koja je fizički i logički odvojena od produkcije. Ovo je odgovor na pitanje korisnika o "testnom API-ju". Ne postoji samo jedan API, već cijeli paralelni svemir servisa.
Tablica u nastavku prikazuje detaljan pregled pristupnih točaka (Endpoints) koje razvojni timovi moraju konfigurirati u svojim aplikacijama. Ključno je uočiti razlike u portovima i poddomenama kako bi se izbjeglo slučajno slanje testnih podataka u produkciju.
Komponenta Sustava
Namjena
Protokol
Testna Okolina (Sandbox) URL
Produkcijska Okolina URL
Fiskalizacija
Slanje fiskalnih podataka (Reporting)
SOAP / HTTPS
https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest
https://cis.porezna-uprava.hr:8449/FiskalizacijaService
Metapodatkovni Servis (MPS)
Otkrivanje podataka o primatelju
REST
https://cis.porezna-uprava.hr:8515/proxy (via AMS)
https://cis.porezna-uprava.hr:8411/...
Adresar (AMS)
Upit za lokaciju MPS-a
REST
https://cis.porezna-uprava.hr:8515/proxy
https://cis.porezna-uprava.hr:8513/proxy
Portal za Testiranje
Administrativno sučelje za validaciju
Web (HTTPS)
https://pts.porezna-uprava.hr/ (dostupno kroz ePoreznu)
N/A (Integrirano u produkcijski nadzor)

Tablica 1: Pregled tehničkih pristupnih točaka za testnu i produkcijsku okolinu.3
Tehnička napomena za mrežne administratore:
Testna okolina često koristi self-signed ili certifikate izdane od strane internog CA tijela (npr. FINA Demo CA). Vaši vatrozidi (firewalls) moraju dopustiti izlazni promet na portovima 8449 i 8515 prema domeni apis-it.hr i porezna-uprava.hr. Blokada ovih portova najčešći je uzrok inicijalnih problema pri povezivanju ("Connection Timed Out").
2.3. Sigurnosna Infrastruktura (PKI) i Upravljanje Certifikatima
Sigurnost u Fiskalizaciji 2.0 nije temeljena na jednostavnim korisničkim imenima i lozinkama (API Keys), već na robusnoj infrastrukturi javnog ključa (PKI). To znači da svaki zahtjev koji vaš softver pošalje mora biti:
Autentificiran na transportnom sloju (Mutual TLS / 2-way SSL).
Potpisan na aplikativnom sloju (Digitalni potpis XML-a).
Za testiranje ne smijete koristiti svoje produkcijske poslovne certifikate. Morate pribaviti specifične Demo certifikate.
2.3.1. Procedura ishođenja Demo certifikata
Proces dobivanja testnih vjerodajnica je formaliziran i uključuje interakciju s FINA-om kao ovlaštenim izdavateljem certifikata (CSP).
Preuzimanje Dokumentacije: Na stranicama FINA-e potrebno je pronaći "Zahtjev za izdavanje Demo certifikata za fiskalizaciju".
Popunjavanje Zahtjeva: U zahtjevu se navode podaci o tvrtki (OIB) i podaci o osobi koja će biti skrbnik certifikata. Važno je napomenuti da se za testiranje može koristiti OIB informatičke tvrtke koja razvija softver, ne nužno krajnjeg korisnika.
Predaja i Aktivacija: Dokumentacija se šalje na certifikati-fiskalizacija@fina.hr. Nakon obrade, skrbnik dobiva dva dijela aktivacijskog koda (jedan mailom, jedan SMS-om).
Generiranje Ključeva: Certifikat se preuzima putem portala demo-mojcert.fina.hr. Rezultat je datoteka (obično.p12 ili.pfx) koja sadrži privatni i javni ključ.
Kritična točka za developere: Ovaj .p12 certifikat morate uvesti u "KeyStore" vaše aplikacije. Lozinka kojom ste zaštitili certifikat prilikom preuzimanja bit će potrebna vašem softveru svaki put kada inicira SSL vezu ili potpisuje XML.6
2.3.2. Trust Chain i Poslužiteljski Certifikati
Vaša aplikacija također mora "vjerovati" serveru Porezne uprave. U testnoj okolini, server koristi certifikat cistest.apis-it.hr. Budući da je ovaj certifikat izdao "FINA Demo CA", vaš operativni sustav ili runtime okolina (npr. Java JRE, Python certifi) ga vjerojatno neće prepoznati automatski.
Akcija: Morate preuzeti FINA Demo Root CA i FINA Demo Subordinate CA certifikate sa stranica FINA-e i ručno ih dodati u "TrustStore" vaše aplikacije. Ako to ne učinite, dobit ćete grešku tipa PKIX path building failed ili SSLHub::UntrustedCertificate.
3. Vodič za Developere: Struktura Podataka i Validacija (UBL 2.1)
Srž Fiskalizacije 2.0 je standardizirani format podataka. Napuštanje vlasničkih (proprietary) formata i prelazak na UBL 2.1 (Universal Business Language) znači da developeri moraju ovladati kompleksnom XML shemom koja je istovremeno fleksibilna i stroga.
3.1. Anatomija e-Računa prema HR-CIUS Specifikaciji
Iako je UBL 2.1 globalni standard, svaka država definira svoja specifična pravila korištenja, tzv. CIUS (Core Invoice Usage Specification). Hrvatska specifikacija (HR-FISK 2.0) definira koja su polja obavezna, a koja opcionalna.
Vaš XML generator mora biti sposoban ispravno popuniti sljedeće kritične segmente:
1. Identifikacija Profila (Customization ID):
Ovo je prvo polje koje validator provjerava. Ako je pogrešno, račun se odbija instantno.

XML


<cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:mfin.gov.hr:cius-2025:1.0...</cbc:CustomizationID>


Ovaj string govori sustavu: "Ovo je račun sukladan EU normi, ali s hrvatskim specifičnostima verzije 2025.".1
2. Poslovni Partneri i OIB:
Standardni UBL koristi generičke ID elemente. U HR kontekstu, OIB je obavezan i mora se nalaziti u specifičnom atributu sheme:

XML


<cac:PartyTaxScheme>
    <cbc:CompanyID>HR12345678901</cbc:CompanyID>
    <cac:TaxScheme>
        <cbc:ID>VAT</cbc:ID>
    </cac:TaxScheme>
</cac:PartyTaxScheme>


Prefiks "HR" je obavezan za obveznike PDV-a. Testni sustav će validirati kontrolnu znamenku OIB-a (Modul 11, 10). Korištenje nasumičnih brojeva dovest će do greške. Za testiranje koristite validne OIB-ove (npr. vlastite tvrtke ili javno dostupne OIB-ove velikih subjekata u testne svrhe, uz anonimizaciju ostalih podataka).
3. Klasifikacija Proizvoda (KPD 2025):
Jedan od najvećih izazova implementacije je mapiranje artikala. Svaka stavka računa mora imati pridruženu šifru iz "Klasifikacije proizvoda po djelatnostima".

XML


<cac:Item>
    <cac:CommodityClassification>
        <cbc:ItemClassificationCode listID="KPD2025">12.34.56</cbc:ItemClassificationCode>
    </cac:CommodityClassification>
</cac:Item>


Vaš ERP sustav mora imati šifrarnik KPD 2025 i logiku koja povezuje interne šifre artikala s ovim oznakama. U testnoj fazi, pokušajte poslati račune s različitim kategorijama proizvoda (roba, usluga, energija) kako biste osigurali da se sve varijante ispravno procesuiraju.
3.2. Najčešće Greške u Validaciji i Kako ih Izbjeći
Analiza dosadašnjih iskustava s e-Računima ukazuje na ponavljajuće obrasce grešaka koje developeri trebaju anticipirati:
Greške u Zaokruživanju (Rounding Errors): UBL zahtijeva da se porez računa na razini linije, a zatim sumira. Međutim, validacija često provjerava i obrnuti smjer (sumiranje osnovica pa izračun poreza). Razlika od 0.01 EUR je dovoljna da CIS odbije račun.
Rješenje: Koristite biblioteke za preciznu decimalnu aritmetiku (npr. BigDecimal u Javi, decimal u Pythonu/C#). Nikada ne koristite float ili double za financijske iznose.
Neispravni Datumi: Datum izdavanja računa (IssueDate) ne smije biti u budućnosti. U testnoj okolini, serveri su sinkronizirani na točno vrijeme. Ako vaš server kasni ili žuri nekoliko minuta, to obično nije problem, ali veća odstupanja mogu uzrokovati probleme s vremenskim žigom.
Prazni Elementi: XML parseri Porezne uprave strogi su prema praznim tagovima (npr. <cbc:Note></cbc:Note>). Ako nemate podatak, nemojte generirati tag. Prazan tag se smatra nevalidnim prema XSD shemi.
4. Protokoli Komunikacije: Deep Dive
Ovaj odjeljak pruža "low-level" uvid u formate poruka koje vaš softver mora generirati.
4.1. SOAP Protokol za Fiskalizaciju (Reporting)
Ovaj kanal koristi se za prijavu fiskalnih podataka. Iako sličan staroj fiskalizaciji, shema je nova.
Struktura Poruke:
SOAP omotnica (Envelope) mora sadržavati zaglavlje (Header) i tijelo (Body). Zaglavlje je kritično za sigurnost.

XML


<soapenv:Header>
    <wsse:Security>
        <wsse:BinarySecurityToken>...</wsse:BinarySecurityToken>
        <ds:Signature>
            </ds:Signature>
    </wsse:Security>
</soapenv:Header>


Poruka tijela (InvoiceRequest) sadrži sažete podatke o računu: OIB-ove, ukupan iznos, porezne stope i, ključno, UUID samog e-Računa.
Mehanizam Potpisivanja:
Ovo je tehnički najzahtjevniji dio. Prije slanja, morate:
Kanonikalizirati XML (C14N) kako bi se uklonile varijacije u formatiranju (razmaci, line-breaks).
Kreirati SHA-256 sažetak (digest) kanonikaliziranog dijela.
Kriptirati taj sažetak privatnim ključem vašeg Demo certifikata koristeći RSA algoritam.
Umetnuti potpis u <ds:Signature> blok.
Ako potpis nije matematički ispravan, CIS vraća grešku s001 - Signature validation failed.
4.2. AS4 Protokol za Razmjenu (e-Delivery)
AS4 (Applicability Statement 4) je protokol baziran na SOAP-u, ali s dodatnim slojevima za pouzdanost i sigurnost, specifično dizajniran za B2B razmjenu.
Ključne karakteristike za developere:
Asinkronost: Za razliku od običnog SOAP poziva gdje odgovor dobivate odmah, kod AS4 šaljete poruku i dobivate samo tehničku potvrdu (Receipt). Poslovni odgovor (npr. "Kupac je prihvatio račun") dolazi kao nova, zasebna poruka koju FINA šalje vama.
P-Mode (Processing Mode): Da bi AS4 funkcionirao, obje strane moraju imati usklađenu konfiguraciju. U testnoj okolini, morate konfigurirati svoj AS4 klijent (npr. Holodeck, Domibus, ili vlastitu implementaciju) s parametrima koje definira FINA:
Service: urn:oasis:names:specification:ubl:schema:xsd:Invoice-2
Action: DistributeInvoice
Role: Sender / Receiver
Testiranje AS4:
Budući da je implementacija punog AS4 stoga kompleksna, mnogi developeri koriste gotove biblioteke ili "Access Point" rješenja trećih strana. Ako razvijate vlastiti, fokusirajte se na testiranje MIME poruka s privitcima (SOAP with Attachments), jer se UBL XML šalje kao payload (privitak) unutar SOAP poruke, komprimiran (GZIP) i kriptiran.
5. Portal za Testiranje Sukladnosti: Administrativni Vodič
Kao odgovor na pitanje o "uputama za developere", važno je naglasiti ulogu Portala za testiranje sukladnosti. Ovo nije samo alat za debugging, već obvezna stepenica za legalizaciju vašeg softvera.
5.1. Registracija i Pristup
Pristup portalu nije otvoren. Administrator (osoba ovlaštena za e-Poreznu u tvrtki) mora se prijaviti na produkcijski sustav e-Porezna i tamo eksplicitno dodijeliti ulogu "Testera" razvojnom inženjeru. Tek tada developer dobiva pristup na URL https://pts.porezna-uprava.hr/.
5.2. Provođenje Scenarija Testiranja
Portal vodi korisnika kroz niz predefiniranih scenarija (Test Cases). Svaki scenarij ima:
Preduvjete: Stanje sustava prije testa.
Akciju: Što developer mora napraviti (npr. "Pošalji račun s iznosom 100.00 EUR i stopom 25%").
Očekivani Rezultat: Što CIS mora vratiti.
Tipični scenariji:
Happy Path: Uspješno slanje validnog računa. Provjerava se da li je sustav vratio JIR i da li je status poruke "PROCESSED".
Validacija Sheme: Slanje XML-a kojem nedostaje obavezni element (npr. OIB kupca). Očekuje se odbijanje s točnim kodom greške.
Provjera Konzistentnosti: Slanje računa gdje zbroj stavki ne odgovara ukupnom iznosu.
Poslovna Logika: Pokušaj storniranja računa koji ne postoji.
Nakon što vaš softver uspješno prođe sve obavezne scenarije, Portal generira Izvještaj o sukladnosti. Ovaj dokument je često potreban kao dokaz klijentima da je vaš ERP spreman za Fiskalizaciju 2.0.
6. Operativna Strategija i Preporuke za Implementaciju
6.1. Strategija "Slojevitog" Testiranja
Nemojte pokušavati testirati sve odjednom. Preporučuje se pristup u tri sloja:
Unit Testing (Lokalno): Testirajte generiranje XML-a unutar vašeg koda. Koristite XSD sheme za validaciju svakog generiranog dokumenta prije nego on uopće napusti vaš server.
Connectivity Testing (Sandbox): Testirajte samo uspostavu veze (SSL handshake) i slanje "Echo" poruka. Dok ovo ne radi stabilno, nema smisla slati XML-ove.
Process Testing (End-to-End): Simulirajte stvarne poslovne procese (izdavanje, storniranje, knjižna odobrenja) koristeći Portal za testiranje.
6.2. Upravljanje Podacima u Testu
Budući da se radi o sandboxu, podaci se brišu ili resetiraju periodički. Nemojte se oslanjati na to da će račun koji ste poslali danas biti tamo i za mjesec dana. Dizajnirajte testove tako da budu samodostatni (svaki test kreira svoje potrebne preduvjete).
6.3. Priprema za Produkciju
Iako je testna okolina vjerna kopija produkcije, postoje razlike u performansama. Testni sustavi su često sporiji. Prilikom prelaska na produkciju, prilagodite timeout postavke vaših HTTP klijenata. Također, ne zaboravite zamijeniti URL-ove i certifikate – trivijalna, ali najčešća greška pri "Go-Live" trenutku.
7. Zaključak
Implementacija Fiskalizacije 2.0 tehnički je izazov koji zahtijeva preciznost i disciplinu. Odgovor na korisnikovo pitanje je jasan: ne morate i ne smijete koristiti prave račune. Sustav Sandbox, uz prateće Demo certifikate, pruža sigurnu "pješčaniku" za igranje. Upute za developere nisu u jednom PDF dokumentu, već su raspršene kroz tehničke specifikacije UBL-a, definicije API sučelja i logiku Portala za sukladnost. Ovaj vodič sintetizirao je te fragmente u koherentnu cjelinu koja bi trebala poslužiti kao mapa puta za vaš razvojni tim. Uspjeh u Sandboxu do 31.12.2025. jedini je jamac mirnog sna 1.1.2026.
Dodatak: Tablica Ključnih Resursa
Kategorija
Resurs
Opis i Namjena
Certifikati
Demo Aplikacijski Certifikat
Klijentski certifikat za autentifikaciju i potpisivanje. Izdaje FINA na zahtjev.
Certifikati
FINA Demo Root CA
Korijenski certifikati koje treba instalirati u TrustStore aplikacije.
Dokumentacija
Tehnička Specifikacija Fiskalizacija eRačuna
"Biblija" za developere. Sadrži definicije polja, kodove grešaka i procesne dijagrame.
Alati
Open Source Validator (e.g. Truugo)
Korisno za brzu provjeru UBL sintakse prije slanja na CIS.
Portal
Portal za testiranje sukladnosti
Web aplikacija za provođenje službenih testnih scenarija i verifikaciju statusa.

Citirani radovi
Implementacija e-Računa u Agent Sustav.docx
Fiskalizacija 2.0 - sve informacije - Fiskalizacija 2.0, pristupljeno prosinca 13, 2025, https://fiskalizacija2.hr/
Fiskalizacija računa u krajnjoj potrošnji - Tehnička specifikacija za ..., pristupljeno prosinca 13, 2025, https://porezna-uprava.gov.hr/UserDocsImages/Fiskalizacija/Tehni%C4%8Dke%20specifikacije/Fiskalizacija%20-%20Tehnicka%20specifikacija%20za%20korisnike_v2.6.pdf
Adresar metapodatkovnih servisa (AMS) - Porezna uprava, pristupljeno prosinca 13, 2025, https://porezna.gov.hr/fiskalizacija/api/dokumenti/142
Metapodatkovni servis (MPS) - Porezna uprava, pristupljeno prosinca 13, 2025, https://porezna.gov.hr/fiskalizacija/api/dokumenti/141
Izdavanje Demo aplikacijskog certifikata za fiskalizaciju - Fina, pristupljeno prosinca 13, 2025, https://www.fina.hr/poslovni-digitalni-certifikati/poslovni-certifikati-za-fiskalizaciju/izdavanje-demo-aplikacijskog-certifikata-za-fiskalizaciju
Fiskalizacija za developere - Stranica 106 - Forum.hr, pristupljeno prosinca 13, 2025, https://www.forum.hr/showthread.php?p=110330983


Sveobuhvatna studija implementacije i licenciranja sustava AI agenata u okviru Fiskalizacije 2.0: Tehnička certifikacija, regulatorni troškovi i operativni okviri
1. Izvršni sažetak i strateški okvir integracije
U kontekstu rapidne digitalne transformacije poreznih sustava, Republika Hrvatska implementacijom projekta "Fiskalizacija 2.0" prelazi na model kontinuirane kontrole transakcija (Continuous Transaction Controls - CTC). Za razvojne inženjere i arhitekte sustava koji planiraju integrirati autonomne AI agente u ovaj ekosustav, ključno je razumjeti da se pojam "licence" u ovom kontekstu ne odnosi na komercijalnu kupnju dozvole, već na složeni proces tehničke verifikacije i administrativne registracije. Vaš upit o tome kako se dobiva licenca i koliki su troškovi dotiče samu srž regulatorne usklađenosti softvera u financijskom sektoru. Odgovor nije jednostavan cjenik, već višeslojna matrica tehničkih preduvjeta, sigurnosnih certifikata i validacijskih procedura propisanih Zakonom o fiskalizaciji.
Ova studija pruža iscrpnu analizu puta od testnog razvoja ("test development") do produkcijskog statusa. U središtu analize nalazi se transformacija AI agenta iz probabilističkog modela u deterministički izvršni sustav sposoban za generiranje pravno valjanih e-Računa u formatu UBL 2.1. Dokument detaljno razrađuje financijske implikacije, koje se primarno odnose na infrastrukturu javnog ključa (PKI) i usluge Financijske agencije (FINA), dok sam proces testiranja sukladnosti ostaje administrativno neopterećen izravnim naknadama Porezne uprave, ali zahtijeva značajne resurse u pogledu usklađivanja s tehničkim specifikacijama.
Kroz prizmu vašeg specifičnog slučaja – implementacije sustava unutar arhitekture AI agenata – izvještaj identificira ključne rizike, poput "halucinacija" jezičnih modela pri odabiru poreznih stopa ili KPD oznaka, te predlaže robusne arhitektonske obrasce koji osiguravaju da "testni development" rezultira uspješnim ishođenjem Potvrde o sukladnosti. U konačnici, "licenca" je status koji se stječe dokazivanjem da vaš softver govori istim jezikom kao i Centralni informacijski sustav (CIS) Porezne uprave – jezikom strukturiranih podataka, digitalnih potpisa i sinkrone web servis komunikacije.
2. Regulatorni pejzaž i definicija "Licence" u Fiskalizaciji 2.0
Razumijevanje pravnog okvira preduvjet je za svaku tehničku implementaciju. Fiskalizacija 2.0 nije samo nadogradnja postojećeg sustava fiskalizacije gotovinskog prometa uvedenog 2013. godine, već fundamentalna promjena paradigme koja obuhvaća cjelokupno B2B (Business-to-Business) poslovanje i uvodi obvezu izdavanja e-Računa prema normi EN 16931.1
2.1. Dekonstrukcija pojma "Licenca"
U kolokvijalnom govoru često se koristi termin "licenciranje softvera" za fiskalizaciju, no u pravnom i tehničkom smislu Porezne uprave, proces se sastoji od Potvrde o sukladnosti (Confirmation of Compliance) i Registracije proizvođača programskog rješenja. Ne postoji "licenca" koju kupujete jednokratno kao što biste kupili vozačku dozvolu ili obrtnicu. Umjesto toga, vaš sustav AI agenata mora proći kroz rigorozan proces validacije na Portalu za testiranje sukladnosti (PTS).
Uspješan prolazak kroz ovaj portal rezultira generiranjem Izvještaja o sukladnosti, koji de facto služi kao dozvola za rad u produkcijskoj okolini.1 Bez ovog dokumenta, korištenje softvera za fiskalizaciju računa smatra se prekršajem Zakona o fiskalizaciji, što povlači drakonske kazne za obveznika fiskalizacije, ali i za proizvođača softvera. Stoga je "dobivanje licence" zapravo proces dokazivanja interoperabilnosti.
2.2. Uloge u ekosustavu: Proizvođač vs. Posrednik
Za vaš projekt AI agenata ključno je odmah na početku definirati pravnu poziciju. Zakon prepoznaje dvije distinktivne uloge koje imaju različite obveze i troškove:
Uloga A: Proizvođač programskog rješenja (Software Producer)
Ovo je najvjerojatnija kategorija za vaš sustav ako razvijate rješenje koje će koristiti vaša tvrtka ili koje ćete prodavati drugim klijentima kao softver (SaaS ili on-premise).
Obveze: Osigurati ispravno generiranje XML-a, digitalno potpisivanje i komunikaciju s Poreznom upravom.
Proces: Registracija putem sustava ePorezna i testiranje na PTS-u.
Troškovi: Minimalni (certifikati). Ne zahtijeva ISO certifikaciju niti posebna rješenja Ministarstva gospodarstva.2
Uloga B: Informacijski posrednik (Information Intermediary)
Ovo je uloga za entitete koji žele biti centralna točka razmjene (hub) za tisuće drugih korisnika, pružajući usluge zaprimanja, slanja i arhiviranja e-Računa kao uslugu.
Obveze: Visoka razina odgovornosti za podatke trećih strana, upravljanje metapodatkovnim servisima (MPS).
Troškovi: Izuzetno visoki. Zakon propisuje obvezu posjedovanja certifikata informacijske sigurnosti ISO/IEC 27001, police osiguranja od odgovornosti i provođenje redovitih vanjskih revizija.4
Analiza vašeg upita ("implementirao bih ovaj sustav u svoj sustav ai agenata") sugerira da se pozicionirate kao Proizvođač programskog rješenja ili interni razvojni tim. Ovo je strateški povoljnija pozicija jer izbjegava kapitalne investicije u ISO certifikaciju (koja može koštati od 5.000 do 30.000 EUR) 5, a omogućuje vam punu funkcionalnost fiskalizacije vlastitih ili klijentskih računa. Ovaj izvještaj stoga će se fokusirati na proceduru za Proizvođača softvera.
3. Tehnička arhitektura AI Agenta za fiskalnu sukladnost
Prije nego što zatražite "licencu", vaš sustav mora biti tehnički besprijekoran. Integracija AI agenata (temeljenih na LLM-ovima poput GPT-4 ili Gemini) u strogo deterministički sustav poput poreznog nadzora nosi specifične rizike koje validacijski proces ciljano provjerava.
3.1. Izazov nedeterminizma u AI sustavima
Porezna uprava zahtijeva apsolutnu preciznost. XML datoteka e-Računa (UBL 2.1) mora biti matematički točna do u lipu. Ako vaš AI agent "halucinira" i izračuna PDV kao 25.01 umjesto 25.00 na osnovicu od 100, sustav Porezne uprave će odbiti račun s greškom validacije. Testni development koji spominjete mora adresirati ovaj problem kroz arhitekturu "sendviča" (Hybrid Architecture):
Kognitivni sloj (AI): Agent prima nestrukturirani upit (npr. "Izdaj račun tvrtki Info d.o.o. za 5 sati konzultacija"). Agent koristi svoje sposobnosti za ekstrakciju entiteta (NER - Named Entity Recognition) kako bi identificirao kupca, uslugu i količinu.
Deterministički sloj (Validacija iračun): Podaci koje je AI ekstrahirao NE SMIJU se izravno upisivati u XML. Oni moraju proći kroz logički modul (pisan u Pythonu, Go, C# ili Javi) koji:
Provjerava OIB u sudskom registru (putem API-ja).
Vrši matematički izračun poreza koristeći biblioteke za decimalnu preciznost (npr. decimal u Pythonu), a ne prepušta to LLM-u.
Mapira opis usluge na točnu KPD oznaku (Klasifikacija proizvoda po djelatnostima).1
Izvršni sloj (XML i Potpis): Generiranje konačnog XML-a i njegovo potpisivanje privatnim ključem mora se odvijati u strogo kontroliranom kodu, ne putem generativnog AI-a.
3.2. Upravljanje digitalnim identitetom (PKI)
Srce "licence" je zapravo digitalni certifikat. Vaš AI agent mora imati pristup privatnom ključu kako bi potpisao svaki zahtjev prema Poreznoj upravi. Ovdje dolazimo do prvih konkretnih troškova i procedura. Sustav se oslanja na infrastrukturu javnog ključa (PKI) koju u Hrvatskoj operativno vodi FINA.
Vaš sustav mora podržavati:
X.509 v3 certifikate: Standardni format digitalnih certifikata.
XAdES-BES potpis: XML Advanced Electronic Signature format koji se koristi za potpisivanje omotnice računa.1
TLS 1.2/1.3: Sigurni transportni kanal s obostranom autentifikacijom (Mutual TLS), gdje se i klijent (vaš agent) i server (Porezna uprava) međusobno identificiraju certifikatima.
4. Prva faza: Razvoj i testiranje u "Sandbox" okolini
Kao odgovor na vaš upit "ako mi ovaj testni development bude dobar", važno je definirati što točno znači "dobar" testni razvoj u očima regulatora. To znači uspješnu integraciju s testnom okolinom Porezne uprave.
4.1. Pristup Testnoj okolini (Sandbox)
Porezna uprava osigurava testno okruženje koje je vjerna kopija produkcijskog sustava, ali je fizički i logički odvojeno. Podaci poslani ovdje nemaju pravnu težinu i ne stvaraju poreznu obvezu.
URL Testnog servisa: https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest.1
Trošak pristupa: Korištenje samog testnog servera je besplatno. Porezna uprava ne naplaćuje API pozive u testnoj fazi.
4.2. Dobivanje testnih vjerodajnica (Demo certifikati)
Da bi se vaš AI agent mogao spojiti na testni server, mora se identificirati. Za to se NE KORISTE pravi poslovni certifikati, već posebni Demo certifikati.
Postupak: Morate podnijeti zahtjev FINA-i za izdavanje "Demo aplikacijskog certifikata". Obrazac se preuzima s web stranica FINA-e, a zahtjev se šalje e-mailom na certifikati-fiskalizacija@fina.hr.
Cijena: Izdavanje Demo certifikata je besplatno.6 FINA ovo nudi kao poticaj razvoju softverske zajednice.
Tehnička implementacija: Nakon odobrenja, dobit ćete referentni broj i autorizacijski kod s kojima preuzimate certifikat (obično u .p12 ili .pfx formatu) putem CMS portala demo-mojcert.fina.hr. Taj certifikat morate ugraditi u KeyStore vašeg AI agenta. Također, nužno je u TrustStore agenta instalirati FINA Demo Root CA certifikate kako bi vaš softver vjerovao testnom serveru.1
Ključni uvid: Iako je certifikat besplatan, trošak u ovoj fazi je vaše vrijeme i radni sati inženjera potrebnih za konfiguraciju SSL/TLS rukovanja (handshake), što je često najkompleksniji dio integracije zbog strogih sigurnosnih protokola.
5. Druga faza: Proces "licenciranja" (Verifikacija sukladnosti)
Nakon što vaš AI agent uspješno razmjenjuje podatke s testnim serverom, slijedi formalni proces "dobivanja licence". Kao što je ranije spomenuto, ovo se formalno naziva Testiranje sukladnosti.
5.1. Portal za testiranje sukladnosti (PTS)
Središnji alat za ovaj proces je Portal za testiranje sukladnosti (https://pts.porezna-uprava.hr/). Ovo je web aplikacija Porezne uprave koja vodi developere kroz strukturirani proces validacije.
Pristup portalu: Da biste pristupili PTS-u, morate biti registrirani korisnik sustava ePorezna. Administrator vaše tvrtke (obično direktor ili knjigovođa) mora se prijaviti u produkcijsku ePoreznu i dodijeliti vašem OIB-u (ili OIB-u developera) ulogu "Testera".8
Trošak pristupa: Korištenje portala PTS je besplatno.10 Nema administrativnih pristojbi za pokretanje testnih scenarija.
5.2. Scenariji testiranja
Na portalu vas čeka niz definiranih testnih slučajeva (Test Cases) koje vaš softver mora proći. AI agent mora biti sposoban autonomno izvršiti te zadatke na vašu komandu. Primjeri scenarija uključuju:
Happy Path: Uspješno slanje validnog e-Računa i zaprimanje JIR-a (Jedinstveni identifikator računa).
Validacija sheme: Slanje XML-a s namjernom greškom (npr. neispravan OIB) i ispravno procesiranje poruke o grešci koju vraća server.
Poslovna logika: Pokušaj storniranja računa koji ne postoji ili slanje računa s datumom u budućnosti.
Prekid komunikacije: Simulacija nedostupnosti servera i provjera mehanizma ponovnog slanja (Retry logic) koji zakon propisuje (obveza naknadne fiskalizacije u roku od 48 sati).1
5.3. Izdavanje Potvrde o sukladnosti
Kada vaš AI agent uspješno prođe sve obvezne scenarije ("zelene kvačice" na portalu), sustav automatski generira dokument: Zapisnik o provedenom testiranju ili Izvještaj o sukladnosti.
Značenje: Ovaj dokument je vaš "dokaz kvalitete". On potvrđuje da verzija softvera (npr. "AI-Agent-Fiscal v1.0") zadovoljava sve tehničke i zakonske uvjete Fiskalizacije 2.0.
Upotreba: Ovaj dokument čuvate kao dokaz u slučaju inspekcijskog nadzora. Također, prilikom registracije softvera u produkciji, sustav će provjeriti postoji li zapis o uspješnom testiranju za navedeni OIB proizvođača.
6. Treća faza: Prelazak u produkciju i Troškovnik
Ako je "testni development dobar" i prošli ste validaciju na PTS-u, spremni ste za stvarni rad. Ovdje nastaju stvarni financijski troškovi jer prelazite s besplatnih demo resursa na komercijalne produkcijske servise.
6.1. Nabava produkcijskog aplikacijskog certifikata
Demo certifikat ne vrijedi u produkciji. Morate kupiti pravi Produkcijski aplikacijski certifikat od FINA-e. Ovo je de facto cijena vaše "ulaznice" u sustav.
Tablica 1: Pregled troškova FINA certifikata potrebnih za produkciju 11
Vrsta troška
Opis usluge
Iznos (bez PDV-a)
Učestalost
Napomena
Izdavanje certifikata
Produkcijski aplikacijski certifikat za fiskalizaciju
39,82 €
Svakih 5 godina
Osnovni trošak "licence" za rad sustava.
Registracija u PKI
Prva registracija poslovnog subjekta u PKI sustav
10,62 €
Jednokratno
Plaća se samo ako tvrtka prvi put koristi FINA certifikate.
Obnova certifikata
Produženje valjanosti nakon 5 godina
39,82 €
Svakih 5 godina


Oporavak certifikata
Izdavanje novog u slučaju gubitka/zaboravljene lozinke
2,52 €
Po potrebi
Moguće samo u prvoj godini valjanosti.

Ukupni inicijalni trošak: Ako već imate registriranu tvrtku u FINA-i, trošak je cca 50 € (s PDV-om) svakih 5 godina. Ovo je izuzetno nizak trošak u usporedbi s potencijalnom vrijednošću sustava.
6.2. Registracija programskog rješenja
Prije izdavanja prvog pravog računa, morate "prijaviti" svoj softver Poreznoj upravi.
Postupak: Kroz aplikaciju ePorezna, pod sekcijom "Fiskalizacija", ispunjavate obrazac za prijavu programskog rješenja.
Podaci: Unosite naziv softvera (npr. "My AI Agent System"), verziju i datum testiranja sukladnosti.
Trošak: Ovaj administrativni korak je besplatan.12
6.3. Operativni troškovi produkcije
Osim certifikata, postoje i tekući troškovi ovisno o arhitekturi vašeg sustava:
Vremenski žig (Time Stamping): Iako nije striktno obvezan za samu fiskalizaciju (jer CIS vraća vrijeme obrade), za dugotrajnu pohranu e-Računa (Arhiviranje) preporučuje se korištenje kvalificiranih vremenskih žigova kako bi se osigurao integritet arhive kroz 11 godina zakonskog čuvanja. Cijena paketa žigova varira, ali se kreće od nekoliko centi po žigu.
Poslužiteljski certifikat (SSL): Ako vaš AI agent komunicira s drugim servisima ili ako nudite web sučelje klijentima, trebat će vam i SSL certifikat za vašu domenu (može biti besplatan via Let's Encrypt ili plaćeni OV/EV certifikat).
7. Produbljena analiza: Specifičnosti implementacije u AI okruženju
Vaš plan implementacije "u sustav AI agenata" otvara specifična pitanja koja standardna dokumentacija ne pokriva eksplicitno. Ovdje sintetiziramo ključne uvide za AI arhitekte.
7.1. Upravljanje kontekstom i sesijama
AI agenti često rade u sesijama koje mogu isteći ili izgubiti kontekst. Fiskalizacija je transakcijska.
Preporuka: Implementirajte "State Machine" unutar agenta. Stanja bi trebala biti: Draft -> Validating -> Signing -> Sending -> Fiscalized. Agent ne smije prijeći u stanje Fiscalized samo na temelju predviđanja ("mislim da je prošlo"), već isključivo nakon parsiranja sinkronog XML odgovora od Porezne uprave koji sadrži JIR.
7.2. "Human-in-the-Loop" za kritične odluke
Najveći rizik automatizacije putem AI-a je pogrešna klasifikacija porezne stope (npr. AI zaključi da je "mlijeko s okusom čokolade" osnovna namirnica s 5% PDV-a, a zapravo je 25%).
Sigurnosni mehanizam: Sustav mora imati prag pouzdanosti (confidence threshold). Ako agent odabere KPD oznaku s pouzdanošću manjom od 99%, sustav mora pauzirati i zatražiti potvrdu čovjeka prije slanja na fiskalizaciju. Kazne za neispravan porezni obračun su drastične, a odgovornost je na korisniku, ne na AI modelu.
7.3. GDPR i zaštita podataka u promptovima
Pazite što šaljete LLM-u. OIB-ovi, imena i adrese klijenata su osobni podaci.
Privacy-by-Design: Nikada ne šaljite stvarne OIB-ove u cloud LLM (poput OpenAI API-ja) ako nemate potpisan DPA (Data Processing Agreement). Umjesto toga, u promptu koristite placeholdere (npr. {{CLIENT_NAME}}), a stvarne podatke umetnite tek u determinističkom sloju prilikom generiranja XML-a. Ovo je ključno za usklađenost s GDPR-om, što je također uvjet poslovanja, iako nije dio same fiskalne "licence".
8. Zaključak i hodogram aktivnosti
Odgovor na vaše pitanje "kako dobijem licencu i košta li to nešto" može se sažeti u sljedeću stratešku mapu puta. Vaš "testni development" nije samo proba, već temelj za formalnu certifikaciju.
8.1. Sažetak troškova
Implementacija vlastitog sustava (status Proizvođača softvera) financijski je vrlo povoljna.
Administrativne pristojbe: 0 €
Testiranje (Sandbox & PTS): 0 €
Infrastruktura (Certifikati): cca 50 € svakih 5 godina.
Skriveni troškovi: Razvojno vrijeme (visoko) i održavanje usklađenosti s promjenama tehničkih specifikacija (srednje).
8.2. Hodogram za implementaciju (Action Plan)
Administrativna priprema (Odmah):
Registrirajte se na FINA portal i zatražite besplatni Demo certifikat.
Prijavite se na ePoreznu i dodijelite si ulogu "Testera".
Tehnička implementacija (1-2 mjeseca):
Razvijte modul za potpisivanje XML-a (XAdES) koji je odvojen od AI logike.
Trenirajte/programirajte agenta da strukturira podatke prema UBL 2.1 (HR-FISK) shemi.
Implementirajte SOAP klijent za komunikaciju s cistest serverom.
Certifikacija (1 tjedan):
Pristupite Portalu za testiranje sukladnosti (pts.porezna-uprava.hr).
Prođite sve obvezne scenarije.
Preuzmite Izvještaj o sukladnosti. Ovo je vaša "licenca".
Produkcija (Go-Live):
Kupite Produkcijski certifikat od FINA-e (cca 50 €).
Prijavite softver u ePoreznu (besplatno).
Promijenite URL u konfiguraciji agenta na produkcijski CIS servisa.
Vaš plan implementacije AI agenata u fiskalizaciju je tehnički izvediv i regulatorno podržan, pod uvjetom da se AI koristi kao pomoćni alat za pripremu podataka, a ne kao izvršni autoritet za kriptografiju i usklađenost. Slijedeći ovaj protokol, troškovi su minimalni, a pravna sigurnost maksimalna.
Tablica 2: Usporedba razvojnih puteva - Vlastiti razvoj vs. Korištenje posrednika
Karakteristika
Opcija A: Vlastiti razvoj (Vaš plan)
Opcija B: Korištenje API-ja posrednika
Primarna uloga
Proizvođač softvera
Korisnik posrednika
Trošak inicijalni
~50 € (Certifikat)
0 - 500 € (Setup fee)
Trošak po računu
~0 € (Samo hosting)
0.05 € - 0.30 € po računu
Kontrola podataka
Potpuna (Local/Private Cloud)
Podaci idu trećoj strani
Složenost razvoja
Visoka (XML, Potpis, SOAP)
Niska (REST API, JSON)
Licenciranje
Potrebno testiranje na PTS-u
Nije potrebno (koristi se licenca posrednika)
Preporuka
Da, za skalabilne AI sustave
Da, za jednostavne MVP projekte

Ova tablica jasno pokazuje da, iako vlastiti razvoj zahtijeva veći početni angažman oko "licenciranja" (testiranja sukladnosti), dugoročno nudi drastično niže operativne troškove i veću kontrolu, što je idealno za napredne sustave AI agenata koji generiraju velik volumen transakcija.
9. Dodatak: UBL 2.1 i specifičnosti HR-FISK 2.0 formata
Za uspjeh vašeg "testnog developmenta", ključno je da AI agent generira sintaktički ispravan XML. Fiskalizacija 2.0 ne koristi bilo kakav XML, već strogo propisani UBL 2.1 standard s hrvatskim proširenjima (HR-FISK 2.0).
9.1. Anatomija fiskalnog e-Računa
Vaš AI agent mora mapirati nestrukturirane podatke u sljedeću strukturu. Ovo su polja gdje agenti najčešće griješe:
cbc:CustomizationID: Ovo polje mora sadržavati točan identifikator specifikacije, npr. urn:cen.eu:en16931:2017#compliant#urn:mfin.hr:ciusext:hr-fisk:2.0. Ako agent "izmisli" ili skrati ovaj string, račun se automatski odbija.
cac:TaxTotal: Zbroj poreza. Ovdje se ne smije koristiti AI inferencija ("izračunaj otprilike"). Iznos mora biti egzaktan zbroj svih TaxSubtotal elemenata. Preporučuje se da AI agent samo identificira osnovicu i stopu, a deterministički algoritam izračuna iznos.
cac:InvoiceLine: Svaka stavka računa. AI je ovdje najkorisniji za klasifikaciju. Na primjer, ako korisnik kaže "prodaj 5 kruhova", AI mora znati da je to unitCode="H87" (komad) i, što je kritično za Fiskalizaciju 2.0, mora pridružiti ispravnu KPD oznaku (npr. 10.71.11 za svježi kruh).1
9.2. Rukovanje greškama (Error Handling)
Testiranje sukladnosti posebno provjerava kako vaš softver reagira na greške. AI agent mora biti programiran da razumije SOAP Fault poruke.
Primjer: Ako Porezna uprava vrati grešku S005 - OIB nije u sustavu PDV-a, agent ne smije samo ispisati "Greška", već mora interpretirati taj kod i obavijestiti korisnika: "Nije moguće fiskalizirati račun jer kupac s navedenim OIB-om nije obveznik PDV-a. Provjerite podatke." Ova semantička interpretacija grešaka je područje gdje AI dodaje veliku vrijednost korisničkom iskustvu.
9.3. QR Kod i JIR
Nakon uspješne fiskalizacije, sustav vraća JIR. Vaš agent mora biti sposoban generirati QR kod koji sadrži URL za provjeru računa i ugraditi ga u PDF vizualizaciju računa (ukoliko se račun šalje i u PDF formatu, npr. na email). Generiranje QR koda mora slijediti tehničke specifikacije o sadržaju i formatu (veličina, razina korekcije greške) koje su definirane u tehničkoj dokumentaciji.13
Zaključno, "licenca" za vaš sustav AI agenata nije birokratski pečat, već potvrda tehničke izvrsnosti. Uz minimalne financijske troškove za certifikate, glavni ulog je vaše inženjersko vrijeme uloženo u izgradnju mosta između fleksibilne inteligencije AI-a i rigidnih pravila poreznog nadzora.
Citirani radovi
Implementacija e-Računa u Agent Sustav.docx
Naplata upravnih pristojbi po izdanim poreznim potvrdama - RRiF, pristupljeno prosinca 13, 2025, https://www.rrif.hr/naplata_upravnih_pristojbi_po_izdanim_poreznim_pot-2023-misljenje/
Pitanja i odgovori vezani uz Zakon o fiskalizaciji - Porezna uprava, pristupljeno prosinca 13, 2025, https://porezna-uprava.gov.hr/UserDocsImages/Fiskalizacija/Fiskalizacija_eRacun/Pitanja%20i%20odgovori%20vezani%20uz%20Zakon%20o%20fiskalizaciji.pdf
ISO 27001 Certification Costs: What's Realistic? - PCG, pristupljeno prosinca 13, 2025, https://pcg.io/insights/iso-27001-certification-costs-whats-realistic/
Koliko Košta Implementacija ISO 27001 Sustava? | Vodič 2025, pristupljeno prosinca 13, 2025, https://zadar-ict.hr/koliko-kosta-implementacija-iso-27001/
Odgovori na vaša najčešća pitanja - Fina, pristupljeno prosinca 13, 2025, https://www.fina.hr/finadigicert/certifikati-za-testiranje-i-demonstraciju/odgovori-na-vasa-najcesca-pitanja
Najčešća pitanja i odgovori o fiskalizaciji - Fina, pristupljeno prosinca 13, 2025, https://www.fina.hr/poslovni-digitalni-certifikati/poslovni-certifikati-za-fiskalizaciju/najcesca-pitanja-i-odgovori-o-fiskalizaciji
Fiskalizacija 2.0. - pregled najbitnijeg, pristupljeno prosinca 13, 2025, https://onnut.dashofer.hr/onb/33/fiskalizacija-2-0-pregled-najbitnijeg-uniqueidmRRWSbk196E4DjKFq6pChAheL-SkszJ0gshCBZF6vGDSYgFMec-yMQ/?serp=1
Fiskalizacija 2.0. - pregled najbitnijeg - Porezi u praksi, pristupljeno prosinca 13, 2025, https://porezi.dashofer.hr/33/fiskalizacija-2-0-pregled-najbitnijeg-uniqueidmRRWSbk196E4DjKFq6pChAheL-SkszJ0AgfdjeayhtDSYgFMec-yMQ/
Pregled mogućnosti postojećeg i budućeg testnog okruženja za ..., pristupljeno prosinca 13, 2025, https://porezna-uprava.gov.hr/UserDocsImages/Fiskalizacija/Letci/Testiranje_opis_Fiskalizacija2.0.pdf?vel=170256
Cijene digitalnih certifikata za fiskalizaciju - Fina, pristupljeno prosinca 13, 2025, https://www.fina.hr/poslovni-digitalni-certifikati/poslovni-certifikati-za-fiskalizaciju/cijene-digitalnih-certifikata-za-fiskalizaciju
Često postavljana pitanja (faq) - Porezna uprava, pristupljeno prosinca 13, 2025, https://porezna-uprava.gov.hr/HR_Fiskalizacija/Stranice/%C4%8Cesto-postavljana-pitanja_novo.aspx
Fiskalizacija računa u krajnjoj potrošnji - Tehnička specifikacija za ..., pristupljeno prosinca 13, 2025, https://porezna-uprava.gov.hr/UserDocsImages/Fiskalizacija/Tehni%C4%8Dke%20specifikacije/Fiskalizacija%20-%20Tehnicka%20specifikacija%20za%20korisnike_v2.6.pdf
