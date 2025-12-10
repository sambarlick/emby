"""Data update coordinator."""
from __future__ import annotations
import logging
import asyncio
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .emby_client import EmbyClient
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

class EmbyDataUpdateCoordinator(DataUpdateCoordinator):
    """Emby Data Update Coordinator."""

    config_entry: ConfigEntry

    def __init__(self, hass, client: EmbyClient, entry: ConfigEntry) -> None:
        self.client = client
        self.entry = entry
        super().__init__(
            hass, _LOGGER, name="Emby Data", update_interval=timedelta(seconds=10),
        )

    async def _async_update_data(self):
        try:
            # 1. Fetch Basic Data
            sessions = await self.client.api_request("GET", "Sessions")
            system_info = await self.client.api_request("GET", "System/Info")
            
            libraries = []
            folders = await self.client.get_media_folders()
            
            # 2. Process Libraries (Parallelized)
            if folders and "Items" in folders:
                tasks = []
                for item in folders["Items"]:
                    tasks.append(self._process_library_item(item))
                
                results = await asyncio.gather(*tasks)
                libraries = [lib for lib in results if lib is not None]

            return {
                "sessions": sessions or [], 
                "libraries": libraries,
                "system_info": system_info or {}
            }
            
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def _process_library_item(self, item):
        """Helper to process a single library item."""
        try:
            col_type = item.get("CollectionType", "unknown")
            if col_type == "livetv":
                channels_resp = await self.client.api_request(
                    "GET", "LiveTv/Channels", params={"Limit": 30, "EnableImages": "false"} 
                )
                channel_data = []
                if channels_resp and "Items" in channels_resp:
                    for ch in channels_resp["Items"]:
                        name = ch.get("Name", "Unknown")
                        prog = ch.get("CurrentProgram", {}).get("Name", "Off Air")
                        channel_data.append({"name": name, "program": prog})

                return {
                    "Id": item["Id"], "Name": item["Name"], "Type": col_type,
                    "Count": channels_resp.get("TotalRecordCount", 0) if channels_resp else 0,
                    "LatestItems": channel_data 
                }
            else:
                count_resp = await self.client.get_items(
                    params={"ParentId": item["Id"], "Recursive": "true", "IncludeItemTypes": "Movie,Series,Episode,Audio,Video", "Limit": 0}
                )
                latest_resp = await self.client.get_items(
                    params={"ParentId": item["Id"], "Recursive": "true", "Limit": 5, "SortBy": "DateCreated", "SortOrder": "Descending", "IncludeItemTypes": "Movie,Series,Episode,Audio,Video"}
                )
                return {
                    "Id": item["Id"], "Name": item["Name"], "Type": col_type,
                    "Count": count_resp.get("TotalRecordCount", 0) if count_resp else 0,
                    "LatestItems": latest_resp.get("Items", []) if latest_resp else []
                }
        except Exception as e:
            _LOGGER.error(f"Error processing library {item.get('Name')}: {e}")
            return None

    async def async_connect(self) -> None:
        await self.client.validate_connection()
        await self.async_config_entry_first_refresh()
        
    @callback
    def setup_global_listeners(self, courtesy_callback):
        """Register WebSocket listeners directly on the client for global events."""
        self.client.add_message_listener("ServerShuttingDown", courtesy_callback)
        self.client.add_message_listener("ServerRestarting", courtesy_callback)
        
        # --- NEW: Instant Updates for Playback/Sessions ---
        @callback
        def _trigger_refresh(data):
            if not self._listeners: return
            self.hass.async_create_task(self.async_request_refresh())

        # FIX: Added 'Playstate' listener to catch immediate pause/resume events
        self.client.add_message_listener("Sessions", _trigger_refresh)
        self.client.add_message_listener("SessionData", _trigger_refresh)
        self.client.add_message_listener("Playstate", _trigger_refresh) 
        self.client.add_message_listener("UserDataChanged", _trigger_refresh)
