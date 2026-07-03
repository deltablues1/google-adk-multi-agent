"""
Home Assistant ADK Tools — TV i media upravljanje preko HA REST API-ja.

Jarvis ne priča s uređajima direktno: kaže Home Assistantu što treba
(media_player/remote servisi), a HA odradi komunikaciju s TCL Google TV-om
preko Android TV Remote integracije. Paljenje TV-a je posebno: TCL u dubljem
standbyju ugasi upravljačke servise, pa tv_turn_on prvo šalje Wake-on-LAN
magic packet (mrežna kartica ga čuje i u dubokom snu preko žice), zatim
ponavlja HA turn_on dok se TV ne javi.

Env (Pi .env):
  HA_URL                  npr. http://192.168.100.200:8123
  HA_TOKEN                long-lived access token
  TV_MEDIA_PLAYER_ENTITY  default media_player.tv
  TV_REMOTE_ENTITY        default remote.tv
  TV_MAC                  default d0:65:b3:07:97:bc (TCL 55P7K, žica)
  TV_WAKE_RETRIES         default 4 (pokušaji HA turn_on nakon WoL)
"""

import json
import logging
import os
import socket
import struct
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


def _ha_url() -> str:
    return os.getenv("HA_URL", "").strip().rstrip("/")


def _ha_token() -> str:
    return os.getenv("HA_TOKEN", "").strip()


def _tv_media_player() -> str:
    return os.getenv("TV_MEDIA_PLAYER_ENTITY", "media_player.tv").strip()


def _tv_remote() -> str:
    return os.getenv("TV_REMOTE_ENTITY", "remote.tv").strip()


def _tv_mac() -> str:
    return os.getenv("TV_MAC", "d0:65:b3:07:97:bc").strip()


def _ha_request(path: str, payload: Optional[dict] = None, timeout: float = 10.0):
    """Call the HA REST API; returns parsed JSON or raises RuntimeError."""
    url, token = _ha_url(), _ha_token()
    if not url or not token:
        raise RuntimeError("HA_URL/HA_TOKEN nisu postavljeni u .env")

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{url}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HA API {e.code}: {e.read().decode('utf-8')[:200]}")
    except Exception as e:
        raise RuntimeError(f"HA API nedostupan ({e})")


def _ha_service(domain: str, service: str, entity_id: str, extra: Optional[dict] = None):
    payload = {"entity_id": entity_id}
    if extra:
        payload.update(extra)
    return _ha_request(f"/api/services/{domain}/{service}", payload)


def _ha_state(entity_id: str) -> str:
    try:
        state = _ha_request(f"/api/states/{entity_id}")
        return (state or {}).get("state", "unknown")
    except RuntimeError:
        return "unknown"


def _send_wol(mac: str) -> None:
    """Broadcast a Wake-on-LAN magic packet (twice, ports 9 and 7)."""
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    for port in (9, 7):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(packet, ("255.255.255.255", port))


def ha_call_service(domain: str, service: str, entity_id: str, data_json: str = "") -> dict:
    """Pozovi proizvoljni Home Assistant servis.

    Args:
        domain: HA domena servisa (npr. "media_player", "remote", "switch").
        service: naziv servisa (npr. "turn_on", "volume_set", "play_media").
        entity_id: ciljni entitet (npr. "media_player.tv").
        data_json: opcionalni dodatni parametri kao JSON string
            (npr. '{"volume_level": 0.2}').

    Returns:
        dict sa "success" i opisom rezultata ili "error".
    """
    try:
        extra = json.loads(data_json) if data_json.strip() else None
    except json.JSONDecodeError as e:
        return {"error": f"data_json nije valjan JSON: {e}"}
    try:
        _ha_service(domain, service, entity_id, extra)
        return {"success": True, "detail": f"{domain}.{service} -> {entity_id}"}
    except RuntimeError as e:
        return {"error": str(e)}


def tv_turn_on() -> dict:
    """Upali televizor (TCL u dnevnoj sobi).

    Robusna sekvenca: Wake-on-LAN magic packet (budi mrežnu karticu i iz
    dubokog sna), zatim HA turn_on s ponavljanjem dok se TV ne javi.

    Returns:
        dict sa "success"/"error" i stanjem TV-a.
    """
    entity = _tv_media_player()
    retries = int(os.getenv("TV_WAKE_RETRIES", "4"))
    try:
        _send_wol(_tv_mac())
    except Exception as e:
        logger.warning("WoL slanje nije uspjelo: %s", e)

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            _ha_service("media_player", "turn_on", entity)
            _ha_service("remote", "turn_on", _tv_remote())
        except RuntimeError as e:
            last_err = str(e)
        time.sleep(3)
        state = _ha_state(entity)
        if state not in ("unavailable", "unknown", "off"):
            return {"success": True, "state": state, "attempts": attempt}
        try:
            _send_wol(_tv_mac())
        except Exception:
            pass

    state = _ha_state(entity)
    if state not in ("unavailable", "unknown", "off"):
        return {"success": True, "state": state, "attempts": retries}
    return {
        "error": (
            "TV se ne javlja ni nakon Wake-on-LAN i ponovljenih pokušaja"
            + (f" (zadnja HA greška: {last_err})" if last_err else "")
            + ". Ako je TV dugo u standbyju, možda je u predubokom snu."
        )
    }


