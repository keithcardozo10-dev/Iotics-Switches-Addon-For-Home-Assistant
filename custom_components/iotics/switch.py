"""Switch platform for Iotics — on/off switches.

Creates SwitchEntity instances linked to Iotics devices in the device
registry. State is read from the coordinator's entity_state map (updated
by MQTT messages). Commands are forwarded to physical devices via LAN HTTP.
"""

from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, COORDINATOR
from .iotics_api import slugify, IoticsApiClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Iotics switch entities."""
    coordinator = hass.data[DOMAIN][COORDINATOR]
    devices = coordinator.data
    buttons = IoticsApiClient.extract_buttons(devices)
    switches = [b for b in buttons if not b["is_fan"]]

    entities = []
    for b in switches:
        room_slug = slugify(b["device_name"])
        label_slug = slugify(b["label"])
        entity_id = f"switch.iotics_{room_slug}_{label_slug}"

        entities.append(
            IoticsSwitch(
                coordinator=coordinator,
                entity_id=entity_id,
                name=b["label"],
                device_name=b["device_name"],
                token=b["token"],
                btn=b["btn"],
                ip=b["ip"],
                unique_id=f"iotics_{room_slug}_{label_slug}",
            )
        )

    async_add_entities(entities)


class IoticsSwitch(CoordinatorEntity, SwitchEntity):
    """An Iotics switch/light/plug that shows under Devices & Services."""

    def __init__(
        self,
        coordinator,
        entity_id: str,
        name: str,
        device_name: str,
        token: str,
        btn: str,
        ip: str,
        unique_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_id = entity_id
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._token = token
        self._btn = btn
        self._ip = ip

        # Link to device registry so it appears under a device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, token)},
            name=device_name,
            manufacturer="Iotics",
            model="Iotics Smart Switch",
        )

    @property
    def is_on(self) -> bool | None:
        """Return current state from the coordinator's MQTT-updated map."""
        state = self.coordinator.entity_state.get(self.entity_id, "off")
        return state == STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._send_command("1")
        self.coordinator.entity_state[self.entity_id] = "on"
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._send_command("0")
        self.coordinator.entity_state[self.entity_id] = "off"
        self.async_write_ha_state()

    async def _send_command(self, status: str) -> None:
        """Send HTTP command to the physical Iotics device."""
        if not self._ip:
            _LOGGER.warning("No IP for %s, cannot send command", self.entity_id)
            return

        import urllib.request
        loop = __import__("asyncio").get_event_loop()
        url = f"http://{self._ip}/action?button={self._btn}&status={status}"
        try:
            await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(url, timeout=5).read()
            )
            _LOGGER.debug("HTTP command sent: %s", url)
        except Exception as err:
            _LOGGER.error("HTTP command to %s failed: %s", url, err)
