"""Support for Emby media players."""
from .entity import EmbyEntity
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia, MediaPlayerEntity, MediaPlayerEntityFeature, MediaPlayerState, MediaType
)
# ... other imports remain unchanged ...

class EmbyMediaPlayer(EmbyEntity, MediaPlayerEntity):
# ... __init__ and properties remain unchanged ...

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        return (
            MediaPlayerEntityFeature.PAUSE | MediaPlayerEntityFeature.PREVIOUS_TRACK |
            MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.STOP |
            MediaPlayerEntityFeature.SEEK | MediaPlayerEntityFeature.PLAY |
            MediaPlayerEntityFeature.BROWSE_MEDIA | MediaPlayerEntityFeature.PLAY_MEDIA |
            # ADDED: Volume Controls
            MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_MUTE |
            MediaPlayerEntityFeature.VOLUME_STEP
        )

    # ADDED: Volume Properties
    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        play_state = self.session_data.get("PlayState", {})
        # Emby uses 0-100, HA needs 0.0-1.0
        if "VolumeLevel" in play_state:
            return play_state["VolumeLevel"] / 100
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        return self.session_data.get("PlayState", {}).get("IsMuted", False)

    # ADDED: Volume Methods
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        # Convert HA 0.0-1.0 back to Emby 0-100
        emby_vol = int(volume * 100)
        if self.session_id:
            await self.coordinator.client.api_request(
                "POST", 
                f"Sessions/{self.session_id}/Command/SetVolume",
                params={"Volume": emby_vol}
            )
            # Optimistic state update
            self.session_data.get("PlayState", {})["VolumeLevel"] = emby_vol
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        await self._send_command_to_session("VolumeUp")
        
    async def async_volume_down(self) -> None:
        """Volume down media player."""
        await self._send_command_to_session("VolumeDown")

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        command = "Mute" if mute else "Unmute"
        await self._send_command_to_session(command)
        
    async def _send_command_to_session(self, cmd):
        """Helper to send general commands to the session."""
        if self.session_id:
            await self.coordinator.client.api_request("POST", f"Sessions/{self.session_id}/Command/{cmd}")
        await self.coordinator.async_request_refresh()

    # NOTE: async_media_play, async_media_pause, async_media_stop, async_media_next_track, 
    # async_media_previous_track, async_play_media, async_browse_media remain unchanged.
