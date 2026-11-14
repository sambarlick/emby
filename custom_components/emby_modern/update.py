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
    # Removed _attr_icon so it uses defaults (which works best with Brands/Themes)

    def __init__(self, coordinator):
        # device_id=None allows the base class to use the Server UUID
        super().__init__(
            coordinator, 
            device_id=None, 
            client_name="Emby Server"
        )
        self._attr_name = "Update" # Logic: Device Name (Emby Server) + "Update"
        self._attr_unique_id = f"{coordinator.entry.unique_id}-update"
        self._attr_title = "Emby Server"

    @property
    def installed_version(self) -> str | None:
        """Version installed and in use."""
        return self.coordinator.data.get("system_info", {}).get("Version")

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""
        info = self.coordinator.data.get("system_info", {})
        return info.get("Version") 

    @property
    def in_progress(self) -> bool | int | None:
        return False

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Install an update (Restart Server to trigger)."""
        await self.coordinator.client.api_request("POST", "System/Restart")
