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

# Jarvis answers simple questions in a few seconds, but a request that makes the
# orchestrator call tools (calendar, mail, sensor history) can legitimately take
# half a minute. Cutting that short would look like a broken agent.
DEFAULT_TIMEOUT = 90
