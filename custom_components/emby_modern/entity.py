"""Base entity for Emby Modern."""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

class EmbyEntity(CoordinatorEntity, Entity):
    """Base class for Emby entities."""

    # FIX: Added arguments to match what media_player/sensor are sending
    def __init__(self, coordinator, device_id=None, device_name=None, client_name=None, version=None):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = coordinator.client
        
        # If a specific device_id was passed (e.g. from a Media Player), use it.
        # Otherwise, default to the Server ID (for sensors/buttons).
        if device_id:
            self._device_id = device_id
            self._device_name = device_name
            self._model = client_name
            self._version = version
        else:
            # Fallback logic for Server entities
            self._device_id = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
            self._device_name = self.coordinator.data.get("system_info", {}).get("ServerName", "Emby Server")
            self._model = "Emby Server"
            self._version = self.coordinator.data.get("system_info", {}).get("Version", "Unknown")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the Emby Server or Client."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Emby",
            model=self._model,
            sw_version=self._version,
            configuration_url=self.client.get_server_url(),
        )
    
    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        # This ensures the entity has a stable ID in the HA Registry
        return f"{self.coordinator.entry.unique_id}-{self._device_id}"
