"""Put every entity in the room it is actually in, and switch the useful
diagnostics back on.

Everything hangs off two ESPHome devices, so Home Assistant files all of it
under those devices' areas: every switch under "Kuca" and every sensor under no
area at all. That is why the Rooms view shows almost nothing per room. Areas set
on the entity itself override the device, which is what this does.
"""

import asyncio
import json
import os
import sys

import websockets

URL = os.environ["HA_URL"].replace("http://", "ws://") + "/api/websocket"
TOKEN = os.environ["HA_TOKEN"]
BACKUP = "/tmp/entity-registry-backup.json"

# suffix of the entity_id -> area_id
ROOM_BY_SUFFIX = {
    # --- BME280 mux node: climate per room ---
    "dnevni_prostor_temperatura": "living_room",
    "dnevni_prostor_vlaga": "living_room",
    "dnevni_prostor_tlak": "living_room",
    "kupaona_temperatura": "kupaona",
    "kupaona_vlaga": "kupaona",
    "kupaona_tlak": "kupaona",
    "soba_temperatura": "bedroom",
    "soba_vlaga": "bedroom",
    "soba_tlak": "bedroom",
    "ulaz_temperatura": "ulaz",
    "ulaz_vlaga": "ulaz",
    "ulaz_tlak": "ulaz",
    "vanjska_temperatura": "vani",
    "vanjska_vlaga": "vani",
    "vanjski_tlak": "vani",
    # --- air quality: the SPS30 sits in the living area ---
    "kvaliteta_zraka_pm1": "living_room",
    "kvaliteta_zraka_pm2_5": "living_room",
    "kvaliteta_zraka_pm4": "living_room",
    "kvaliteta_zraka_pm10": "living_room",
    "broj_cestica_pm0_5": "living_room",
    "broj_cestica_pm1": "living_room",
    "broj_cestica_pm2_5": "living_room",
    "broj_cestica_pm4": "living_room",
    "broj_cestica_pm10": "living_room",
    "prosjecna_velicina_cestica": "living_room",
    "sps30_pokreni_ciscenje": "living_room",
    # --- power measurement belongs to the house, not a room ---
    "mrezni_napon": "kuca",
    "test_sct_struja": "kuca",
    "test_stvarna_snaga": "kuca",
    "test_prividna_snaga": "kuca",
    "test_faktor_snage": "kuca",
    "kat_struja": "kuca",
    "kat_stvarna_snaga": "kuca",
    "kat_prividna_snaga": "kuca",
    "kat_faktor_snage": "kuca",
    "bme280_mux_uptime": "kuca",
    "bme280_mux_wifi_signal": "kuca",
    # --- lights ---
    "svjetlo_blagavaona": "blagavaona",
    "svjetlo_boravak": "living_room",
    "svjetlo_fotelja": "living_room",
    "svjetlo_tv": "living_room",
    "svjetlo_sank": "kitchen",
    "svjetlo_kuhinja": "kitchen",
    "svjetlo_kupaona": "kupaona",
    "svjetlo_hodnik": "hodnik",
    "svjetlo_soba1": "bedroom",
    "svjetlo_soba2": "bedroom",
    "svjetlo_terasa1": "terasa",
    "svjetlo_terasa2": "terasa",
    "svjetlo_ulaz": "ulaz",
    "svjetlo_vani": "vani",
    "svjetlo_stup": "vani",
    "svjetlo_hidrofor": "kuca",
    # --- sockets ---
    "uticnica_blagavaona": "blagavaona",
    "uticnica_boravak": "living_room",
    "uticnica_tv": "living_room",
    "uticnica_kuhinja": "kitchen",
    "uticnica_frizider": "kitchen",
    "uticnica_kupaona": "kupaona",
    "uticnica_bojler": "kupaona",
    "uticnica_soba1": "bedroom",
    "uticnica_soba2": "bedroom",
    "uticnica_terasa": "terasa",
    "uticnica_ulaz": "ulaz",
    "pecnica": "kitchen",
    "slobodno1": "kuca",
    "slobodno2": "kuca",
}

