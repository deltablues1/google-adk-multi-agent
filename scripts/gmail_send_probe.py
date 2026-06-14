"""Read-only Gmail auth check: list labels via the ADK tool. Confirms Gmail
auth + API work without sending or writing anything."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv()

from tools.adk_tools.gmail_adk_tools import gmail_list_labels


async def main():
    result = await gmail_list_labels()
    text = str(result)
    print("OK" if ("INBOX" in text or "label" in text.lower()) else "CHECK")
    print("RESULT:", text[:400])


asyncio.run(main())
