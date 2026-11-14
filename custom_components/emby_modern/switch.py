"""Shutdown Courtesy Mode: warn viewers before the server restarts or shuts down."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .emby_client import CannotConnect
from .entity import EmbyServerEntity

_LOGGER = logging.getLogger(__name__)

MESSAGES = {
    "ServerRestarting": "Emby Server is restarting. Playback will be interrupted shortly.",
    "ServerShuttingDown": "Emby Server is shutting down. Playback will be interrupted shortly.",
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([EmbyCourtesySwitch(entry.runtime_data)])


class EmbyCourtesySwitch(EmbyServerEntity, SwitchEntity, RestoreEntity):
    """When on, sends a pop-up to every connected client before a restart or shutdown."""

    _attr_name = "Shutdown Courtesy Mode"
    _attr_icon = "mdi:bell-alert-outline"

    def __init__(self, data) -> None:
        super().__init__(data, data.sessions, "courtesy-switch")
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self._attr_is_on = state.state == "on"
        for message_type in MESSAGES:
            self.async_on_remove(self.client.add_message_listener(message_type, self._on_server_event))

    @callback
    def _on_server_event(self, message: dict) -> None:
        if self.is_on:
            self.hass.async_create_task(self._warn_viewers(MESSAGES[message["MessageType"]]))

    async def _warn_viewers(self, text: str) -> None:
        for sess in (self.coordinator.data or {}).get("sessions", []):
            if not sess.get("SupportsRemoteControl"):
                continue
            try:
                await self.client.send_message(sess["Id"], "Server notice", text, 10000)
            except CannotConnect:
                _LOGGER.debug("Couldn't warn %s", sess.get("DeviceName"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
