"""Support for Emby switches."""
from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .entity import EmbyEntity

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    
    # The courtesy switch is a server-level feature (only one per server)
    async_add_entities([EmbyCourtesySwitch(coordinator)])

class EmbyCourtesySwitch(EmbyEntity, SwitchEntity):
    """Switch to toggle the automatic 'Server Shutdown' message feature."""
    
    _attr_icon = "mdi:bell-alert-outline"
    
    def __init__(self, coordinator):
        # Attach to the server's device entry
        ver = coordinator.data.get("system_info", {}).get("Version", "Unknown")
        super().__init__(
            coordinator, 
            device_id=None,
            client_name="Emby Server", 
            version=ver
        )
        self._attr_name = "Shutdown Courtesy Mode"
        self._attr_unique_id = f"{coordinator.entry.unique_id}-courtesy-switch"
        self._is_on = False  # Default to off

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        # For simplicity, we manage the state internally here. 
        # For persistence across HA restarts, this should eventually use entry.options.
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        self._is_on = False
        self.async_write_ha_state()
