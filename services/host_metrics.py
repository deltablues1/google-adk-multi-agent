"""Publishes the Jarvis Pi's own vital signs to Home Assistant over MQTT.

Home Assistant can watch its own Raspberry Pi with the System Monitor
integration, but the Pi that runs Jarvis is a different machine and nothing was
reporting it at all. When that Pi runs out of disk, overheats or simply drops
off the network, the first sign was the assistant going quiet.

MQTT discovery is used rather than a REST push so the sensors appear as one
device, and -- more importantly -- so a last will can be registered: if this
process dies or the network drops, the broker publishes "offline" on our behalf
and every sensor in Home Assistant goes unavailable. A gap in reported numbers
is easy to miss; an entity that says it is offline is not.

Everything is read straight from /proc and /sys. That is Linux-specific, which
this machine is, and it avoids a dependency for arithmetic this simple.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
STATE_PREFIX = "google_clause/jarvis_host"
DEVICE_ID = "jarvis_pi_host"

_PROC_STAT = Path("/proc/stat")
_PROC_MEMINFO = Path("/proc/meminfo")
_PROC_UPTIME = Path("/proc/uptime")
_THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


# --- parsing, kept separate from the reading so it can be tested -------------


def parse_cpu_times(stat_text: str) -> tuple[int, int]:
    """Return (idle, total) jiffies from the aggregate line of /proc/stat."""
    for line in stat_text.splitlines():
        if line.startswith("cpu "):
            fields = [int(value) for value in line.split()[1:]]
            # user nice system idle iowait irq softirq steal ...
            idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
            return idle, sum(fields)
    raise ValueError("no aggregate cpu line in /proc/stat")


def parse_memory_percent(meminfo_text: str) -> float:
    """Percentage of memory in use, counting cache as free like `free -m` does."""
    values = {}
    for line in meminfo_text.splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            values[key] = float(rest.strip().split()[0])
    total = values.get("MemTotal", 0.0)
    if not total:
        raise ValueError("no MemTotal in /proc/meminfo")
    available = values.get("MemAvailable", total)
    return round((total - available) / total * 100, 1)


def parse_temperature(thermal_text: str) -> float:
    """Millidegrees in the file, degrees out."""
    return round(int(thermal_text.strip()) / 1000, 1)


def parse_uptime_seconds(uptime_text: str) -> float:
    return float(uptime_text.split()[0])


def local_ip_address() -> str:
    """The address this machine uses to reach the LAN, without resolving names."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet is sent for UDP connect; it only picks the outbound route.
        probe.connect(("192.168.100.1", 1))
        return probe.getsockname()[0]
    except OSError:
        return ""
    finally:
        probe.close()


# --- collecting ---------------------------------------------------------------


class MetricsReader:
    """Reads the host's vital signs. CPU needs two samples, hence the state."""

    def __init__(self) -> None:
        self._last_cpu: tuple[int, int] | None = None

    def cpu_percent(self, stat_text: str) -> float | None:
        """None on the first call -- a single sample says nothing about load."""
        idle, total = parse_cpu_times(stat_text)
        previous, self._last_cpu = self._last_cpu, (idle, total)
        if previous is None:
            return None
        idle_delta = idle - previous[0]
        total_delta = total - previous[1]
        if total_delta <= 0:
            return None
        return round((1 - idle_delta / total_delta) * 100, 1)

    def collect(self) -> dict:
        """Everything worth reporting. Individual failures are left out."""
        metrics: dict[str, object] = {}

        try:
            cpu = self.cpu_percent(_PROC_STAT.read_text())
            if cpu is not None:
                metrics["cpu"] = cpu
        except (OSError, ValueError, IndexError) as err:
            logger.debug("CPU unreadable: %s", err)

        try:
            metrics["memory"] = parse_memory_percent(_PROC_MEMINFO.read_text())
        except (OSError, ValueError, IndexError) as err:
            logger.debug("Memory unreadable: %s", err)

        try:
            usage = os.statvfs("/")
            used = (usage.f_blocks - usage.f_bfree) * usage.f_frsize
            total = usage.f_blocks * usage.f_frsize
            if total:
                metrics["disk"] = round(used / total * 100, 1)
                metrics["disk_free_gb"] = round(
                    usage.f_bavail * usage.f_frsize / 1024**3, 1
                )
        except OSError as err:
            logger.debug("Disk unreadable: %s", err)

        try:
            metrics["temperature"] = parse_temperature(_THERMAL.read_text())
        except (OSError, ValueError) as err:
            logger.debug("Temperature unreadable: %s", err)

        try:
            uptime = parse_uptime_seconds(_PROC_UPTIME.read_text())
            metrics["uptime_seconds"] = int(uptime)
            # A boot timestamp lets Home Assistant render "5 days ago" itself,
            # and stays correct without being republished.
            metrics["boot"] = time.strftime(
                "%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() - uptime)
            )
        except (OSError, ValueError, IndexError) as err:
            logger.debug("Uptime unreadable: %s", err)

        try:
            metrics["load_1m"] = round(os.getloadavg()[0], 2)
        except OSError:
            pass

        address = local_ip_address()
        if address:
            metrics["ip"] = address

        return metrics


