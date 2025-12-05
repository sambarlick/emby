"""Expose Emby as a media source."""
from __future__ import annotations
from homeassistant.components.media_player import BrowseMedia, MediaClass
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .browse_media import async_browse_media

async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    """Set up Emby media source."""
    return EmbyMediaSource(hass)

class EmbyMediaSource(MediaSource):
    """Provide Emby as a media source."""
    name = "Emby Modern"
    domain = DOMAIN

    def __init__(self, hass: HomeAssistant):
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a url."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise Unresolvable("No Emby server configured.")
        
        # Use the first available server
        entry = entries[0]
        coordinator = entry.runtime_data
        client = coordinator.client
        
        # 1. Fetch Item Details to determine Type (Audio vs Video)
        media_id = item.identifier
        item_details = await client.get_item(media_id)
        
        if not item_details:
             raise Unresolvable(f"Media item {media_id} not found.")

        media_type = item_details.get("Type", "Unknown")
        base_url = client.get_server_url()
        api_param = f"api_key={client.api_key}"
        
        # 2. Build URL based on type
        # We REMOVED 'static=true' to allow transcoding if needed
        if media_type in ["Audio", "MusicAudio"]:
            url = f"{base_url}/Audio/{media_id}/stream?{api_param}"
            mime = "audio/mpeg"
        elif media_type in ["Movie", "Episode", "Video", "TvChannel"]:
            url = f"{base_url}/Videos/{media_id}/stream?container=mp4&{api_param}"
            mime = "video/mp4"
        else:
             url = f"{base_url}/Items/{media_id}/Download?{api_param}"
             mime = "application/octet-stream"

        return PlayMedia(url, mime)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Return media."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise MediaSourceError("No Emby server configured.")
        
        entry = entries[0]
        coordinator = entry.runtime_data
        
        # Safe handling for Root
        media_content_id = item.identifier
        if not media_content_id:
            media_content_id = None
            
        return await async_browse_media(
            self.hass, 
            coordinator.client, 
            None, 
            media_content_id
  
        )
