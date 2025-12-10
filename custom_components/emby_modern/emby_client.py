import logging
import asyncio
import json
import aiohttp
from typing import Any, Callable
from aiohttp import ClientSession, ClientError, ClientTimeout, WSMsgType

_LOGGER = logging.getLogger(__name__)

class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

class InvalidAuth(Exception):
    """Error to indicate there is invalid authentication."""

class EmbyClient:
    """Wrapper for Emby API."""

    def __init__(self, host, port, api_key, ssl, loop=None, session: ClientSession | None = None):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.ssl = ssl
        self._session = session
        self._server_name = None
        self._user_id = None 
        
        protocol = "https" if ssl else "http"
        self._url = f"{protocol}://{host}:{port}"
        
        # WebSocket Variables
        self._ws_url = f"{'wss' if ssl else 'ws'}://{host}:{port}/embywebsocket?api_key={api_key}&deviceId=homeassistant"
        self._ws = None
        self._listeners = {} # { "EventName": [callback_function] }
        # Store loop if provided, otherwise use running loop
        self._loop = loop or asyncio.get_running_loop()
        self._ws_task = None

    async def validate_connection(self) -> dict:
        """Validate connection and get System Info."""
        if self._session is None:
             raise CannotConnect("No aiohttp session provided.")

        try:
            info = await self.get_system_info()
            self._server_name = info.get("ServerName", "Emby Server")
            server_id = info.get("Id") 
            await self._find_user_id()
            
            # Start WebSocket connection in background if validated
            if not self._ws_task:
                self._ws_task = self._loop.create_task(self._websocket_loop())

            return {
                "title": self._server_name,
                "unique_id": server_id
            }
        except InvalidAuth:
            raise
        except Exception as err:
            raise CannotConnect(f"Connection check failed: {err}")

    async def _find_user_id(self):
        """Find a valid Admin/User ID to use for queries."""
        try:
            sessions = await self.api_request("GET", "Sessions")
            if sessions:
                for sess in sessions:
                    if "UserId" in sess:
                        self._user_id = sess["UserId"]
                        return

            if not self._user_id:
                users = await self.api_request("GET", "Users", params={"IsHidden": "true"})
                if users and "Items" in users and len(users["Items"]) > 0:
                    self._user_id = users["Items"][0]["Id"]
        except Exception:
            pass # Non-critical if user ID finding fails initially

    async def api_request(self, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> Any:
        headers = {"X-Emby-Token": self.api_key, "Accept": "application/json"}
        url = f"{self._url}/{endpoint}"
        try:
            async with self._session.request(
                method, url, headers=headers, params=params, json=json_data, timeout=ClientTimeout(total=10)
            ) as resp:
                if resp.status == 401: raise InvalidAuth("Invalid API Key")
                if resp.status == 204: return None
                
                if resp.status >= 400:
                    try:
                        error_text = await resp.text()
                    except:
                        error_text = ""
                    _LOGGER.error(f"Emby API Error {resp.status} on {endpoint}: {error_text}")
                    return None
                
                try:
                    return await resp.json()
                except Exception:
                    return None
                    
        except ClientError as err:
            raise CannotConnect(f"Connection error: {err}")

    # --- API Methods ---

    async def get_system_info(self) -> dict:
        return await self.api_request("GET", "System/Info") or {}

    async def get_media_folders(self) -> dict:
        if not self._user_id: await self._find_user_id()
        if not self._user_id: return {}
        return await self.api_request("GET", f"Users/{self._user_id}/Views")

    async def get_items(self, params: dict) -> dict:
        if not self._user_id: await self._find_user_id()
        if not self._user_id: return {}
        return await self.api_request("GET", f"Users/{self._user_id}/Items", params=params)

    def get_artwork_url(self, item_id: str, type: str = "Primary", max_width: int = 400) -> str:
        return f"{self._url}/Items/{item_id}/Images/{type}?maxHeight={max_width}&Quality=90"

    def get_server_name(self): 
        return self._server_name or "Emby Server"

    def get_server_url(self):
        return self._url

    # --- WebSocket Handling ---

    def add_message_listener(self, event_name: str, callback: Callable):
        """Register a callback for a specific WebSocket event."""
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)

    async def close(self):
        """Close the WebSocket connection and cancel the task."""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
            
        self._listeners = {} # Clear refs
        _LOGGER.debug("Emby Client closed")

    async def _websocket_loop(self):
        """Maintain WebSocket connection."""
        while True:
            try:
                async with self._session.ws_connect(self._ws_url, heartbeat=30) as ws:
                    self._ws = ws
                    _LOGGER.debug("Connected to Emby WebSocket")
                    
                    # Send identification
                    await ws.send_json({"MessageType": "SessionsStart", "Data": "1000,1000"})
                    
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            try:
                                data = msg.json()
                                msg_type = data.get("MessageType")
                                
                                # 1. Notify listeners for specific events
                                if msg_type in self._listeners:
                                    for listener in self._listeners[msg_type]:
                                        try:
                                            listener(data)
                                        except Exception as e:
                                            _LOGGER.error(f"Error in listener for {msg_type}: {e}")
                                            
                                # 2. Map generic 'Event' type messages (common in Emby)
                                if msg_type == "Package" or msg_type == "ScheduledTasksInfo":
                                    pass # Placeholder for future event handling
                                    
                            except ValueError:
                                pass
                        elif msg.type == WSMsgType.ERROR:
                            break
            except Exception as e:
                _LOGGER.debug(f"WebSocket connection lost: {e}")
                
            # Reconnect delay
            await asyncio.sleep(10)
