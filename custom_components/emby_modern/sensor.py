"""Support for Emby sensors."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .entity import EmbyEntity

# Define the possible states
EMBY_STATE_RUNNING = "Running"
EMBY_STATE_RESTARTING = "Restarting"
EMBY_STATE_SHUTTING_DOWN = "Shutting Down"
EMBY_STATE_UNAVAILABLE = "Unavailable"

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities = []
    
    # 1. Add the Active Streams Sensor (RETAINED)
    entities.append(EmbyActiveStreamsSensor(coordinator))
    
    # 2. Add the Server Status Sensor (NEW)
    entities.append(EmbyServerStatusSensor(coordinator))
    
    # 3. Add a Sensor for every Library found (RETAINED)
    libraries = coordinator.data.get("libraries", [])
    for lib in libraries:
        entities.append(EmbyLibrarySensor(coordinator, lib))

    async_add_entities(entities)

class EmbyServerStatusSensor(EmbyEntity, SensorEntity):
    """Sensor to track the Emby server's operational status."""
    
    def __init__(self, coordinator):
        ver = coordinator.data.get("system_info", {}).get("Version", "Unknown")
        super().__init__(
            coordinator, 
            device_id=None,
            client_name="Emby Server", 
            version=ver
        )
        self._attr_name = "Server Status"
        self._attr_unique_id = f"{coordinator.entry.unique_id}-server-status"
        self._attr_icon = "mdi:server-network"
        self._current_state = EMBY_STATE_RUNNING

    @property
    def native_value(self) -> str:
        """Return the current operational status."""
        if not self.coordinator.last_update_success:
            return EMBY_STATE_UNAVAILABLE
        return self._current_state

    @property
    def icon(self):
        if self._current_state in [EMBY_STATE_RESTARTING, EMBY_STATE_SHUTTING_DOWN]:
            return "mdi:server-network-off"
        if not self.coordinator.last_update_success:
             return "mdi:server-network-off"
        return "mdi:server-network"

    async def async_added_to_hass(self):
        """Subscribe to specific WebSocket events to update state instantly."""
        await super().async_added_to_hass()
        
        # Subscribe to Emby WebSocket events handled by the client object
        self.coordinator.client.add_message_listener("ServerRestarting", self._handle_restart_shutdown)
        self.coordinator.client.add_message_listener("ServerShuttingDown", self._handle_restart_shutdown)
        
        # Reset state when coordinator successfully reconnects after a failure
        self.coordinator.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_restart_shutdown(self, data):
        """Update sensor state based on the specific event."""
        event_name = data.get("EventName")
        if event_name == "ServerRestarting":
            self._current_state = EMBY_STATE_RESTARTING
        elif event_name == "ServerShuttingDown":
            self._current_state = EMBY_STATE_SHUTTING_DOWN
            
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self):
        """Called when the coordinator successfully updates."""
        # If we successfully update, the server is running again
        if self.coordinator.last_update_success:
            self._current_state = EMBY_STATE_RUNNING
        else:
            self._current_state = EMBY_STATE_UNAVAILABLE
            
        self.async_write_ha_state()

# ... EmbyActiveStreamsSensor and EmbyLibrarySensor remain unchanged ...
