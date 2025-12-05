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
            info = await self.api_request("GET", "System/Info")
            self._server_name = info.get("ServerName", "Emby Server")
            # CAPTURE THE ID HERE
            self._system_id = info.get("Id") 

            # 2. Find User ID
            sessions = await self.api_request("GET", "Sessions")
            if sessions:
                for sess in sessions:
                    if "UserId" in sess:
                        self._user_id = sess["UserId"]
                        break
            
            if not self._user_id:
                users = await self.api_request("GET", "Users", params={"IsHidden": "true"})
                if users and "Items" in users and len(users["Items"]) > 0:
                    self._user_id = users["Items"][0]["Id"]

            # Return a dict with both the name (for display) and ID (for config)
            return {
                "title": self._server_name,
                "unique_id": self._system_id
            }

        except InvalidAuth:
            raise
        except Exception as err:
            raise CannotConnect(f"Connection check failed: {err}")
            
   
    async def api_request(self, method: str, endpoint: str, params: dict = None) -> Any:
        headers = {"X-Emby-Token": self.api_key, "Accept": "application/json"}
        url = f"{self._url}/{endpoint}"
        try:
            async with self._session.request(
                method, url, headers=headers, params=params, timeout=ClientTimeout(total=10)
            ) as resp:
                if resp.status == 401: raise InvalidAuth("Invalid API Key")
                
                # FIX: Handle 204 No Content as success
                if resp.status == 204:
                    return None
                
                if resp.status >= 400:
                    try:
                        error_text = await resp.text()
                    except:
                        error_text = ""
                    raise CannotConnect(f"Error {resp.status}: {error_text}")
                
                # Only try to parse JSON if we have content
                try:
                    return await resp.json()
                except Exception:
                    return None
                    
        except ClientError as err:
            raise CannotConnect(f"Connection error: {err}")

    # --- API Methods ---

    # This is the method that was missing and causing the crash
    async def get_system_info(self) -> dict:
        """Get the full system info response."""
        return await self.api_request("GET", "System/Info")

    async def get_media_folders(self) -> dict:
        if not self._user_id: return {}
        return await self.api_request("GET", f"Users/{self._user_id}/Views")

    async def get_item(self, item_id: str) -> dict:
        if not self._user_id: return {}
        return await self.api_request("GET", f"Users/{self._user_id}/Items/{item_id}")

    async def get_items(self, params: dict) -> dict:
        if not self._user_id: return {}
        return await self.api_request("GET", f"Users/{self._user_id}/Items", params=params)

    def get_artwork_url(self, item_id: str, type: str = "Primary", max_width: int = 600) -> str:
        return f"{self._url}/Items/{item_id}/Images/{type}?maxHeight={max_width}&Quality=90"

    def get_server_name(self): return self._server_name or "Emby Server"
    def get_server_url(self):
        return self._url
