"""
Batch Test Runner for Google Workspace ADK Multi-Agent System
Runs all 25 test cases sequentially and logs results
"""

import os
import sys
import asyncio
import logging
import time

# Setup logging to file and console
log_filename = f"test_results_{int(time.time())}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from main import WorkspaceADKSystem, sanitize_emojis

# All 25 test cases
TEST_CASES = [
    # RAZINA 1: Pojedinacni agenti (14 testova)
    {
        "id": 1,
        "agents": "researcher",
        "query": 'Istraži mi koje su glavne prednosti i mane korištenja AI agenata u poslovanju u 2026. godini. Daj mi sažetak u 5 točaka.'
    },
    {
        "id": 2,
        "agents": "analyst",
        "query": 'Otvori tablicu "Sales Q4 2025.xlsx" na Google Driveu i analiziraj podatke - koliki je ukupni revenue, koliko je narudžbi completed vs pending vs cancelled, i koji kupac ima najveći revenue?'
    },
    {
        "id": 3,
        "agents": "analyst",
        "query": 'Otvori tablicu "Test Data 2026.xlsx" na Driveu, sheet "Expenses" i reci mi koliki je ukupni iznos troškova po kategoriji.'
    },
    {
        "id": 4,
        "agents": "mailer",
        "query": 'Pošalji email na tgolic555@gmail.com s naslovom "Test sustava - datum" i u tijelu napiši "Ovo je automatski test email iz AI sustava. Sustav radi ispravno."'
    },
    {
        "id": 5,
        "agents": "rolodex",
        "query": 'Pronađi kontakt Tomislav Golić u mojim Google kontaktima i prikaži mi sve podatke o njemu.'
    },
    {
        "id": 6,
        "agents": "librarian",
        "query": 'Pronađi sve xlsx datoteke na mom Google Driveu i izlistaj ih s nazivima i lokacijama.'
    },
    {
        "id": 7,
        "agents": "scribe",
        "query": 'Kreiraj Google Docs dokument s naslovom "Zapisnik testiranja sustava" i sadržajem: "Datum: danas. Sustav je uspješno testiran. Svi agenti rade ispravno. Potpis: AI asistent." Podijeli dokument javno.'
    },
    {
        "id": 8,
        "agents": "secretary",
        "query": 'Kreiraj događaj u kalendaru za sutra u 10:00 s naslovom "Testni sastanak AI sustava" koji traje 30 minuta.'
    },
    {
        "id": 9,
        "agents": "tracker",
        "query": 'Kreiraj novi task s naslovom "Testirati sve agente" s rokom do kraja tjedna i bilješkom "Provjeriti rad svih 14 agenata u sustavu".'
    },
    {
        "id": 10,
        "agents": "scraper",
        "query": 'Scrapeaj stranicu https://www.hgk.hr i izvuci mi glavne naslove i linkove s naslovnice.'
    },
    {
        "id": 11,
        "agents": "synthesizer",
        "query": 'Prepiši ovaj tekst profesionalno u stil executive summary: "AI agenti su cool. Koristimo Gemini modele. Imamo 14 agenata. Sustav radi na Google ADK-u. Fiskalizacija isto radi. Sve je super."'
    },
    {
        "id": 12,
        "agents": "marketing",
        "query": 'Osmisli kratku marketinšku kampanju za fiktivni proizvod "SmartDesk Pro" - pametni radni stol za ured. Trebam headline, opis i 3 ključne prodajne točke.'
    },
    {
        "id": 13,
        "agents": "socrates",
        "query": 'Što je pravednost i može li zakon biti nepravedan?'
    },
    {
        "id": 14,
        "agents": "fiskalizacija",
        "query": 'Fiskaliziraj račun za kupca OIB 12345678903, za uslugu "IT konzalting" u iznosu od 1000 EUR + PDV 25%.'
    },
    # RAZINA 2: Multi-agent workflowi (7 testova)
    {
        "id": 15,
        "agents": "researcher -> scribe -> mailer",
        "query": 'Istraži temu "budućnost remote rada u Hrvatskoj 2026", napravi Google Docs dokument s rezultatima istraživanja i pošalji link na tgolic555@gmail.com.'
    },
    {
        "id": 16,
        "agents": "rolodex -> mailer",
        "query": 'Pronađi email adresu kontakta Tomislav Golić iz mojih kontakata i pošalji mu email s naslovom "Poziv na sastanak" i porukom "Pozivam te na kratki sastanak sutra u 10h. Javi se!"'
    },
    {
        "id": 17,
        "agents": "analyst -> scribe",
        "query": 'Analiziraj tablicu "Customers.xlsx" na Driveu i kreiraj Google Docs izvještaj s popisom svih kupaca i njihovih email adresa u formatiranoj tablici.'
    },
    {
        "id": 18,
        "agents": "researcher -> synthesizer",
        "query": 'Istraži temu "prednosti i rizici generativne AI u obrazovanju" i zatim prepiši rezultate u profesionalni izvještaj prilagođen za direktora škole.'
    },
    {
        "id": 19,
        "agents": "librarian -> analyst",
        "query": 'Pronađi datoteku "Sales Q4 2025.xlsx" na Driveu i analiziraj koji su orderi sa statusom "Completed" i koliki je njihov ukupni revenue.'
    },
    {
        "id": 20,
        "agents": "secretary -> mailer",
        "query": 'Zakaži sastanak za petak u 14:00 s naslovom "Kvartalni pregled" na 1 sat i pošalji obavijest o sastanku na tgolic555@gmail.com.'
    },
    {
        "id": 21,
        "agents": "scraper -> scribe",
        "query": 'Scrapeaj stranicu https://www.index.hr , izvuci glavne vijesti i kreiraj Google Docs dokument "Pregled vijesti" s tim sadržajem. Podijeli javno.'
    },
    # RAZINA 3: Kompleksni workflowi (4 testa)
    {
        "id": 22,
        "agents": "researcher -> synthesizer -> scribe -> librarian -> mailer",
        "query": 'Istraži "AI trendovi u financijskom sektoru 2026", prepiši u profesionalni izvještaj, kreiraj Google Docs dokument, spremi ga u folder "Istraživanja" na Driveu i pošalji link dokumenta na tgolic555@gmail.com.'
    },
    {
        "id": 23,
        "agents": "analyst -> scribe -> mailer",
        "query": 'Analiziraj tablicu "Test Data 2026.xlsx" sheet "Sales Data" na Driveu - izračunaj ukupnu prodaju po proizvodu, napravi Google Docs izvještaj "Izvještaj o prodaji Q1 2026" s tim podacima i pošalji ga na tgolic555@gmail.com.'
    },
    {
        "id": 24,
        "agents": "rolodex -> secretary -> mailer",
        "query": 'Pronađi kontakt Tomislav Golić, zakaži sastanak s njim za ponedjeljak u 11:00 pod naslovom "Projektni sync" na 45 minuta i pošalji mu email potvrdu o zakazanom sastanku.'
    },
    {
        "id": 25,
        "agents": "researcher -> scribe -> librarian",
        "query": 'Istraži "najbolji alati za projektni management u 2026", napravi dokument "Usporedba PM alata 2026" s rezultatima i spremi ga na Drive.'
    },
]