def tv_turn_off() -> dict:
    """Ugasi televizor.

    Returns:
        dict sa "success"/"error".
    """
    try:
        _ha_service("media_player", "turn_off", _tv_media_player())
        return {"success": True, "detail": "TV ugašen"}
    except RuntimeError as e:
        return {"error": str(e)}


def tv_volume(action: str, level: int = 0) -> dict:
    """Upravljaj glasnoćom televizora.

    Args:
        action: "up" (pojačaj), "down" (stišaj), "set" (postavi na level),
            "mute" (bez zvuka), "unmute" (vrati zvuk).
        level: za "set" — postotak 0-100.

    Returns:
        dict sa "success"/"error".
    """
    entity = _tv_media_player()
    try:
        if action == "up":
            for _ in range(2):
                _ha_service("media_player", "volume_up", entity)
        elif action == "down":
            for _ in range(2):
                _ha_service("media_player", "volume_down", entity)
        elif action == "set":
            level = max(0, min(100, level))
            _ha_service(
                "media_player", "volume_set", entity,
                {"volume_level": round(level / 100.0, 2)},
            )
        elif action == "mute":
            _ha_service("media_player", "volume_mute", entity, {"is_volume_muted": True})
        elif action == "unmute":
            _ha_service("media_player", "volume_mute", entity, {"is_volume_muted": False})
        else:
            return {"error": f"Nepoznata akcija '{action}' (up/down/set/mute/unmute)"}
        return {"success": True, "detail": f"glasnoća: {action} {level if action == 'set' else ''}".strip()}
    except RuntimeError as e:
        return {"error": str(e)}


def tv_open_app(app: str) -> dict:
    """Otvori aplikaciju na televizoru.

    Args:
        app: naziv aplikacije — podržano: "youtube", "netflix", "hbo max",
            "disney", "spotify", ili Android deep-link/URL.

    Returns:
        dict sa "success"/"error".
    """
    deep_links = {
        "youtube": "https://www.youtube.com",
        "netflix": "https://www.netflix.com/title",
        "hbo": "https://play.hbomax.com",
        "hbo max": "https://play.hbomax.com",
        "disney": "https://www.disneyplus.com",
        "disney+": "https://www.disneyplus.com",
        "spotify": "spotify://",
    }
    target = deep_links.get(app.strip().lower(), app.strip())
    try:
        _ha_service(
            "remote", "turn_on", _tv_remote(),
            {"activity": target},
        )
        return {"success": True, "detail": f"otvaram {app}"}
    except RuntimeError as e:
        return {"error": str(e)}


def tv_play_youtube(query: str) -> dict:
    """Pokreni YouTube pretragu na televizoru (korisnik bira rezultat daljinskim).

    Args:
        query: što tražiti (npr. "Radiohead Creep").

    Returns:
        dict sa "success"/"error".
    """
    from urllib.parse import quote_plus

    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    try:
        _ha_service("remote", "turn_on", _tv_remote(), {"activity": url})
        return {"success": True, "detail": f"YouTube pretraga: {query}"}
    except RuntimeError as e:
        return {"error": str(e)}


def tv_send_key(key: str) -> dict:
    """Pošalji tipku daljinskog televizoru (navigacija).

    Args:
        key: jedna od DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT, DPAD_CENTER,
            BACK, HOME, MEDIA_PLAY_PAUSE, MEDIA_NEXT, MEDIA_PREVIOUS,
            CHANNEL_UP, CHANNEL_DOWN.

    Returns:
        dict sa "success"/"error".
    """
    allowed = {
        "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER",
        "BACK", "HOME", "MEDIA_PLAY_PAUSE", "MEDIA_NEXT", "MEDIA_PREVIOUS",
        "CHANNEL_UP", "CHANNEL_DOWN",
    }
    key = key.strip().upper()
    if key not in allowed:
        return {"error": f"Nepodržana tipka '{key}'. Podržane: {', '.join(sorted(allowed))}"}
    try:
        _ha_service("remote", "send_command", _tv_remote(), {"command": key})
        return {"success": True, "detail": f"tipka {key}"}
    except RuntimeError as e:
        return {"error": str(e)}


def tv_status() -> dict:
    """Dohvati stanje televizora (upaljen/ugašen, što se reproducira).

    Returns:
        dict sa "state" i, ako postoji, "app" i "media_title".
    """
    try:
        state = _ha_request(f"/api/states/{_tv_media_player()}")
    except RuntimeError as e:
        return {"error": str(e)}
    if not state:
        return {"error": "TV entitet nije pronađen u Home Assistantu"}
    attrs = state.get("attributes", {})
    return {
        "state": state.get("state", "unknown"),
        "app": attrs.get("app_name") or attrs.get("app_id") or "",
        "media_title": attrs.get("media_title", ""),
    }


def get_ha_adk_tools() -> list:
    """Get all Home Assistant TV/media tools as a list."""
    return [
        tv_turn_on,
        tv_turn_off,
        tv_volume,
        tv_open_app,
        tv_play_youtube,
        tv_send_key,
        tv_status,
        ha_call_service,
    ]
