"""Reproduce the mailer worker agent in isolation with a read-only request to
see whether it returns text (vs the empty result seen via the orchestrator)."""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

from agents.adk_agents.mailer_adk import create_mailer_agent
from agents.adk_agents.runner_utils import run_agent_simple


async def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "Koje Gmail labele imam? Nabroji ih ukratko."
    agent = create_mailer_agent()
    resp = await run_agent_simple(
        agent, msg, session_id="diag-mailer", user_id="diag-user", app_name="agents"
    )
    print("RESP_LEN:", len(resp or ""))
    print("RESP:", repr((resp or "")[:400]))


asyncio.run(main())
