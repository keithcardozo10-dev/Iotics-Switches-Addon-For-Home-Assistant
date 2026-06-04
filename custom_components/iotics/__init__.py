"""Iotics Smart Home — custom integration for Home Assistant.

Architecture (exact Mac replica):
  1. Cloud API login + device discovery (at startup and every 5 min)
  2. MQTT WSS to AWS IoT for realtime push updates
  3. HA REST API sync for initial states (via supervisor endpoint)
  4. call_service interception for toggle --> device command

No cloud polling loops. No dashboard generation. Pure realtime.
"""

from __future__ import annotations
import asyncio
import logging
import os
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .iotics_api import IoticsApiClient, slugify, is_fan_button
from .mqtt_client import IoticsMqttClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SWITCH, Platform.NUMBER]
DOMAIN = "iotics"
UPDATE_INTERVAL = timedelta(minutes=5)

COORDINATOR = "coordinator"
MQTT_CLIENT = "mqtt_client"
API_CLIENT = "api_client"
MQTT_TASK = "mqtt_task"

# Supervisor socket helper — shared to avoid code duplication
_SOCKET_PATH = "/run/supervisor/core.sock"


def _push_state_to_supervisor(eid: str, state_val: str) -> bool:
    """Push a single entity state to HA via supervisor Unix socket.

    This is used ONLY for initial state push on startup.
    Runtime updates use coordinator.async_update_listeners() instead.
    """
    import json, socket, http.client
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token or not os.path.exists(_SOCKET_PATH):
        return False
    try:
        domain = eid.split(".")[0]
        attrs = {"source": "iotics_mqtt"}
        if domain == "number":
            attrs["icon"] = "mdi:fan-speed"
        body = json.dumps({"state": state_val, "attributes": attrs})
        conn = http.client.HTTPConnection("localhost")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(_SOCKET_PATH)
        conn.request("POST", f"/api/states/{eid}",
            body=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return True
    except Exception:
        return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Iotics integration from a config entry."""
    _LOGGER.info("=== IOTICS ASYNC_SETUP_ENTRY STARTED ===")
    hass.data.setdefault(DOMAIN, {})

    # Create API client
    email = entry.data["email"]
    password = entry.data["password"]
    appid = entry.data.get("appid", "696f74696373617070")
    api = IoticsApiClient(email, password, appid)
    hass.data[DOMAIN][API_CLIENT] = api

    # Create MQTT client
    mqtt = IoticsMqttClient()
    hass.data[DOMAIN][MQTT_CLIENT] = mqtt

    # Coordinator: cloud API polling for backup + initial discovery
    async def async_update_data():
        _LOGGER.info("Coordinator async_update_data called")
        try:
            devices = await hass.async_add_executor_job(api.discover_direct)
            if not devices:
                _LOGGER.error("No devices found from Iotics cloud API")
                raise UpdateFailed("No devices found from Iotics cloud API")
            _LOGGER.info("Coordinator fetched %d devices successfully", len(devices))
            return devices
        except Exception as err:
            _LOGGER.error("Coordinator fetch failed: %s", err, exc_info=True)
            raise UpdateFailed(f"Error fetching devices: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name="iotics",
        update_method=async_update_data,
        update_interval=UPDATE_INTERVAL,
    )

    # First fetch
    try:
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.info("Coordinator first refresh succeeded: %d devices", len(coordinator.data))
    except Exception as e:
        _LOGGER.error("Coordinator first refresh FAILED: %s", e, exc_info=True)
        return False
    devices = coordinator.data

    _LOGGER.info("Registering %d devices in HA registry...", len(devices))
    dev_reg = dr.async_get(hass)
    device_ids: dict[str, str] = {}
    for dev in devices:
        token = dev.get("hardwaretoken") or dev.get("mac", "").replace(":", "")
        hwname = dev.get("hardwarename") or dev.get("room") or token
        connections = set()
        if dev.get("ip"):
            connections.add(("ip", dev["ip"]))
        device = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, token)},
            name=hwname,
            manufacturer="Iotics",
            model="Iotics Smart Switch",
            sw_version="1.0",
            connections=connections,
        )
        device_ids[token] = device.id
    _LOGGER.info("Registered %d devices", len(device_ids))

    # Entity state map: entity_id -> state string
    entity_state: dict[str, str] = {}
    # O(1) MQTT lookup
    mqtt_lookup: dict[str, dict[str, Any]] = {}

    # Build entity state map + MQTT lookup
    buttons = IoticsApiClient.extract_buttons(devices)
    _LOGGER.info("Extracted %d buttons from devices", len(buttons))
    for b in buttons:
        room_slug = slugify(b["device_name"])
        label_slug = slugify(b["label"])
        raw_status = b["status"]

        if b["is_fan"]:
            number_eid = f"number.iotics_{room_slug}_{label_slug}"
            switch_eid = f"switch.iotics_{room_slug}_fan"
            entity_state[number_eid] = raw_status
            entity_state[switch_eid] = "on" if raw_status and raw_status != "0" else "off"
            key = f"{b['token']}_{b['btn']}"
            mqtt_lookup[key] = {"eid": number_eid, "is_fan": True, "ip": b["ip"], "btn": b["btn"]}
            switch_key = f"{b['token']}_{b['btn']}_switch"
            mqtt_lookup[switch_key] = {"eid": switch_eid, "is_fan": False, "ip": b["ip"], "btn": b["btn"]}
        else:
            eid = f"switch.iotics_{room_slug}_{label_slug}"
            entity_state[eid] = "on" if raw_status == "1" else "off"
            key = f"{b['token']}_{b['btn']}"
            mqtt_lookup[key] = {"eid": eid, "is_fan": False, "ip": b["ip"], "btn": b["btn"]}

    _LOGGER.info("Built entity_state with %d entries, mqtt_lookup with %d entries",
                 len(entity_state), len(mqtt_lookup))

    coordinator.device_ids = device_ids
    coordinator.entity_state = entity_state
    coordinator.mqtt_lookup = mqtt_lookup

    # Store coordinator in hass.data BEFORE forwarding to entity platforms
    # so switch.py and number.py can access it during async_setup_entry
    hass.data[DOMAIN][COORDINATOR] = coordinator

    # Forward to entity platforms
    _LOGGER.info("Forwarding setup to entity platforms...")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Entity platform setups done")

    # Push initial states via Supervisor Unix socket (one-shot at startup)
    def _push_initial_states():
        pushed = 0
        for eid, state_val in entity_state.items():
            if _push_state_to_supervisor(eid, state_val):
                pushed += 1
        _LOGGER.info("Pushed %d/%d states to HA via socket at startup", pushed, len(entity_state))

    await hass.async_add_executor_job(_push_initial_states)

    # --- MQTT setup ---

    mqtt.add_subscription("io/+/+/+/hw")

    async def on_mqtt_message(topic: str, payload: str):
        """Realtime update from MQTT — updates entity_state and notifies listeners.

        Uses coordinator.async_update_listeners() to let each entity
        read its state from entity_state and call async_write_ha_state().
        This avoids the race condition of pushing ALL states via supervisor socket
        on every MQTT message (which was reverting manual toggles).
        """
        parts = topic.split("/")
        if len(parts) == 5 and parts[-1] == "hw":
            token, btn = parts[1], parts[2]
        elif len(parts) == 4 and parts[-1] == "hw":
            token, btn = parts[1], parts[2]
        else:
            return

        val = payload.strip()
        if val not in ("0", "1", "2", "3", "4"):
            return

        key = f"{token}_{btn}"
        info = coordinator.mqtt_lookup.get(key)
        if info:
            if info["is_fan"]:
                coordinator.entity_state[info["eid"]] = val
                switch_key = f"{token}_{btn}_switch"
                switch_info = coordinator.mqtt_lookup.get(switch_key)
                if switch_info:
                    coordinator.entity_state[switch_info["eid"]] = "on" if val != "0" else "off"
            else:
                coordinator.entity_state[info["eid"]] = "on" if val == "1" else "off"

        # Notify entities to refresh from entity_state
        coordinator.async_update_listeners()

    def _sync_mqtt_callback(topic, payload):
        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(on_mqtt_message(topic, payload), loop)
        except RuntimeError:
            pass

    mqtt.set_message_callback(_sync_mqtt_callback)

    _LOGGER.info("Iotics: starting MQTT connection...")
    mqtt_task = asyncio.create_task(mqtt.connect())
    hass.data[DOMAIN][MQTT_TASK] = mqtt_task
    _LOGGER.info("MQTT connection task created and stored")

    # --- call_service listener: ONLY handles number.set_value (fan speed) ---
    # Switch toggles are handled by IoticsSwitch.async_turn_on/off directly.
    # This avoids double-fire race conditions.
    async def _call_service_listener(event):
        """Intercept call_service events for fan speed only."""
        if event.data.get("domain") != "number":
            return
        service = event.data.get("service", "")
        target = event.data.get("target", {})
        entity_ids = target.get("entity_id", [])
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        for eid in entity_ids:
            if not eid.startswith("number.iotics_"):
                continue

            data = event.data.get("service_data", {})
            desired = str(int(data.get("value", 0)))
            if desired not in ("0", "1", "2", "3", "4"):
                continue

            coordinator.entity_state[eid] = desired
            _LOGGER.info("call_service number: %s -> %s", eid, desired)

            # Find device IP and button from mqtt_lookup
            ip = ""
            btn = ""
            for key, info in coordinator.mqtt_lookup.items():
                if info["eid"] == eid:
                    ip = info.get("ip", "")
                    btn = info.get("btn", "")
                    break

            if ip and btn:
                try:
                    import urllib.request
                    req = urllib.request.Request(
                        f"http://{ip}/action?button={btn}&status={desired}"
                    )
                    urllib.request.urlopen(req, timeout=3)
                    _LOGGER.info("Iotics: sent fan cmd %s -> %s btn=%s speed=%s", eid, ip, btn, desired)
                except Exception as err:
                    _LOGGER.error("Iotics: fan cmd failed for %s: %s", eid, err)

    hass.bus.async_listen("call_service", _call_service_listener)
    _LOGGER.info("=== IOTICS ASYNC_SETUP_ENTRY COMPLETE ===")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the Iotics config entry."""
    _LOGGER.info("Iotics: unloading config entry")
    mqtt: IoticsMqttClient = hass.data[DOMAIN].get(MQTT_CLIENT)
    if mqtt:
        await mqtt.disconnect()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN)
    return unload_ok
