"""Support for Emby sensors."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .entity import EmbyEntity

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities = []
    entities.append(EmbyActiveStreamsSensor(coordinator))
    
    libraries = coordinator.data.get("libraries", [])
    for lib in libraries:
        entities.append(EmbyLibrarySensor(coordinator, lib))

    async_add_entities(entities)

class EmbyActiveStreamsSensor(EmbyEntity, SensorEntity):
    def __init__(self, coordinator):
        ver = coordinator.data.get("system_info", {}).get("Version", "Unknown")
        super().__init__(
            coordinator, 
            coordinator.entry.entry_id, 
            coordinator.client.get_server_name(),
            client_name="Emby Server", 
            version=ver
        )
        self._attr_name = "Active Streams"
        # FIX: Use the Config Entry Unique ID (The System GUID)
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
            
            # Simple Stream formatting
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
    def __init__(self, coordinator, lib_data):
        ver = coordinator.data.get("system_info", {}).get("Version", "Unknown")
        super().__init__(
            coordinator, 
            coordinator.entry.entry_id, 
            coordinator.client.get_server_name(),
            client_name="Emby Server", 
            version=ver
        )
        self._lib_id = lib_data["Id"]
        self._lib_name = lib_data["Name"]
        self._lib_type = lib_data["Type"]
        self._attr_name = self._lib_name
        
        # FIX: Use the Config Entry Unique ID (The System GUID)
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
        """Return simple formatted attributes (Title (Year))."""
        libraries = self.coordinator.data.get("libraries", [])
        attrs = {}
        items = []

        # Find the specific library and its latest items
        for lib in libraries:
            if lib["Id"] == self._lib_id:
                items = lib.get("LatestItems", [])
                break
        
        if not items:
            if self.native_value == 0:
                 return {"status": "Library is empty."}
            else:
                 return {"status": "No recently added items."}

        # 1. Live TV
        if self._lib_type == "livetv":
            for ch in items:
                if isinstance(ch, dict):
                    attrs[ch.get("name", "Unknown")] = ch.get("program", "Unknown")
            return attrs

        # 2. Movies & Series processing
        is_movie_library = "movie" in self._lib_type.lower()
        
        for item in items:
            left_text = "Unknown"
            right_text = "" # Default to empty

            # --- If Item is Dict (Ideal) ---
            if isinstance(item, dict):
                name = item.get("Name", "Unknown")
                
                # Capture year data
                year = item.get("ProductionYear")
                if year is None:
                    premiere_date = item.get("PremiereDate", "")
                    if premiere_date and len(premiere_date) >= 4:
                        year = premiere_date[:4]
                year_str = str(year) if year else "Unknown Year"

                if item.get("Type") == "Episode":
                    # Format: Series Name (Year) -> SxxExx Episode Title
                    series = item.get("SeriesName", "Unknown Series")
                    s = item.get("ParentIndexNumber")
                    e = item.get("IndexNumber")
                    
                    left_text = f"{series} ({year_str})" if year and year_str != "Unknown Year" else series
                    if s is not None and e is not None:
                        right_text = f"S{s:02d}E{e:02d} {name}"
                    else:
                        right_text = name
                else:
                    # FIX: Format for Movies: Title -> <empty>
                    if is_movie_library:
                        left_text = name 
                        right_text = "" 
                    else:
                        left_text = f"{name} ({year_str})" if year and year_str != "Unknown Year" else name
                        right_text = item.get("Type", "Media")
            
            # --- If Item is String (Fallback) ---
            elif isinstance(item, str):
                if " - " in item:
                    parts = item.split(" - ", 1)
                    left_text = parts[0]
                    right_text = parts[1]
                else:
                    left_text = item
                    right_text = "" if is_movie_library else "Media"

            # --- Deduplicate Keys ---
            key = left_text
            count = 2
            while key in attrs:
                key = f"{left_text} ({count})"
                count += 1
            
            attrs[key] = right_text
            
        return attrs
        
