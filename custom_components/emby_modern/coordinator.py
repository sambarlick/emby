"""Data update coordinator."""
from __future__ import annotations
import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .emby_client import EmbyClient
from homeassistant.core import callback # ADDED: Required for event handlers

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
            
            # 2. Process Libraries
            if folders and "Items" in folders:
                for item in folders["Items"]:
                    col_type = item.get("CollectionType", "unknown")
                    
                    # --- A. LIVE TV LOGIC ---
                    if col_type == "livetv":
                        # Fetch Channels with Current Program Info
                        channels_resp = await self.client.api_request(
                            "GET", 
                            "LiveTv/Channels", 
                            params={"Limit": 30, "EnableImages": "false"} 
                        )
                        
                        channel_data = []
                        if channels_resp and "Items" in channels_resp:
                            for ch in channels_resp["Items"]:
                                name = ch.get("Name", "Unknown")
                                # Try to get current program
                                prog = ch.get("CurrentProgram", {}).get("Name", "Off Air")
                                channel_data.append({"name": name, "program": prog})

                        libraries.append({
                            "Id": item["Id"],
                            "Name": item["Name"],
                            "Type": col_type,
                            "Count": channels_resp.get("TotalRecordCount", 0) if channels_resp else 0,
                            "LatestItems": channel_data 
                        })

                    # --- B. STANDARD MEDIA LOGIC (Movies, TV, etc) ---
                    else:
                        # Get Total Count
                        count_resp = await self.client.get_items(
                            params={
                                "ParentId": item["Id"], 
                                "Recursive": "true", 
                                "IncludeItemTypes": "Movie,Series,Episode,Audio,Video", 
                                "Limit": 0
                            }
                        )
                        
                        # Get Latest Items
                        latest_resp = await self.client.get_items(
                            params={
                                "ParentId": item["Id"], 
                                "Recursive": "true", 
                                "Limit": 5, 
                                "SortBy": "DateCreated", 
                                "SortOrder": "Descending", 
                                "IncludeItemTypes": "Movie,Series,Episode,Audio,Video"
                            }
                        )
                        
                        latest_items = []
                        if latest_resp and "Items" in latest_resp:
                            # FIX: Pass the full dictionary object so sensor.py can format it
                            latest_items = latest_resp["Items"]

                        libraries.append({
                            "Id": item["Id"],
                            "Name": item["Name"],
                            "Type": col_type,
                            "Count": count_resp.get("TotalRecordCount", 0),
                            "LatestItems": latest_items
                        })

            return {
                "sessions": sessions or [], 
                "libraries": libraries,
                "system_info": system_info or {}
            }
            
        except Exception as err:
            # IMPORTANT: Re-raising the error here allows the sensor/switch to mark the server as UNAVAILABLE
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def async_connect(self) -> None:
        await self.client.validate_connection()
        await self.async_config_entry_first_refresh()
        
    @callback
    def setup_global_listeners(self, courtesy_callback):
        """Register WebSocket listeners directly on the client for global events."""
        
        # This fixes the AttributeError from __init__.py by correctly calling the listener method
        # on the client object, which the coordinator manages.
        self.client.add_message_listener("ServerShuttingDown", courtesy_callback)
        self.client.add_message_listener("ServerRestarting", courtesy_callback)
