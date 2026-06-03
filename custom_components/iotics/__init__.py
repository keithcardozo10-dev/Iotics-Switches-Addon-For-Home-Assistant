"""Iotics Smart Home — custom integration for Home Assistant.

Discovers Iotics devices from the cloud API, connects to AWS IoT via
MQTT WSS for real-time state updates, and creates proper switch/number
entities that appear under Settings -> Devices & Services.

No hardcoded device data — everything is dynamic at runtime.
"""

from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .iotics_api import IoticsApiClient, slugify
from .mqtt_client import IoticsMqttClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SWITCH, Platform.NUMBER]
DOMAIN = "iotics"
UPDATE_INTERVAL = timedelta(minutes=5)

COORDINATOR = "coordinator"
MQTT_CLIENT = "mqtt_client"
API_CLIENT = "api_client"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Iotics integration from a config entry."""
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

    # Store for MQTT-driven state
    # Maps entity_id -> state (on/off for switches, 0-4 for numbers)
    entity_state: dict[str, str] = {}

    # Create coordinator that polls cloud API periodically
    async def async_update_data():
        """Fetch devices from the Iotics cloud API."""
        try:
            devices = await hass.async_add_executor_job(api.discover_devices)
            if not devices:
                raise UpdateFailed("No devices found from Iotics cloud API")
            return devices
        except Exception as err:
            raise UpdateFailed(f"Error fetching devices: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="iotics",
        update_method=async_update_data,
        update_interval=UPDATE_INTERVAL,
    )

    # First fetch
    await coordinator.async_config_entry_first_refresh()
    devices = coordinator.data

    # Register devices in HA device registry — this is how they appear
    # under Settings > Devices & Services
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

    # Build initial entity state map from first discovery
    buttons = IoticsApiClient.extract_buttons(devices)
    for b in buttons:
        room_slug = slugify(b["device_name"])
        label_slug = slugify(b["label"])
        if b["is_fan"]:
            eid = f"number.iotics_{room_slug}_{label_slug}"
        else:
            eid = f"switch.iotics_{room_slug}_{label_slug}"
        entity_state[eid] = b["status"]

    # Store on coordinator for platform entities to use
    coordinator.device_ids = device_ids
    coordinator.entity_state = entity_state

    hass.data[DOMAIN][COORDINATOR] = coordinator

    # Forward setup to entity platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Connect MQTT now that entities exist
    tokens = list(device_ids.keys())
    for token in tokens:
        mqtt.add_subscription(f"io/{token}/#")

    async def on_mqtt_message(topic: str, payload: str):
        """Update entity state from MQTT message."""
        # topic format: io/{token}/{btn}/hw
        parts = topic.split("/")
        if len(parts) < 4 or parts[0] != "io" or parts[-1] != "hw":
            return
        token = parts[1]
        btn = parts[2]
        val = payload.strip()
        if val not in ("0", "1", "2", "3", "4"):
            return

        # Find the entity for this token+btn and update its state
        for b in IoticsApiClient.extract_buttons(coordinator.data):
            if b["token"] == token and b["btn"] == btn:
                room_slug = slugify(b["device_name"])
                label_slug = slugify(b["label"])
                if b["is_fan"]:
                    eid = f"number.iotics_{room_slug}_{label_slug}"
                    new_state = val
                else:
                    eid = f"switch.iotics_{room_slug}_{label_slug}"
                    new_state = "on" if val == "1" else "off"

                coordinator.entity_state[eid] = new_state
                _LOGGER.debug("MQTT update %s = %s", eid, new_state)
                coordinator.async_update_listeners()
                break

    mqtt.set_message_callback(on_mqtt_message)
    asyncio = __import__("asyncio")
    asyncio.ensure_future(mqtt.connect())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the Iotics config entry."""
    mqtt: IoticsMqttClient = hass.data[DOMAIN].get(MQTT_CLIENT)
    if mqtt:
        await mqtt.disconnect()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN)

    return unload_ok
