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
    
    # 1. Add the Active Streams Sensor
    entities.append(EmbyActiveStreamsSensor(coordinator))
    
    # 2. Add the Server Status Sensor
    entities.append(EmbyServerStatusSensor(coordinator))
    
    # 3. Add a Sensor for every Library found
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
        # Note: Ensure your EmbyClient supports 'add_message_listener'
        try:
            self.coordinator.client.add_message_listener("ServerRestarting", self._handle_restart_shutdown)
            self.coordinator.client.add_message_listener("ServerShuttingDown", self._handle_restart_shutdown)
        except AttributeError:
             pass # Gracefully fail if client doesn't support websockets yet
        
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

class EmbyActiveStreamsSensor(EmbyEntity, SensorEntity):
    """Sensor to track active streams."""
    
    def __init__(self, coordinator):
        ver = coordinator.data.get("system_info", {}).get("Version", "Unknown")
        super().__init__(
            coordinator, 
            device_id=None, 
            client_name="Emby Server", 
            version=ver
        )
        self._attr_name = "Active Streams"
        self._attr_unique_id = f"{coordinator.entry.unique_id}-active-streams"
        self._attr_native_unit_of_measurement = "streams"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:play-network"

    @property
    def native_value(self) -> int:
        return sum(1 for sess in self.coordinator.data.get("sessions", []) if "NowPlayingItem" in sess)

    @property
    def extra_state_attributes(self):
        streams = []
        for sess in self.coordinator.data.get("sessions", []):
            if "NowPlayingItem" not in sess: continue
            item = sess["NowPlayingItem"]
            title = item.get("Name")
            
            if item.get("Type") == "Episode":
                s = item.get("ParentIndexNumber")
                e = item.get("IndexNumber")
                if s is not None and e is not None:
                    title = f"{item.get('SeriesName')} - S{s:02d}E{e:02d} - {title}"
            elif item.get("ProductionYear"):
                title = f"{title} ({item.get('ProductionYear')})"
            
            streams.append({
                "user": sess.get("UserName", "Unknown"),
                "device": sess.get("DeviceName", "Unknown"),
                "title": title,
            })
        return {"active_streams": streams}

class EmbyLibrarySensor(EmbyEntity, SensorEntity):
    """Sensor to track library items."""

    def __init__(self, coordinator, lib_data):
        ver = coordinator.data.get("system_info", {}).get("Version", "Unknown")
        super().__init__(
            coordinator, 
            device_id=None, 
            client_name="Emby Server", 
            version=ver
        )
        self._lib_id = lib_data["Id"]
        self._lib_name = lib_data["Name"]
        self._lib_type = lib_data["Type"]
        self._attr_name = self._lib_name
        
        self._attr_unique_id = f"{coordinator.entry.unique_id}-library-{self._lib_id}"
        self._attr_native_unit_of_measurement = "items"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def icon(self):
        t = self._lib_type.lower()
        if "movie" in t: return "mdi:movie"
        if "tv" in t or "series" in t: return "mdi:television-classic"
        if "music" in t: return "mdi:music"
        if "photo" in t: return "mdi:image"
        if "book" in t: return "mdi:book"
        return "mdi:folder-multiple"

    @property
    def native_value(self) -> int | str:
        libraries = self.coordinator.data.get("libraries", [])
        for lib in libraries:
            if lib["Id"] == self._lib_id:
                return lib["Count"]
        return 0

    @property
    def extra_state_attributes(self):
        libraries = self.coordinator.data.get("libraries", [])
        attrs = {}
        items = []

        for lib in libraries:
            if lib["Id"] == self._lib_id:
                items = lib.get("LatestItems", [])
                break
        
        if not items:
            if self.native_value == 0:
                 return {"status": "Library is empty."}
            else:
                 return {"status": "No recently added items."}

        if self._lib_type == "livetv":
            for ch in items:
                if isinstance(ch, dict):
                    attrs[ch.get("name", "Unknown")] = ch.get("program", "Unknown")
            return attrs

        for item in items:
            key_text = "Unknown"
            value_text = ""

            if isinstance(item, dict):
                name = item.get("Name", "Unknown")
                year = item.get("ProductionYear")
                year_str = str(year) if year else ""

                if item.get("Type") == "Episode":
                    series = item.get("SeriesName", "Unknown Series")
                    s = item.get("ParentIndexNumber")
                    e = item.get("IndexNumber")
                    if s is not None and e is not None:
                        key_text = f"S{s:02d}E{e:02d} {name}"
                    else:
                        key_text = name
                    value_text = series

                else:
                    key_text = name
                    value_text = year_str if year_str else ""
            
            elif isinstance(item, str):
                key_text = item
                value_text = ""

            key = key_text
            count = 2
            while key in attrs:
                key = f"{key_text} ({count})"
                count += 1
            
            attrs[key] = value_text
            
        return attrs
