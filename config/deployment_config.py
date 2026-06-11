"""
Deployment Configuration
========================
Controls feature availability based on deployment profile.

Profiles:
  - "full"     : All features including ERP (dev machine, production)
  - "rpi-home" : Smart home + selected Google Workspace + conversational agents

Environment variables:
  DEPLOYMENT_PROFILE       - "full" (default) or "rpi-home"
  ENABLE_WAKE_WORD         - "true" to enable wake word listener
  VOICE_DIRECT_ROUTING     - direct-route wake-word requests to home / christian / socrates
  DISABLE_ADK_TELEMETRY    - disable flaky ADK tracing that can crash on bytes payloads
  ENABLE_WEB_SCHEDULER     - allow web process to start embedded APScheduler
"""

import os

DEPLOYMENT_PROFILE = os.getenv("DEPLOYMENT_PROFILE", "full")
IS_RPI_HOME = DEPLOYMENT_PROFILE == "rpi-home"

# Feature flags
ENABLE_ERP = DEPLOYMENT_PROFILE == "full"
ENABLE_WAKE_WORD = os.getenv("ENABLE_WAKE_WORD", "false").lower() == "true"
VOICE_DIRECT_ROUTING = os.getenv(
    "VOICE_DIRECT_ROUTING",
    "true" if IS_RPI_HOME else "false",
).lower() == "true"
DISABLE_ADK_TELEMETRY = os.getenv(
    "DISABLE_ADK_TELEMETRY",
    "true" if IS_RPI_HOME else "false",
).lower() == "true"
ENABLE_WEB_SCHEDULER = os.getenv(
    "ENABLE_WEB_SCHEDULER",
    "false" if IS_RPI_HOME else "true",
).lower() == "true"

# Agents that require ERP service layer (services/erp/*)
# These are excluded from agent registry on non-ERP deployments.
# Note: expense, tracker, analyst, rolodex use erp_adk_tools lazily -
# they work partially without ERP (their non-ERP tools still function).
ERP_AGENTS = {
    "fiskalizacija",
    "fiskalni_pripremac",
    "fiskalni_validator",
    "fiskalni_executor",
}

# RPi home profile should not load every non-ERP agent by default.
# Keep it focused on smart-home, Google Workspace, research, and conversational use.
RPI_HOME_ALLOWED_AGENTS = {
    "orchestrator",
    "decision_validator",
    "ask_user",
    "mailer",
    "librarian",
    "analyst",
    "secretary",
    "rolodex",
    "tracker",
    "researcher",
    "scribe",
    "scraper",
    "synthesizer",
    "voice_qa",
    "socrates",
    "christian_guide",
    "smart_home",
}
