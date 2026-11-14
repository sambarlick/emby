"""Emby sensors: server status, active streams and one per library."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import EmbyServerEntity

STATUS_RUNNING = "running"
STATUS_RESTARTING = "restarting"
STATUS_SHUTTING_DOWN = "shutting_down"
STATUS_UNREACHABLE = "unreachable"
STATUS_OPTIONS = [STATUS_RUNNING, STATUS_RESTARTING, STATUS_SHUTTING_DOWN, STATUS_UNREACHABLE]

LIBRARY_ICONS = {
    "movies": "mdi:movie", "tvshows": "mdi:television-classic", "music": "mdi:music",
    "musicvideos": "mdi:music-box", "photos": "mdi:image", "homevideos": "mdi:video",
    "books": "mdi:book", "audiobooks": "mdi:book-music", "livetv": "mdi:television",
    "boxsets": "mdi:movie-open", "playlists": "mdi:playlist-play",
}


def _episode_label(item: dict) -> str:
    season, episode = item.get("ParentIndexNumber"), item.get("IndexNumber")
    if season is not None and episode is not None:
        return f"S{season:02d}:E{episode:02d} - {item.get('Name')}"
    return item.get("Name", "Unknown")


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    data = entry.runtime_data
    entities: list[SensorEntity] = [EmbyServerStatusSensor(data), EmbyActiveStreamsSensor(data)]
    entities += [EmbyLibrarySensor(data, lib) for lib in (data.libraries.data or {}).values()]
    async_add_entities(entities)


class EmbyServerStatusSensor(EmbyServerEntity, SensorEntity):
    """Running, Restarting, Shutting down, or Unreachable."""

    _attr_name = "Server Status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS
    _attr_translation_key = "server_status"

    def __init__(self, data) -> None:
        super().__init__(data, data.sessions, "server-status")
        self._event_state: str | None = None
        self._seen_down = False
        self._event_at = dt_util.utcnow()

    @property
    def available(self) -> bool:
        return True  # "Unreachable" is a state, not unavailability

    @property
    def native_value(self) -> str:
        if self._event_state:
            return self._event_state
        return STATUS_RUNNING if self.coordinator.last_update_success else STATUS_UNREACHABLE

    @property
    def icon(self) -> str:
        return "mdi:server-network" if self.native_value == STATUS_RUNNING else "mdi:server-network-off"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.client.add_message_listener("ServerRestarting", self._on_event))
        self.async_on_remove(self.client.add_message_listener("ServerShuttingDown", self._on_event))

    @callback
    def _on_event(self, message: dict) -> None:
        self._seen_down = False
        self._event_at = dt_util.utcnow()
        self._event_state = STATUS_RESTARTING if message.get("MessageType") == "ServerRestarting" else STATUS_SHUTTING_DOWN
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        # Clear "Restarting"/"Shutting down" once the server has been seen
        # down and is answering again, or after 10 minutes as a safety net.
        if self._event_state:
            if not self.coordinator.last_update_success:
                self._seen_down = True
            elif self._seen_down or dt_util.utcnow() - self._event_at > timedelta(minutes=10):
                self._event_state = None
        super()._handle_coordinator_update()


class EmbyActiveStreamsSensor(EmbyServerEntity, SensorEntity):
    _attr_name = "Active Streams"
    _attr_icon = "mdi:play-network"
    _attr_native_unit_of_measurement = "streams"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, data) -> None:
        super().__init__(data, data.sessions, "active-streams")

    @property
    def _playing(self) -> list[dict]:
        return [s for s in (self.coordinator.data or {}).get("sessions", []) if s.get("NowPlayingItem")]

    @property
    def native_value(self) -> int:
        return len(self._playing)

    @property
    def extra_state_attributes(self) -> dict:
        streams = []
        for sess in self._playing:
            item = sess["NowPlayingItem"]
            if item.get("Type") == "Episode":
                title = f"{item.get('SeriesName')} {_episode_label(item)}"
            elif item.get("ProductionYear"):
                title = f"{item.get('Name')} ({item['ProductionYear']})"
            else:
                title = item.get("Name")
            streams.append({"user": sess.get("UserName"), "device": sess.get("DeviceName"), "title": title})
        return {"active_streams": streams}


class EmbyLibrarySensor(EmbyServerEntity, SensorEntity):
    """Item count for one library. Empty libraries start disabled."""

    _attr_native_unit_of_measurement = "items"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, data, lib: dict) -> None:
        super().__init__(data, data.libraries, f"library-{lib['Id']}")
        self._lib_id = lib["Id"]
        self._lib_type = lib["Type"]
        self._attr_name = lib["Name"]
        self._attr_icon = LIBRARY_ICONS.get(self._lib_type, "mdi:folder-multiple")
        self._attr_entity_registry_enabled_default = lib.get("Count", 0) > 0

    @property
    def _lib(self) -> dict | None:
        return (self.coordinator.data or {}).get(self._lib_id)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._lib is not None

    @property
    def native_value(self) -> int | None:
        return self._lib["Count"] if self._lib else None

    @property
    def extra_state_attributes(self) -> dict:
        lib = self._lib or {}
        attrs: dict = {f"{t.lower()}_count": c for t, c in lib.get("Counts", {}).items()}
        latest = []
        for item in lib.get("Latest", []):
            if self._lib_type == "livetv":
                latest.append(f"{item['Name']}: {item['Program']}")
            elif item.get("Type") == "Episode":
                latest.append(f"{item.get('SeriesName', '')} {_episode_label(item)}".strip())
            elif item.get("ProductionYear"):
                latest.append(f"{item.get('Name')} ({item['ProductionYear']})")
            else:
                latest.append(item.get("Name", "Unknown"))
        attrs["latest" if self._lib_type != "livetv" else "channels"] = latest
        return attrs
