"""Support for media browsing."""
from __future__ import annotations
from typing import Any
import logging
from homeassistant.components.media_player import BrowseError, BrowseMedia, MediaClass, MediaType
from .const import CONTENT_TYPE_MAP, MEDIA_CLASS_MAP, MEDIA_TYPE_NONE, SUPPORTED_COLLECTION_TYPES
from .emby_client import EmbyClient

_LOGGER = logging.getLogger(__name__)

# FIX: Ensure we use the official MediaType constants for playback compatibility
PLAYABLE_MEDIA_TYPES = [
    MediaType.EPISODE, 
    MediaType.MOVIE, 
    MediaType.MUSIC, 
    MediaType.TRACK, 
    MediaType.VIDEO, 
    MediaType.CHANNEL
]

async def async_browse_media(hass, client: EmbyClient, media_content_type: str | None, media_content_id: str | None) -> BrowseMedia:
    # Robust check for Root
    if media_content_id in [None, "", "media-source://emby_modern", "root"]:
        return await build_root_response(client)
    
    try:
        return await build_item_response(client, media_content_type, media_content_id)
    except Exception as err:
        _LOGGER.error("Error browsing media id '%s': %s", media_content_id, err)
        raise BrowseError(f"Error browsing media: {err}")

async def item_payload(client: EmbyClient, item: dict[str, Any]) -> BrowseMedia | None:
    try:
        title = item.get("Name", "Unknown")
        thumbnail = None
        
        # Try primary image, fall back to backdrop
        if item.get("ImageTags", {}).get("Primary"):
             thumbnail = client.get_artwork_url(item["Id"], "Primary", 600)
        elif item.get("ParentBackdropItemId"):
             thumbnail = client.get_artwork_url(item["ParentBackdropItemId"], "Backdrop", 600)

        media_content_id = item["Id"]
        emby_type = item.get("Type", "Unknown")
        
        # Map Emby types to HA types
        media_content_type = CONTENT_TYPE_MAP.get(emby_type, "library")
        media_class = MEDIA_CLASS_MAP.get(emby_type, MediaClass.DIRECTORY)
        
        can_play = bool(media_content_type in PLAYABLE_MEDIA_TYPES and media_content_id)
        
        # Logic to determine if it's a folder (expandable)
        can_expand = item.get("IsFolder", False) or emby_type in [
            "Series", "Season", "MusicAlbum", "BoxSet", "CollectionFolder", "UserView", "Folder"
        ]

        return BrowseMedia(
            title=title,
            media_content_id=media_content_id,
            media_content_type=media_content_type,
            media_class=media_class,
            can_play=can_play,
            can_expand=can_expand,
            children_media_class=None,
            thumbnail=thumbnail,
        )
    except Exception as e:
        # Log the specific item failure but return None so we don't crash the whole list
        _LOGGER.warning(f"Failed to parse item {item.get('Id', 'unknown')}: {e}")
        return None

async def build_root_response(client: EmbyClient) -> BrowseMedia:
    try:
        folders = await client.get_media_folders()
        children = []
        if "Items" in folders:
            for folder in folders["Items"]:
                payload = await item_payload(client, folder)
                if payload: children.append(payload)

        return BrowseMedia(
            media_content_id="",
            media_content_type="root",
            media_class=MediaClass.DIRECTORY,
            children_media_class=MediaClass.DIRECTORY,
            title=client.get_server_name(),
            can_play=False,
            can_expand=True,
            children=children,
        )
    except Exception as e:
         _LOGGER.error(f"Failed to build root response: {e}")
         raise BrowseError(f"Failed to build root: {e}")

async def build_item_response(client: EmbyClient, media_content_type: str | None, media_content_id: str) -> BrowseMedia:
    # 1. Get details of the folder/item we are clicking
    item_details = await client.get_item(media_content_id)
    if not item_details:
        raise BrowseError(f"Media item not found: {media_content_id}")

    title = item_details.get("Name", "Library")
    
    # Infer type if not provided
    if not media_content_type or media_content_type == "none":
        emby_type = item_details.get("Type", "Unknown")
        media_content_type = CONTENT_TYPE_MAP.get(emby_type, "library")

    thumbnail = None
    if item_details.get("ImageTags", {}).get("Primary"):
         thumbnail = client.get_artwork_url(media_content_id)

    # 2. Prepare params to fetch children
    # Default: Sort by Name
    params = {"ParentId": media_content_id, "SortBy": "SortName", "SortOrder": "Ascending"}
    
    # Special Case: TV Series should sort by Season/Episode (ParentIndex/Index)
    if item_details.get("Type") == "Series":
         params = {"ParentId": media_content_id} # Emby defaults to season order
    
    # 3. Fetch Children
    children_data = await client.get_items(params)
    children = []
    
    if children_data and "Items" in children_data:
        for child in children_data["Items"]:
            # FIX: Only append valid children. If item_payload fails (returns None), skip it.
            payload = await item_payload(client, child)
            if payload: 
                children.append(payload)

    return BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id=media_content_id,
        media_content_type=str(media_content_type),
        title=title,
        can_play=bool(media_content_type in PLAYABLE_MEDIA_TYPES),
        can_expand=True,
        children=children,
        thumbnail=thumbnail,
    )
    
