"""
ADK Tools Package

Native Google ADK tool implementations using FunctionTool primitives.
These tools wrap existing API implementations in ADK-compliant format.
"""

# Factory functions for older agent initialization (deprecated)
# from .research_adk_tools import get_research_adk_tools, get_research_capabilities
# from .docs_adk_tools import get_docs_adk_tools
# from .calendar_adk_tools import get_calendar_adk_tools
# from .sheets_adk_tools import get_sheets_adk_tools, get_sheets_capabilities
# from .drive_adk_tools import get_drive_adk_tools, get_drive_capabilities

# Direct function imports (modern pattern - used in tests and workflows)
from . import gmail_adk_tools
from . import research_adk_tools
from . import docs_adk_tools
from . import calendar_adk_tools
from . import sheets_adk_tools
from . import drive_adk_tools
from . import contacts_adk_tools

# Fiskalizacija 2.0 tools
from . import fiskalizacija_adk_tools

__all__ = [
    'gmail_adk_tools',
    'research_adk_tools',
    'docs_adk_tools',
    'calendar_adk_tools',
    'sheets_adk_tools',
    'drive_adk_tools',
    'contacts_adk_tools',
    # Fiskalizacija 2.0
    'fiskalizacija_adk_tools',
]
