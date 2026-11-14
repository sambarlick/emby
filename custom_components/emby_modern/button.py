"""Emby buttons: server actions and per-client Stop session."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .clients import selected_clients
from .entity import EmbyClientEntity, EmbyServerEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    data = entry.runtime_data
    entities: list[ButtonEntity] = [
        EmbyServerButton(data, "restart", "Restart", "mdi:restart", data.client.restart),
        EmbyServerButton(data, "scan", "Scan Library", "mdi:database-refresh", data.client.scan_libraries),
        EmbyServerButton(data, "shutdown", "Shutdown", "mdi:power", data.client.shutdown, enabled=False),
    ]
    entities += [
        EmbyStopSessionButton(data, device_id, info["name"], info.get("app"))
        for device_id, info in selected_clients(hass, entry).items()
    ]
    async_add_entities(entities)


class EmbyServerButton(EmbyServerEntity, ButtonEntity):
    """Restart, Scan Library or Shutdown the server."""


    def __init__(self, data, key, name, icon, action, enabled: bool = True) -> None:
        super().__init__(data, data.sessions, key)
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = enabled
        self._action = action

    async def async_press(self) -> None:
        await self._action()


class EmbyStopSessionButton(EmbyClientEntity, ButtonEntity):
    """Stop playback on a client. Disabled by default: the media player's Stop does the same."""

    _attr_name = "Stop Session"
    _attr_icon = "mdi:stop-circle-outline"
    _attr_entity_registry_enabled_default = False

    def __init__(self, data, device_id, device_name, app_name) -> None:
        super().__init__(data, device_id, device_name, app_name, key="stop_session")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.session)

    async def async_press(self) -> None:
        if not self.session_id:
            raise HomeAssistantError("That client isn't connected")
        await self.client.playstate(self.session_id, "Stop")
        await self.coordinator.async_request_refresh()
