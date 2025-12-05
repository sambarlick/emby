"""Support for Emby Update entity."""
from __future__ import annotations
from typing import Any

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import EmbyEntity

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([EmbyServerUpdate(coordinator)])

class EmbyServerUpdate(EmbyEntity, UpdateEntity):
    """Emby Server Update Entity."""

    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_icon = "mdi:update"

    def __init__(self, coordinator):
        super().__init__(
            coordinator, 
            coordinator.entry.entry_id, 
            coordinator.client.get_server_name(),
            client_name="Emby Server"
        )
        self._attr_name = "Emby Server Update"
        # FIX: Use the stable System GUID
        self._attr_unique_id = f"{coordinator.entry.unique_id}-update"
        self._attr_title = "Emby Server"

    @property
    def entity_picture(self):
        """Force no image so the icon displays."""
        return None

    @property
    def installed_version(self) -> str | None:
        """Version installed and in use."""
        return self.coordinator.data.get("system_info", {}).get("Version")

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""
        info = self.coordinator.data.get("system_info", {})
        # If Emby says update available, but doesn't give a version, 
        # we can't display 'Update Available' as a version string.
        # Ideally, we query the Github API or Emby releases here, 
        # but for now, we just reflect the current version if we can't find the new one.
        # (This prevents the entity from looking 'broken' with a text string as a version)
        return info.get("Version") 

    @property
    def in_progress(self) -> bool | int | None:
        return False

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Install an update (Restart Server to trigger)."""
        await self.coordinator.client.api_request("POST", "System
/Restart")