async def run_tests(start_from: int = 1, only_ids: list = None):
    """Run test cases sequentially, optionally starting from a specific test ID or running only specific IDs"""

    if only_ids:
        tests_to_run = [t for t in TEST_CASES if t["id"] in only_ids]
    else:
        tests_to_run = [t for t in TEST_CASES if t["id"] >= start_from]

    logger.info("=" * 80)
    logger.info("BATCH TEST RUNNER - Google Workspace ADK Multi-Agent System")
    logger.info(f"Tests to run: {len(tests_to_run)} (starting from TEST {start_from})")
    logger.info(f"Log file: {log_filename}")
    logger.info("=" * 80)

    # Initialize system once
    system = WorkspaceADKSystem()
    system.initialize_agents()

    if not system.verify_authentication():
        logger.warning("Authentication not configured. Some features may not work.")

    results = []

    for test in tests_to_run:
        test_id = test["id"]
        agents = test["agents"]
        query = test["query"]

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"TEST {test_id}/25 [{agents}]")
        logger.info(f"Query: {query}")
        logger.info("=" * 80)

        start_time = time.time()
        status = "UNKNOWN"
        result_text = ""
        error_msg = ""

        # Retry logic for 429 rate limit errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Route based on philosophy or orchestrator
                from interfaces.base_interface import looks_philosophical

                if looks_philosophical(query):
                    logger.info("Routing to Philosophy Classroom (Socrates)")
                    socrates_response = await system.socrates.run_with_fallback(query)
                    result_text = socrates_response
                    status = "PASS" if result_text and len(result_text) > 20 else "FAIL"
                else:
                    logger.info("Routing to Smart Orchestrator")
                    result_text = await system.orchestrator_helper.run(query)
                    # Basic success check
                    if result_text and len(result_text) > 20:
                        status = "PASS"
                    else:
                        status = "FAIL"
                break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = 60 * (attempt + 1)  # 60s, 120s, 180s
                        logger.warning(f"Test {test_id} hit 429 rate limit (attempt {attempt+1}/{max_retries}). Waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                status = "ERROR"
                logger.error(f"Test {test_id} failed with exception: {e}")
                break

        elapsed = time.time() - start_time

        # Log result
        logger.info("")
        logger.info(f"--- TEST {test_id} RESULT ---")
        logger.info(f"Status: {status}")
        logger.info(f"Time: {elapsed:.1f}s")
        if error_msg:
            logger.info(f"Error: {error_msg}")
        if result_text:
            # Truncate long results for log readability
            display_text = sanitize_emojis(result_text[:500]) if len(result_text) > 500 else sanitize_emojis(result_text)
            logger.info(f"Result preview: {display_text}")
        logger.info(f"--- END TEST {test_id} ---")

        results.append({
            "id": test_id,
            "agents": agents,
            "status": status,
            "time": elapsed,
            "error": error_msg,
            "result_length": len(result_text) if result_text else 0
        })

        # Delay between tests to avoid Vertex AI rate limiting (429)
        if status == "ERROR" and "429" in error_msg:
            logger.info("Rate limited! Waiting 60s before next test...")
            await asyncio.sleep(60)
        else:
            logger.info("Waiting 15s before next test...")
            await asyncio.sleep(15)

    # Print summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    total_time = sum(r["time"] for r in results)

    for r in results:
        marker = "[OK]" if r["status"] == "PASS" else "[FAIL]" if r["status"] == "FAIL" else "[ERROR]"
        logger.info(f"  TEST {r['id']:2d} [{r['agents']:<50s}] {marker} ({r['time']:.1f}s)")

    logger.info("")
    logger.info(f"PASSED:  {passed}/25")
    logger.info(f"FAILED:  {failed}/25")
    logger.info(f"ERRORS:  {errors}/25")
    logger.info(f"TOTAL TIME: {total_time:.1f}s ({total_time/60:.1f} min)")
    logger.info(f"Log saved to: {log_filename}")
    logger.info("=" * 80)


if __name__ == "__main__":
    # Usage: python test_batch.py [start_from] [only_ids]
    # Examples: python test_batch.py 10       (start from test 10)
    #           python test_batch.py 1 10,13,16  (run only tests 10, 13, 16)
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    only_ids = None
    if len(sys.argv) > 2:
        only_ids = [int(x) for x in sys.argv[2].split(",")]
    try:
        asyncio.run(run_tests(start_from=start, only_ids=only_ids))
    except KeyboardInterrupt:
        logger.info("\nTest run interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
