"""
Deployment Configuration
========================
Controls feature availability based on deployment profile.

Profiles:
  - "full"     : All features including ERP (dev machine, production)
  - "rpi-home" : Smart home deployment (no ERP/fiskalizacija)

Environment variables:
  DEPLOYMENT_PROFILE  - "full" (default) or "rpi-home"
  ENABLE_WAKE_WORD    - "true" to enable wake word listener
"""

import os

DEPLOYMENT_PROFILE = os.getenv("DEPLOYMENT_PROFILE", "full")

# Feature flags
ENABLE_ERP = DEPLOYMENT_PROFILE == "full"
ENABLE_WAKE_WORD = os.getenv("ENABLE_WAKE_WORD", "false").lower() == "true"

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
