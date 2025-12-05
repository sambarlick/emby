"""Base entity for Emby Modern."""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

class EmbyEntity(CoordinatorEntity, Entity):
    """Base class for Emby entities."""

    def __init__(self, coordinator):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = coordinator.client
        
        # --- THE FIX IS HERE ---
        # We must grab the SAME ID that we used in __init__.py
        # If the config entry has a unique_id (the Server UUID), use it.
        # Otherwise, fall back to the entry_id.
        self._device_id = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id

    @property
    def device_info(self):
        """Return device info for the Emby Server."""
        system_info = self.coordinator.data.get("system_info", {})
        
        return {
            # This identifier MUST match what is in __init__.py exactly
            "identifiers": {(DOMAIN, self._device_id)},
            "name": system_info.get("ServerName", "Emby Server"),
            "manufacturer": "Emby",
            "model": "Emby Server",
            "sw_version": system_info.get("Version", "Unknown"),
            "configuration_url": self.client.get_server_url(),
     }
