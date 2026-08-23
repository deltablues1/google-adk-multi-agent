"""Config flow for the Jarvis conversation agent."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_TIMEOUT,
    CONF_TOKEN,
    CONF_URL,
    CONF_USER_ID,
    DEFAULT_TIMEOUT,
    DEFAULT_URL,
    DEFAULT_USER_ID,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default=DEFAULT_URL): str,
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_USER_ID, default=DEFAULT_USER_ID): str,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
    }
)


class InvalidAuth(Exception):
    """The API token was rejected."""


async def _async_validate(hass, data: dict[str, Any]) -> None:
    """Reach Jarvis once before saving, so a typo fails here and not at runtime."""
    session = async_get_clientsession(hass)
    url = data[CONF_URL].rstrip("/") + "/api/status"
    headers = {"Authorization": "Bearer " + data[CONF_TOKEN]}
    async with session.get(
        url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
    ) as response:
        if response.status in (401, 403):
            raise InvalidAuth
        response.raise_for_status()


class JarvisConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Ask for the Jarvis URL and token."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _async_validate(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001 - any failure means "cannot reach it"
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_URL])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Jarvis", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
