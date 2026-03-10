#!/usr/bin/env python3
"""
Test Available Gemini Models
Testira koje modele možeš koristiti s tvojim GOOGLE_API_KEY
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()


async def test_model(model_name: str) -> bool:
    """Testira jedan Gemini model"""
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv('GOOGLE_API_KEY')
        client = genai.Client(api_key=api_key)

        logger.info(f"📞 Testiram: {model_name}...")

        response = client.models.generate_content(
            model=model_name,
            contents="Reci samo 'OK' na hrvatskom.",
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=10
            )
        )

        result = response.text if hasattr(response, 'text') else str(response)
        logger.info(f"✅ {model_name}: RADI - Odgovor: {result.strip()}")
        return True

    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "invalid" in error_msg.lower():
            logger.warning(f"⚠️  {model_name}: NIJE DOSTUPAN")
        else:
            logger.error(f"❌ {model_name}: ERROR - {error_msg}")
        return False


async def list_all_models():
    """Lista sve dostupne modele preko API-ja"""
    try:
        from google import genai

        api_key = os.getenv('GOOGLE_API_KEY')
        client = genai.Client(api_key=api_key)

        logger.info("\n📋 Dohvaćam listu svih dostupnih modela...")

        models = client.models.list()

        logger.info("\n✅ DOSTUPNI MODELI:")
        logger.info("="*70)

        gemini_models = []
        for model in models:
            model_name = model.name if hasattr(model, 'name') else str(model)
            if 'gemini' in model_name.lower():
                gemini_models.append(model_name)
                logger.info(f"  • {model_name}")

        if not gemini_models:
            logger.warning("Nema Gemini modela u listi")

        return gemini_models

    except Exception as e:
        logger.error(f"❌ Ne mogu dohvatiti listu modela: {e}")
        return []


async def main():
    """Main entry point"""
    logger.info("\n" + "#"*70)
    logger.info("# TEST DOSTUPNIH GEMINI MODELA")
    logger.info("#"*70)

    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        logger.error("❌ GOOGLE_API_KEY nije postavljen u .env")
        return False

    logger.info(f"✓ API Key pronađen: {api_key[:10]}...")

    # Lista modela za testiranje
    models_to_test = [
        # Gemini 1.5 (trenutni)
        "gemini-1.5-flash",
        "gemini-1.5-flash-002",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-002",
        "gemini-1.5-pro-latest",

        # Gemini 2.0 (ako je dostupan)
        "gemini-2.0-flash",
        "gemini-2.0-flash-exp",

        # Gemini 1.0 (legacy)
        "gemini-1.0-pro",
        "gemini-pro",
    ]

    logger.info("\n" + "="*70)
    logger.info("TEST 1: Testiranje poznatih Gemini modela")
    logger.info("="*70)

    working_models = []
    for model in models_to_test:
        if await test_model(model):
            working_models.append(model)
        await asyncio.sleep(0.5)  # Rate limiting

    # Dohvati sve dostupne modele
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Dohvaćanje svih dostupnih modela")
    logger.info("="*70)

    all_models = await list_all_models()

    # Sažetak
    logger.info("\n" + "="*70)
    logger.info("📊 SAŽETAK")
    logger.info("="*70)

    logger.info(f"\n✅ Modeli koji RADE s tvojim API keyem ({len(working_models)}):")
    for model in working_models:
        logger.info(f"  • {model}")

    if working_models:
        logger.info("\n📋 PREPORUKA za tvoj sustav:")

        # Pronađi beste modele
        flash_models = [m for m in working_models if 'flash' in m]
        pro_models = [m for m in working_models if 'pro' in m and 'flash' not in m]

        if flash_models:
            best_flash = flash_models[0]  # Prvi koji radi
            logger.info(f"  FLASH model: {best_flash}")
            logger.info(f"  └─ Koristi za: orchestrator, librarian, analyst, secretary, rolodex, tracker")

        if pro_models:
            best_pro = pro_models[0]  # Prvi koji radi
            logger.info(f"  PRO model: {best_pro}")
            logger.info(f"  └─ Koristi za: mailer, scribe, researcher, scraper")

        # Predloži .env konfiguraciju
        logger.info("\n📝 Dodaj u .env file:")
        if flash_models:
            logger.info(f"  GEMINI_MODEL_FLASH={flash_models[0]}")
        if pro_models:
            logger.info(f"  GEMINI_MODEL_PRO={pro_models[0]}")

        return True
    else:
        logger.error("\n❌ Nijedan model ne radi!")
        logger.error("Provjeri:")
        logger.error("  1. Je li API key validan")
        logger.error("  2. Ima li API key pristup Gemini modelima")
        logger.error("  3. Internet konekcija")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
