"""
ADK Agents Package

Native Google ADK agent implementations using LlmAgent, SequentialAgent,
ParallelAgent, and LoopAgent primitives.
"""

from .mailer_adk import create_mailer_agent
from .researcher_adk import create_researcher_agent
from .scribe_adk import create_scribe_agent
from .secretary_adk import create_secretary_agent
from .analyst_adk import create_analyst_agent
from .librarian_adk import create_librarian_agent
from .rolodex_adk import create_rolodex_agent
from .tracker_adk import create_tracker_agent
from .scraper_adk import create_scraper_agent

# Fiskalizacija 2.0 agents
from .fiskalni_pripremac_adk import create_fiskalni_pripremac_agent
from .fiskalni_validator_adk import create_fiskalni_validator_agent
from .fiskalni_executor_adk import create_fiskalni_executor_agent
from .fiskalizacija_adk import create_fiskalizacija_agent

__all__ = [
    'create_mailer_agent',
    'create_researcher_agent',
    'create_scribe_agent',
    'create_secretary_agent',
    'create_analyst_agent',
    'create_librarian_agent',
    'create_rolodex_agent',
    'create_tracker_agent',
    'create_scraper_agent',
    # Fiskalizacija 2.0
    'create_fiskalni_pripremac_agent',
    'create_fiskalni_validator_agent',
    'create_fiskalni_executor_agent',
    'create_fiskalizacija_agent',  # Wrapper for complete fiscalization flow
]
