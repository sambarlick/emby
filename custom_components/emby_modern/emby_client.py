import logging
from typing import Any
from aiohttp import ClientSession, ClientError, ClientTimeout

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

    async def validate_connection(self) -> dict:
        """Validate connection and get System Info."""
        if self._session is None:
             raise CannotConnect("No aiohttp session provided.")

        try:
            # 1. Get System Info
            info = await self.get_system_info()
            self._server_name = info.get("ServerName", "Emby Server")
            server_id = info.get("Id") 

            # 2. Find User ID (Required for libraries/media)
            await self._find_user_id()

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
        # Try to find a user via Sessions first
        sessions = await self.api_request("GET", "Sessions")
        if sessions:
            for sess in sessions:
                if "UserId" in sess:
                    self._user_id = sess["UserId"]
                    return

        # Fallback to Users list
        if not self._user_id:
            users = await self.api_request("GET", "Users", params={"IsHidden": "true"})
            if users and "Items" in users and len(users["Items"]) > 0:
                self._user_id = users["Items"][0]["Id"]

    async def api_request(self, method: str, endpoint: str, params: dict = None) -> Any:
        headers = {"X-Emby-Token": self.api_key, "Accept": "application/json"}
        url = f"{self._url}/{endpoint}"
        try:
            async with self._session.request(
                method, url, headers=headers, params=params, timeout=ClientTimeout(total=10)
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
        """Get the full system info response."""
        return await self.api_request("GET", "System/Info") or {}

    # Restored: Used by your Coordinator
    async def get_media_folders(self) -> dict:
        """Get the top-level views (libraries)."""
        if not self._user_id: await self._find_user_id()
        if not self._user_id: return {}
        # Returns the full dict so your coordinator's 'if "Items" in folders' check works
        return await self.api_request("GET", f"Users/{self._user_id}/Views")

    # Restored: Used by your Coordinator
    async def get_items(self, params: dict) -> dict:
        """Generic item fetcher."""
        if not self._user_id: await self._find_user_id()
        if not self._user_id: return {}
        return await self.api_request("GET", f"Users/{self._user_id}/Items", params=params)

    # Used by media_player.py
    def get_artwork_url(self, item_id: str, type: str = "Primary", max_width: int = 400) -> str:
        return f"{self._url}/Items/{item_id}/Images/{type}?maxHeight={max_width}&Quality=90"

    # Used by sensor.py
    def get_server_name(self): 
        return self._server_name or "Emby Server"

    # RESTORED: Used by __init__.py (this was the missing piece)
    def get_server_url(self):
        return self._url
