"""Constants for the Jarvis conversation integration."""

DOMAIN = "jarvis"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_USER_ID = "user_id"
CONF_TIMEOUT = "timeout"

# Jarvis runs on the second Raspberry Pi; the web API is the same one the
# dashboard uses.
DEFAULT_URL = "http://192.168.100.105:8000"
DEFAULT_USER_ID = "ha-assist"

# Simple questions come back in a few seconds, but a real task can run for
# minutes: measured 2026-08-23, "research heat pumps, write it up and mail it to
# me" took ~3 minutes across 12 tool calls and finished successfully -- while a
# 90 s timeout had already told the user it had failed. The cost of waiting too
# long is a slow answer; the cost of waiting too little is lying about a task
# that actually completed.
DEFAULT_TIMEOUT = 300
