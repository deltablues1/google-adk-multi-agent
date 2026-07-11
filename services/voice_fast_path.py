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


# The fast path is substring-based, so a question ("koji film preporucujes?"),
# a negation ("nemoj ugasiti sve") or a future/conditional request ("sutra
# ugasi sve") would otherwise fire a real device action. Any of these markers
# blocks the fast path; the request falls through to the LLM smart_home agent
# which understands the sentence. Markers are matched against the
# diacritic-stripped text with a leading space = word start ("kad" must not
# match "nikad"); a false positive only costs the latency shortcut.
_FAST_PATH_BLOCK_MARKERS = (
    # questions
    " koji", " koja", " koje", " kakav", " kakva", " kakvo", " sto ", " zasto",
    " je li ", " jel ", " jeli ", " da li ", " dal ", " preporuc", " reci mi",
    # negations
    " nemoj", " ne gasi", " ne pali", " ne ukljuc", " ne iskljuc",
    " ne upal", " ne ugas", " nista ne ",
    # future / conditional / scheduling
    " sutra", " kasnije", " navecer", " ujutro", " za sat", " za pola sata",
    " za pet ", " za deset ", " za petnaest", " za dvadeset", " u ponoc",
    " kad ", " kada ", " ako ", " cim ", " nakon ",
    " podsjeti", " zakazi", " rasporedi",
)


def classify_fast_path_intent(normalized: str) -> str:
    """Classify normalized voice text as "command" or "blocked" for the fast path.

    "blocked" does NOT mean rejected — the request continues to the LLM
    smart-home agent; only the deterministic substring shortcut is skipped.
    """
    if "?" in normalized:
        return "blocked"
    padded = f" {normalized.strip()} "
    if any(marker in padded for marker in _FAST_PATH_BLOCK_MARKERS):
        return "blocked"
    return "command"


def resolve_voice_smart_home_response(
    base_response: str,
    response_mode: Optional[str] = None,
) -> str:
    mode = (
        response_mode
        or os.getenv("VOICE_SMART_HOME_RESPONSE_MODE", "ok")
    ).strip().lower()
    if mode == "none":
        return ""
    if mode == "ok":
        return "U redu."
    return base_response


# Statuses that mean "the action worked" (confirmed = device echoed the new
# state; ok = confirmation layer disabled, publish succeeded).
_SUCCESS_STATUSES = ("confirmed", "ok")


def _scene_outcome_response(
    result: dict,
    success_text: str,
    response_mode: Optional[str],
) -> Optional[str]:
    """Spoken response for a scene result. Failures are ALWAYS spoken."""
    status = result.get("status")
    if status in _SUCCESS_STATUSES:
        return resolve_voice_smart_home_response(success_text, response_mode)
    if status == "partial":
        confirmed = result.get("confirmed", 0)
        total = result.get("total", 0)
        unconfirmed = result.get("unconfirmed_devices") or []
        detail = f" Nisu potvrdili: {', '.join(unconfirmed[:4])}." if unconfirmed else ""
        return f"{success_text} Potvrđeno {confirmed} od {total} uređaja.{detail}"
    if status in ("timeout", "unconfirmed"):
        return (
            "Poslao sam naredbe, ali nijedan uređaj nije potvrdio promjenu. "
            "Provjeri jesu li uređaji dostupni."
        )
    if status == "error":
        return "Ne mogu se spojiti na pametnu kuću. Provjeri MQTT vezu."
    return None


async def execute_fast_smart_home_command(
    message: str,
    response_mode: Optional[str] = None,
) -> Optional[str]:
    """Run a deterministic smart-home command without the full orchestrator path."""
    normalized = normalize_voice_text(message)

    # Questions, negations and deferred requests must never fire devices from
    # the substring shortcut — let the LLM agent interpret them instead.
    if classify_fast_path_intent(normalized) == "blocked":
        return None

    if "ugasi sve" in normalized or "sve ugasi" in normalized:
        result = await mqtt_scene_control("sve_ugasi")
        return _scene_outcome_response(
            result, "Ugasio sam sve sto se smije ugasiti.", response_mode
        )

    for scene, aliases in SMART_HOME_SCENE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            result = await mqtt_scene_control(scene)
            description = str(result.get("description") or scene).strip()
            return _scene_outcome_response(
                result, f"Ukljucio sam scenu {description}.", response_mode
            )

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
    status = result.get("status")
    spoken_name = SMART_HOME_SPOKEN_NAMES.get(device_name, device_name)

    if status in _SUCCESS_STATUSES:
        success_text = (
            f"Ukljucio sam {spoken_name}." if state == "ON"
            else f"Ugasio sam {spoken_name}."
        )
        return resolve_voice_smart_home_response(success_text, response_mode)
    if status in ("timeout", "unconfirmed"):
        # Failures are always spoken, regardless of response mode.
        return (
            f"Poslao sam naredbu, ali {spoken_name} nije potvrdio promjenu. "
            "Provjeri je li uređaj dostupan."
        )
    if status == "error":
        return "Ne mogu se spojiti na pametnu kuću. Provjeri MQTT vezu."
    return None
