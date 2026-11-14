"""Emby libraries in Home Assistant's Media sidebar."""
from __future__ import annotations

from homeassistant.components.media_player import BrowseError, MediaClass
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .browse_media import build_item, build_root
from .const import DOMAIN
from .emby_client import CannotConnect


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    return EmbyMediaSource(hass)


def _to_source(media, entry_id: str) -> BrowseMediaSource:
    """Convert BrowseMedia (with '<entry>/<item>' IDs) to BrowseMediaSource."""
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=media.media_content_id,
        media_class=media.media_class,
        media_content_type=media.media_content_type,
        title=media.title,
        can_play=media.can_play,
        can_expand=media.can_expand,
        thumbnail=media.thumbnail,
        children_media_class=media.children_media_class,
        children=[_to_source(c, entry_id) for c in (media.children or [])],
    )


class EmbyMediaSource(MediaSource):
    """Browse and play Emby media in the HA frontend.

    Playback is transcoded to H.264/AAC HLS by Emby, so any browser can play it.
    """

    name = "Emby"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    def _entries(self):
        return [e for e in self.hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]

    def _client(self, entry_id: str):
        for entry in self._entries():
            if entry.entry_id == entry_id:
                return entry.runtime_data.client
        return None

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        entry_id, _, item_id = (item.identifier or "").partition("/")
        client = self._client(entry_id)
        if client is None or not item_id:
            raise Unresolvable("Emby server not available")
        try:
            details = await client.get_item(item_id)
        except CannotConnect as err:
            raise Unresolvable(f"Cannot reach Emby: {err}") from err
        if not details:
            raise Unresolvable("Emby item not found")
        url, mime = client.get_stream_url(item_id, "Audio" if details.get("MediaType") == "Audio" else "Video")
        return PlayMedia(url, mime)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        entries = self._entries()
        if not item.identifier:
            if len(entries) == 1:
                return await self._browse(entries[0].entry_id, "")
            return BrowseMediaSource(
                domain=DOMAIN, identifier="", media_class=MediaClass.DIRECTORY,
                media_content_type="library", title=self.name, can_play=False, can_expand=True,
                children_media_class=MediaClass.DIRECTORY,
                children=[
                    BrowseMediaSource(
                        domain=DOMAIN, identifier=f"{e.entry_id}/", media_class=MediaClass.DIRECTORY,
                        media_content_type="library", title=e.title, can_play=False, can_expand=True,
                    )
                    for e in entries
                ],
            )
        entry_id, _, item_id = item.identifier.partition("/")
        return await self._browse(entry_id, item_id)

    async def _browse(self, entry_id: str, item_id: str) -> BrowseMediaSource:
        client = self._client(entry_id)
        if client is None:
            raise BrowseError("Emby server not available")
        prefix = f"{entry_id}/"
        try:
            if not item_id:
                media = await build_root(client, prefix, root_id=prefix)
            else:
                media = await build_item(client, item_id, prefix)
        except CannotConnect as err:
            raise BrowseError(f"Cannot reach Emby: {err}") from err
        return _to_source(media, entry_id)
