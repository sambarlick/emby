"""Base Entity for Emby."""
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class EmbyEntity(CoordinatorEntity):
    """Defines a base Emby entity."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, device_id, device_name, client_name=None, version=None):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = device_id
        
        # Use the real client name (e.g. "Emby for Android") if available
        model_name = client_name or "Emby Client"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="Emby",
            model=model_name,
            name=device_name,
            sw_version=version,
            via_device=(DOMAIN, coordinator.entry.entry_id),
        )
        
