"""Browsing Emby libraries, for media players and the Media sidebar."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import BrowseError, BrowseMedia, MediaClass, MediaType
from homeassistant.core import HomeAssistant

from .const import CONTENT_TYPE_MAP, DOMAIN, EXPANDABLE_TYPES, MEDIA_CLASS_MAP, PLAYABLE_TYPES
from .emby_client import CannotConnect, EmbyClient

_LOGGER = logging.getLogger(__name__)

MAX_CHILDREN = 1000
MEDIA_SOURCE_PREFIX = f"media-source://{DOMAIN}/"


def parse_media_source_id(media_id: str) -> tuple[str, str] | None:
    """media-source://emby_modern/<entry_id>/<item_id> -> (entry_id, item_id)."""
    if not media_id.startswith(MEDIA_SOURCE_PREFIX):
        return None
    parts = media_id[len(MEDIA_SOURCE_PREFIX):].split("/", 1)
    return (parts[0], parts[1]) if len(parts) == 2 and parts[1] else None


def _thumbnail(client: EmbyClient, item: dict) -> str | None:
    if item.get("ImageTags", {}).get("Primary"):
        return client.get_artwork_url(item["Id"], "Primary", 600)
    if item.get("SeriesId") and item.get("Type") in ("Season", "Episode"):
        return client.get_artwork_url(item["SeriesId"], "Primary", 600)
    if item.get("ParentBackdropItemId"):
        return client.get_artwork_url(item["ParentBackdropItemId"], "Backdrop", 600)
    return None


def _title(item: dict) -> str:
    name = item.get("Name", "Unknown")
    if item.get("Type") == "Episode" and item.get("IndexNumber") is not None:
        return f"E{item['IndexNumber']:02d} - {name}"
    if item.get("Type") == "Movie" and item.get("ProductionYear"):
        return f"{name} ({item['ProductionYear']})"
    return name


def item_payload(client: EmbyClient, item: dict, id_prefix: str = "") -> BrowseMedia:
    emby_type = item.get("Type", "Folder")
    return BrowseMedia(
        title=_title(item),
        media_content_id=f"{id_prefix}{item['Id']}",
        media_content_type=CONTENT_TYPE_MAP.get(emby_type, "library"),
        media_class=MEDIA_CLASS_MAP.get(emby_type, MediaClass.DIRECTORY),
        can_play=emby_type in PLAYABLE_TYPES,
        can_expand=item.get("IsFolder", False) or emby_type in EXPANDABLE_TYPES,
        thumbnail=_thumbnail(client, item),
    )


async def build_root(client: EmbyClient, id_prefix: str = "", root_id: str = "") -> BrowseMedia:
    folders = await client.get_media_folders()
    children = [item_payload(client, f, id_prefix) for f in folders.get("Items", [])]
    return BrowseMedia(
        title=client.get_server_name(), media_content_id=root_id, media_content_type="library",
        media_class=MediaClass.DIRECTORY, children_media_class=MediaClass.DIRECTORY,
        can_play=False, can_expand=True, children=children,
    )


async def build_item(client: EmbyClient, item_id: str, id_prefix: str = "") -> BrowseMedia:
    item = await client.get_item(item_id)
    if not item:
        raise BrowseError(f"Emby item not found: {item_id}")
    params: dict[str, Any] = {"ParentId": item_id, "Limit": MAX_CHILDREN, "Fields": "PrimaryImageAspectRatio,ProductionYear"}
    if item.get("Type") not in ("Series", "Season", "MusicAlbum", "Playlist", "BoxSet"):
        params.update({"SortBy": "SortName", "SortOrder": "Ascending"})
    children_data = await client.get_items(params)
    children = [item_payload(client, c, id_prefix) for c in children_data.get("Items", [])]
    payload = item_payload(client, item, id_prefix)
    payload.children = children
    payload.can_expand = True
    return payload


async def async_browse_media(
    hass: HomeAssistant, client: EmbyClient, entry_id: str,
    media_content_type: str | None, media_content_id: str | None,
) -> BrowseMedia:
    """Browse for a media player: Emby item IDs, plus a link to the Media sidebar."""
    try:
        if media_content_id in (None, "", "root"):
            return await build_root(client)
        parsed = parse_media_source_id(media_content_id)
        return await build_item(client, parsed[1] if parsed else media_content_id)
    except CannotConnect as err:
        raise BrowseError(f"Cannot reach Emby: {err}") from err