# Whole entity ids that do not follow the suffix pattern.
ROOM_BY_ENTITY = {
    "media_player.smart_tv_pro": "living_room",
}

# Diagnostics worth having on the System view. Everything else stays off.
ENABLE = [
    "sensor.home_assistant_core_cpu_percent",
    "sensor.home_assistant_core_memory_percent",
    "sensor.home_assistant_supervisor_cpu_percent",
    "sensor.home_assistant_supervisor_memory_percent",
    "sensor.home_assistant_host_disk_free",
    "sensor.home_assistant_host_disk_total",
    "sensor.home_assistant_host_disk_used",
    "sensor.home_assistant_operating_system_version",
    "update.esp32_io_firmware",
    "binary_sensor.mosquitto_broker_running",
    "binary_sensor.tailscale_running",
    "binary_sensor.esphome_device_builder_running",
    "binary_sensor.studio_code_server_running",
    "binary_sensor.samba_share_running",
    "binary_sensor.advanced_ssh_web_terminal_running",
    "binary_sensor.file_editor_running",
]


async def call(ws, ident, payload):
    await ws.send(json.dumps({"id": ident, **payload}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == ident and msg.get("type") == "result":
            if not msg.get("success"):
                return {"GRESKA": msg.get("error")}
            return msg.get("result")


def target_area(entity_id: str) -> str | None:
    if entity_id in ROOM_BY_ENTITY:
        return ROOM_BY_ENTITY[entity_id]
    for suffix, area in ROOM_BY_SUFFIX.items():
        if entity_id.endswith(suffix):
            return area
    return None


async def main():
    async with websockets.connect(URL, open_timeout=10, max_size=40_000_000) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            sys.exit("auth odbijen")

        entities = await call(ws, 1, {"type": "config/entity_registry/list"})
        known = {e["entity_id"]: e for e in entities}

        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    e["entity_id"]: {
                        "area_id": e.get("area_id"),
                        "disabled_by": e.get("disabled_by"),
                    }
                    for e in entities
                },
                fh,
                indent=2,
            )
        print(f"  kopija prije izmjena: {BACKUP} ({len(entities)} entiteta)")

        ident = 100
        moved: dict[str, list[str]] = {}
        skipped = []
        for entity_id, entry in sorted(known.items()):
            area = target_area(entity_id)
            if area is None or entry.get("area_id") == area:
                continue
            ident += 1
            result = await call(
                ws,
                ident,
                {
                    "type": "config/entity_registry/update",
                    "entity_id": entity_id,
                    "area_id": area,
                },
            )
            if "GRESKA" in result:
                skipped.append((entity_id, result["GRESKA"]))
            else:
                moved.setdefault(area, []).append(entity_id)

        print(f"\n  === razmjesteno po prostorijama ({sum(len(v) for v in moved.values())}) ===")
        for area, ids in sorted(moved.items()):
            print(f"  {area:14} {len(ids):3}  {', '.join(i.split('.')[-1] for i in ids)[:110]}")

        enabled, missing = [], []
        for entity_id in ENABLE:
            entry = known.get(entity_id)
            if entry is None:
                missing.append(entity_id)
                continue
            if not entry.get("disabled_by"):
                continue
            ident += 1
            result = await call(
                ws,
                ident,
                {
                    "type": "config/entity_registry/update",
                    "entity_id": entity_id,
                    "disabled_by": None,
                },
            )
            (missing if "GRESKA" in result else enabled).append(entity_id)

        print(f"\n  === ukljuceno ({len(enabled)}) ===")
        for entity_id in enabled:
            print("   ", entity_id)
        if missing:
            print("  nije uspjelo / ne postoji:", missing)
        if skipped:
            print("  preskoceno:", skipped)


if __name__ == "__main__":  # importable, so the pure helpers can be tested
    asyncio.run(main())