# --- what Home Assistant is told ----------------------------------------------

# name, key in the state payload, unit, device_class, state_class, icon
_SENSORS = [
    ("Procesor", "cpu", "%", None, "measurement", "mdi:cpu-64-bit"),
    ("Memorija", "memory", "%", None, "measurement", "mdi:memory"),
    ("Disk", "disk", "%", None, "measurement", "mdi:harddisk"),
    ("Slobodno na disku", "disk_free_gb", "GB", None, "measurement", "mdi:harddisk"),
    ("Temperatura", "temperature", "°C", "temperature", "measurement", None),
    ("Opterećenje", "load_1m", None, None, "measurement", "mdi:gauge"),
    ("Pokrenut", "boot", None, "timestamp", None, "mdi:clock-start"),
    ("IP adresa", "ip", None, None, None, "mdi:ip-network"),
]


def build_discovery(device_name: str, api_url: str) -> list[tuple[str, dict]]:
    """(topic, payload) for each sensor, in the shape MQTT discovery expects."""
    device = {
        "identifiers": [DEVICE_ID],
        "name": device_name,
        "manufacturer": "Raspberry Pi",
        "model": "Raspberry Pi 5 (Jarvis)",
        "configuration_url": api_url,
    }
    messages = []
    for name, key, unit, device_class, state_class, icon in _SENSORS:
        payload = {
            "name": name,
            "unique_id": f"{DEVICE_ID}_{key}",
            "object_id": f"jarvis_pi_{key}",
            "state_topic": f"{STATE_PREFIX}/state",
            "value_template": "{{ value_json." + key + " }}",
            "availability_topic": f"{STATE_PREFIX}/availability",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        if state_class:
            payload["state_class"] = state_class
        if icon:
            payload["icon"] = icon
        messages.append(
            (f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/{key}/config", payload)
        )
    return messages


class HostMetricsPublisher:
    """Publishes the metrics on a timer until asked to stop."""

    def __init__(self) -> None:
        self.enabled = os.getenv("HOST_METRICS_ENABLED", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.broker = os.getenv("MQTT_BROKER", "").strip()
        self.port = int(os.getenv("MQTT_PORT", "1883"))
        self.username = os.getenv("MQTT_USER", "").strip()
        self.password = os.getenv("MQTT_PASS", "").strip()
        self.interval = float(os.getenv("HOST_METRICS_INTERVAL_SECONDS", "30"))
        self.device_name = os.getenv("HOST_METRICS_DEVICE_NAME", "Jarvis Pi").strip()
        self.api_url = os.getenv("HOST_METRICS_URL", "http://192.168.100.105:8000")
        self._reader = MetricsReader()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._client = None

    def is_available(self) -> bool:
        return self.enabled and bool(self.broker)

    def start(self) -> bool:
        """Begin publishing in the background. Never raises."""
        if not self.is_available():
            logger.info("Host metrics not published (disabled or no MQTT broker)")
            return False
        self._thread = threading.Thread(
            target=self._run, name="host-metrics", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._client is not None:
            try:
                self._client.publish(f"{STATE_PREFIX}/availability", "offline", retain=True)
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001 - shutting down anyway
                pass

    def _run(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("paho-mqtt missing; host metrics will not be published")
            return

        try:
            client = mqtt.Client(client_id=f"{DEVICE_ID}_publisher")
            if self.username:
                client.username_pw_set(self.username, self.password)
            # The broker announces our death even when we cannot.
            client.will_set(f"{STATE_PREFIX}/availability", "offline", retain=True)
            client.connect(self.broker, self.port, keepalive=60)
            client.loop_start()
            self._client = client
        except Exception as err:  # noqa: BLE001 - metrics must never break the app
            logger.warning("Host metrics could not reach the MQTT broker: %s", err)
            return

        for topic, payload in build_discovery(self.device_name, self.api_url):
            client.publish(topic, json.dumps(payload), retain=True)
        client.publish(f"{STATE_PREFIX}/availability", "online", retain=True)
        logger.info(
            "Publishing host metrics to %s:%s every %.0fs",
            self.broker, self.port, self.interval,
        )

        # The first CPU reading needs a previous sample to compare against.
        self._reader.collect()

        while not self._stop.wait(self.interval):
            try:
                metrics = self._reader.collect()
                client.publish(f"{STATE_PREFIX}/state", json.dumps(metrics))
            except Exception as err:  # noqa: BLE001
                logger.warning("Could not publish host metrics: %s", err)
