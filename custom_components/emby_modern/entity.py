"""Base entity for Emby Modern."""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

class EmbyEntity(CoordinatorEntity, Entity):
    """Base class for Emby entities."""
    
    _attr_has_entity_name = True # FIX: Tells HA to name entity relative to device
    _attr_name = None            # FIX: Default to device name (e.g. "Living Room TV")

    def __init__(self, coordinator, device_id=None, device_name=None, client_name=None, version=None):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.client = coordinator.client
        
        # 1. Determine Device Identity
        if device_id:
            self._device_id = device_id
            self._device_name = device_name
            self._model = client_name
            self._version = version
        else:
            # Fallback for Server Entities (like the Restart Button)
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
        # Use child class ID if provided (e.g. for Button/Update entities)
        if self._attr_unique_id:
            return self._attr_unique_id
            
        # Otherwise, calculate one based on the device
        return f"{self.coordinator.entry.unique_id}-{self._device_id}"
