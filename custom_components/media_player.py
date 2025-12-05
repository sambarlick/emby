"""Support for Emby media players."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia, MediaPlayerEntity, MediaPlayerEntityFeature, MediaPlayerState, MediaType
)
from homeassistant.const import DEVICE_DEFAULT_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .browse_media import async_browse_media
from .const import IGNORED_CLIENTS
from .entity import EmbyEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: Any, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    added_ids = set()

    @callback
    def _async_update_media_players():
        sessions = coordinator.data.get("sessions", [])
        new_entities = []

        for session in sessions:
            if session.get("Client") in IGNORED_CLIENTS: continue
            if not session.get("SupportsRemoteControl", False): continue

            device_id = session.get("DeviceId") or session.get("Id")
            
            if device_id and device_id not in added_ids:
                device_name = session.get("DeviceName") or DEVICE_DEFAULT_NAME
                client_name = session.get("Client")
                version = session.get("ApplicationVersion")
                
                entity = EmbyMediaPlayer(coordinator, device_id, device_name, client_name, version)
                new_entities.append(entity)
                added_ids.add(device_id)
        
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_update_media_players))
    _async_update_media_players()


class EmbyMediaPlayer(EmbyEntity, MediaPlayerEntity):
    """Emby Media Player."""
    _attr_name = None 

    def __init__(self, coordinator, device_id, device_name, client_name, version):
        super().__init__(coordinator, device_id, device_name, client_name, version)
        self.session_id = None
        self._local_device_name = device_name

    @property
    def icon(self):
        """Dynamic icon based on device type or client name."""
        device_type = str(self.session_data.get("DeviceType", "")).lower()
        client = str(self.session_data.get("Client", "")).lower()
        d_name = (self._local_device_name or "").lower()
        
        if any(x in client for x in ["android", "ios", "iphone", "ipad", "mobile"]) or \
           any(x in device_type for x in ["mobile", "phone", "tablet", "ipad"]):
            if "tablet" in device_type or "ipad" in client or "galaxy tab" in d_name:
                 return "mdi:tablet"
            return "mdi:cellphone"
        if any(x in client for x in ["tv", "roku", "kodi", "lg", "samsung"]) or "tv" in device_type:
            return "mdi:television"
        if any(x in client for x in ["web", "chrome", "firefox", "edge", "browser"]) or "desktop" in device_type:
            return "mdi:monitor"
        if "xbox" in client or "xbox" in device_type:
            return "mdi:microsoft-xbox"
        if "ps4" in client or "ps5" in client or "playstation" in device_type:
            return "mdi:sony-playstation"
            
        return "mdi:play-box-multiple"

    @property
    def session_data(self) -> dict:
        for s in self.coordinator.data.get("sessions", []):
            if s.get("DeviceId") == self._device_id or s.get("Id") == self._device_id:
                self.session_id = s.get("Id")
                return s
        return {}

    @property
    def available(self) -> bool:
        return bool(self.session_data) and self.coordinator.last_update_success

    @property
    def state(self) -> MediaPlayerState | None:
        data = self.session_data
        if not data: return MediaPlayerState.OFF
        if data.get("PlayState", {}).get("IsPaused"): return MediaPlayerState.PAUSED
        if "NowPlayingItem" in data: return MediaPlayerState.PLAYING
        return MediaPlayerState.IDLE

    @property
    def media_content_type(self) -> MediaType | str | None:
        """Return the content type. This triggers the correct UI layout."""
        item = self.session_data.get("NowPlayingItem", {})
        m_type = item.get("Type")
        
        if m_type == "Episode":
            return MediaType.TVSHOW
        if m_type == "Movie":
            return MediaType.MOVIE
        if m_type == "Audio":
            return MediaType.MUSIC
        if m_type == "TvChannel":
            return MediaType.CHANNEL
            
        return MediaType.VIDEO

    @property
    def media_title(self):
        """Return the title of current playing media."""
        item = self.session_data.get("NowPlayingItem", {})
        title = item.get("Name")

        # FIX: Handle Episodes (SxxExx Title)
        if item.get("Type") == "Episode":
            s = item.get("ParentIndexNumber")
            e = item.get("IndexNumber")
            if s is not None and e is not None:
                return f"S{s:02d}E{e:02d} {title}"

        # FIX: Handle Movies (Title (Year))
        if item.get("Type") == "Movie":
            year = item.get("ProductionYear")
            if year is None:
                premiere_date = item.get("PremiereDate", "")
                if premiere_date and len(premiere_date) >= 4:
                    year = premiere_date[:4]
            
            if year:
                return f"{title} ({year})"
        
        return title

    @property
    def media_series_title(self):
        """Return the title of the series (TV)."""
        return self.session_data.get("NowPlayingItem", {}).get("SeriesName")

    @property
    def media_season(self):
        """Return None to prevent UI duplication on secondary line."""
        return None

    @property
    def media_episode(self):
        """Return None to prevent UI duplication on secondary line."""
        return None

    @property
    def extra_state_attributes(self):
        """Expose season/episode as attributes for automations."""
        item = self.session_data.get("NowPlayingItem", {})
        attrs = {}
        if item.get("ParentIndexNumber") is not None:
            attrs["season_number"] = item.get("ParentIndexNumber")
        if item.get("IndexNumber") is not None:
            attrs["episode_number"] = item.get("IndexNumber")
        return attrs

    @property
    def media_content_id(self): return self.session_data.get("NowPlayingItem", {}).get("Id")
    
    @property
    def media_image_url(self):
        item = self.session_data.get("NowPlayingItem")
        if item: return self.coordinator.client.get_artwork_url(item["Id"])
        return None

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        return (
            MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.PREVIOUS_TRACK |
            MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.STOP |
            MediaPlayerEntityFeature.SEEK | MediaPlayerEntityFeature.PLAY |
            MediaPlayerEntityFeature.BROWSE_MEDIA | MediaPlayerEntityFeature.PLAY_MEDIA
        )

    async def _send(self, cmd, params=None):
        if self.session_id: 
            await self.coordinator.client.api_request("POST", f"Sessions/{self.session_id}/Playing/{cmd}", params=params)
        await self.coordinator.async_request_refresh()

    async def async_media_play(self):
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()
        await self._send("Unpause")

    async def async_media_pause(self):
        self._attr_state = MediaPlayerState.PAUSED
        self.async_write_ha_state()
        await self._send("Pause")

    async def async_media_stop(self):
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()
        await self._send("Stop")

    async def async_media_next_track(self): await self._send("NextTrack")
    async def async_media_previous_track(self): await self._send("PreviousTrack")
    
    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        if self.session_id:
            self._attr_state = MediaPlayerState.PLAYING
            self.async_write_ha_state()
            await self.coordinator.client.api_request("POST", f"Sessions/{self.session_id}/Playing", params={"ItemIds": media_id, "PlayCommand": "PlayNow"})
            await self.coordinator.async_request_refresh()

    async def async_browse_media(self, media_content_type=None, media_content_id=None) -> BrowseMedia:
        return await async_browse_media(self.hass, self.coordinator.client, media_content_type, media_content_id)
        
