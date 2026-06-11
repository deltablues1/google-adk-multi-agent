"""Fast local voice command handlers for low-latency smart-home actions."""

from __future__ import annotations

import os
import unicodedata
from typing import Optional

from tools.adk_tools.mqtt_adk_tools import mqtt_scene_control, mqtt_switch_control


SMART_HOME_ROOM_ALIASES = {
    "svjetlo_boravak": ("boravak", "dnevni", "dnevni boravak", "dnevnom boravku"),
    "svjetlo_kuhinja": ("kuhinja", "kuhinji"),
    "svjetlo_hodnik": ("hodnik", "hodniku"),
    "svjetlo_kupaona": ("kupaona", "kupaonici", "kupatilo", "kupatilu"),
    "svjetlo_blagavaona": ("blagavaona", "blagovaona", "blagavaonici", "blagovaonici"),
    "svjetlo_ulaz": ("ulaz",),
    "svjetlo_terasa1": ("terasa", "terasi"),
    "svjetlo_vani": ("vani", "dvoriste", "dvoristu"),
    "svjetlo_soba1": ("soba 1", "soba1"),
    "svjetlo_soba2": ("soba 2", "soba2"),
}

SMART_HOME_SPOKEN_NAMES = {
    "svjetlo_boravak": "svjetlo u dnevnom boravku",
    "svjetlo_kuhinja": "svjetlo u kuhinji",
    "svjetlo_hodnik": "svjetlo u hodniku",
    "svjetlo_kupaona": "svjetlo u kupaoni",
    "svjetlo_blagavaona": "svjetlo u blagovaonici",
    "svjetlo_ulaz": "svjetlo na ulazu",
    "svjetlo_terasa1": "svjetlo na terasi",
    "svjetlo_vani": "vanjsko svjetlo",
    "svjetlo_soba1": "svjetlo u sobi 1",
    "svjetlo_soba2": "svjetlo u sobi 2",
}

SMART_HOME_SCENE_ALIASES = {
    "nocno": ("nocno", "nocno"),
    "film": ("film", "kino"),
    "dolazak": ("dolazak", "dosao sam", "dosla sam"),
    "odlazak": ("odlazak", "idem van", "izlazim"),
    "kuhanje": ("kuhanje", "kuham", "kuhaj"),
}


def normalize_voice_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def resolve_voice_smart_home_response(
    base_response: str,
    response_mode: Optional[str] = None,
) -> str:
    mode = (
        response_mode
        or os.getenv("VOICE_SMART_HOME_RESPONSE_MODE", "none")
    ).strip().lower()
    if mode == "none":
        return ""
    if mode == "ok":
        return "U redu."
    return base_response


async def execute_fast_smart_home_command(
    message: str,
    response_mode: Optional[str] = None,
) -> Optional[str]:
    """Run a deterministic smart-home command without the full orchestrator path."""
    normalized = normalize_voice_text(message)

    if "ugasi sve" in normalized or "sve ugasi" in normalized:
        result = await mqtt_scene_control("sve_ugasi")
        if result.get("status") == "ok":
            return resolve_voice_smart_home_response(
                "Ugasio sam sve sto se smije ugasiti.",
                response_mode,
            )
        return None

    for scene, aliases in SMART_HOME_SCENE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            result = await mqtt_scene_control(scene)
            if result.get("status") == "ok":
                description = str(result.get("description") or scene).strip()
                return resolve_voice_smart_home_response(
                    f"Ukljucio sam scenu {description}.",
                    response_mode,
                )
            return None

    state = None
    if any(token in normalized for token in ("upal", "upale", "ukljuc")):
        state = "ON"
    elif any(token in normalized for token in ("ugas", "iskljuc")):
        state = "OFF"

    if state is None:
        return None

    matched_devices = []
    for device_name, aliases in SMART_HOME_ROOM_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            matched_devices.append(device_name)

    if len(matched_devices) != 1:
        return None

    device_name = matched_devices[0]
    result = await mqtt_switch_control(device_name, state)
    if result.get("status") != "ok":
        return None

    spoken_name = SMART_HOME_SPOKEN_NAMES.get(device_name, device_name)
    if state == "ON":
        return resolve_voice_smart_home_response(
            f"Ukljucio sam {spoken_name}.",
            response_mode,
        )
    return resolve_voice_smart_home_response(
        f"Ugasio sam {spoken_name}.",
        response_mode,
    )
