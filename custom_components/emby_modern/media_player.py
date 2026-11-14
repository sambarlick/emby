"""Emby client media players."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .browse_media import async_browse_media, parse_media_source_id
from .clients import selected_clients
from .emby_client import TICKS_PER_SECOND
from .entity import EmbyClientEntity

POSITION_DRIFT = 5  # seconds before a reported position counts as a jump

SUPPORTED = (
    MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.BROWSE_MEDIA | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP | MediaPlayerEntityFeature.TURN_OFF
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    data = entry.runtime_data
    async_add_entities(
        EmbyMediaPlayer(data, device_id, info["name"], info.get("app"))
        for device_id, info in selected_clients(hass, entry).items()
    )


class EmbyMediaPlayer(EmbyClientEntity, MediaPlayerEntity):
    """A selected Emby client. Shown as Off while it isn't connected."""

    _attr_name = None

    def __init__(self, data, device_id, device_name, app_name) -> None:
        super().__init__(data, device_id, device_name, app_name, key=None)
        self._app_name = (app_name or "").lower()
        self._device_name = (device_name or "").lower()
        self._position: float | None = None
        self._position_updated_at: datetime | None = None
        self._last_item: str | None = None
        self._last_paused: bool | None = None
        self._volume_override: tuple[float, datetime] | None = None

    # ---------------- state ----------------

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def _item(self) -> dict:
        return self.session.get("NowPlayingItem") or {}

    @property
    def _play_state(self) -> dict:
        return self.session.get("PlayState") or {}

    @property
    def state(self) -> MediaPlayerState:
        if not self.session:
            return MediaPlayerState.OFF
        if not self._item:
            return MediaPlayerState.IDLE
        return MediaPlayerState.PAUSED if self._play_state.get("IsPaused") else MediaPlayerState.PLAYING

    async def async_added_to_hass(self) -> None:
        self._update_position()
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_position()
        super()._handle_coordinator_update()

    def _update_position(self) -> None:
        """Track position the HA way: only store it when it jumps or play state changes."""
        ticks = self._play_state.get("PositionTicks")
        if ticks is None or not self._item:
            self._position = self._position_updated_at = None
            self._last_item = None
            return
        position = ticks / TICKS_PER_SECOND
        paused = bool(self._play_state.get("IsPaused"))
        now = dt_util.utcnow()
        expected = None
        if self._position is not None and self._position_updated_at and not self._last_paused:
            expected = self._position + (now - self._position_updated_at).total_seconds()
        elif self._position is not None:
            expected = self._position
        if (
            self._item.get("Id") != self._last_item
            or paused != self._last_paused
            or expected is None
            or abs(expected - position) > POSITION_DRIFT
        ):
            self._position, self._position_updated_at = position, now
        self._last_item, self._last_paused = self._item.get("Id"), paused

    @property
    def media_position(self) -> float | None:
        return self._position

    @property
    def media_position_updated_at(self) -> datetime | None:
        return self._position_updated_at

    @property
    def media_duration(self) -> float | None:
        ticks = self._item.get("RunTimeTicks")
        return ticks / TICKS_PER_SECOND if ticks else None

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Hide volume controls the client says it can't do."""
        commands = self.session.get("SupportedCommands")
        if not commands:
            return SUPPORTED
        features = SUPPORTED
        if "SetVolume" not in commands:
            features &= ~MediaPlayerEntityFeature.VOLUME_SET
        if "VolumeUp" not in commands:
            features &= ~MediaPlayerEntityFeature.VOLUME_STEP
        if "Mute" not in commands and "ToggleMute" not in commands:
            features &= ~MediaPlayerEntityFeature.VOLUME_MUTE
        return features

    @property
    def icon(self) -> str:
        client = (self.session.get("Client") or self._app_name).lower()
        device_type = str(self.session.get("DeviceType", "")).lower()
        name = self._device_name
        if any(x in client for x in ("tv", "roku", "kodi", "shield", "fire")) or "tv" in device_type or "tv" in name or "shield" in name:
            return "mdi:television"
        if any(x in client for x in ("ipad", "tablet")) or "tablet" in device_type or "ipad" in name:
            return "mdi:tablet"
        if any(x in client for x in ("web", "chrome", "firefox", "edge", "safari", "theater", "desktop")):
            return "mdi:monitor"
        if "xbox" in client:
            return "mdi:microsoft-xbox"
        if "playstation" in client or "ps4" in client or "ps5" in client:
            return "mdi:sony-playstation"
        if any(x in client for x in ("android", "ios", "iphone")):
            return "mdi:cellphone"
        return "mdi:play-box-multiple"

    @property
    def media_content_id(self) -> str | None:
        return self._item.get("Id")

    @property
    def media_content_type(self) -> MediaType | str | None:
        return {
            "Episode": MediaType.TVSHOW, "Movie": MediaType.MOVIE,
            "Audio": MediaType.MUSIC, "TvChannel": MediaType.CHANNEL,
        }.get(self._item.get("Type"), MediaType.VIDEO if self._item else None)

    @property
    def media_title(self) -> str | None:
        item = self._item
        title = item.get("Name")
        if item.get("Type") == "Episode":
            season, episode = item.get("ParentIndexNumber"), item.get("IndexNumber")
            if season is not None and episode is not None:
                return f"S{season:02d}:E{episode:02d} - {title}"
        if item.get("Type") == "Movie":
            year = item.get("ProductionYear") or (item.get("PremiereDate") or "")[:4]
            if year:
                return f"{title} ({year})"
        return title

    @property
    def media_series_title(self) -> str | None:
        return self._item.get("SeriesName")

    @property
    def media_artist(self) -> str | None:
        artists = self._item.get("Artists")
        return ", ".join(artists) if artists else None

    @property
    def media_album_name(self) -> str | None:
        return self._item.get("Album")

    @property
    def media_image_url(self) -> str | None:
        item = self._item
        if not item:
            return None
        image_id = item["Id"]
        if item.get("Type") == "Episode" and not item.get("ImageTags", {}).get("Primary") and item.get("SeriesId"):
            image_id = item["SeriesId"]
        return self.client.get_artwork_url(image_id)

    @property
    def volume_level(self) -> float | None:
        # Show a newly set volume straight away; clients take a few seconds to report it.
        if self._volume_override and (dt_util.utcnow() - self._volume_override[1]).total_seconds() < 5:
            return self._volume_override[0]
        level = self._play_state.get("VolumeLevel")
        return level / 100 if level is not None else None

    @property
    def is_volume_muted(self) -> bool | None:
        return self._play_state.get("IsMuted")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._item
        attrs: dict[str, Any] = {}
        if item.get("ParentIndexNumber") is not None:
            attrs["season_number"] = item["ParentIndexNumber"]
        if item.get("IndexNumber") is not None:
            attrs["episode_number"] = item["IndexNumber"]
        if self.session.get("UserName"):
            attrs["user"] = self.session["UserName"]
        return attrs

    # ---------------- commands ----------------

    def _require_session(self) -> str:
        if not self.session_id:
            raise HomeAssistantError(f"{self.device_info['name']} isn't connected to Emby")
        return self.session_id

    async def _playstate(self, command: str) -> None:
        await self.client.playstate(self._require_session(), command)
        await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        await self._playstate("Unpause")

    async def async_media_pause(self) -> None:
        await self._playstate("Pause")

    async def async_media_stop(self) -> None:
        await self._playstate("Stop")

    async def async_turn_off(self) -> None:
        """The power button stops playback; Emby can't switch a client off."""
        await self._playstate("Stop")

    async def async_media_next_track(self) -> None:
        await self._playstate("NextTrack")

    async def async_media_previous_track(self) -> None:
        await self._playstate("PreviousTrack")

    async def async_media_seek(self, position: float) -> None:
        await self.client.seek(self._require_session(), position)
        self._position, self._position_updated_at = position, dt_util.utcnow()
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        session_id = self._require_session()
        self._volume_override = (volume, dt_util.utcnow())
        self.async_write_ha_state()
        await self.client.general_command(session_id, "SetVolume", {"Volume": int(volume * 100)})

    async def async_volume_up(self) -> None:
        await self.client.general_command(self._require_session(), "VolumeUp")

    async def async_volume_down(self) -> None:
        await self.client.general_command(self._require_session(), "VolumeDown")

    async def async_mute_volume(self, mute: bool) -> None:
        await self.client.general_command(self._require_session(), "Mute" if mute else "Unmute")
        await self.coordinator.async_request_refresh()

    async def async_play_media(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> None:
        session_id = self._require_session()
        if media_source.is_media_source_id(media_id):
            parsed = parse_media_source_id(media_id)
            if parsed is None:
                raise HomeAssistantError("Only Emby media can be played on an Emby client")
            media_id = parsed[1]
        await self.client.play(session_id, media_id)
        await self.coordinator.async_request_refresh()

    async def async_browse_media(self, media_content_type=None, media_content_id=None) -> BrowseMedia:
        return await async_browse_media(
            self.hass, self.client, self.coordinator.config_entry.entry_id,
            media_content_type, media_content_id,
        )
