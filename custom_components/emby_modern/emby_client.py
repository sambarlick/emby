"""Async client for the Emby Server REST API and WebSocket."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=10)
WS_RECONNECT_DELAY = 10
TICKS_PER_SECOND = 10_000_000


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid authentication."""


class EmbyClient:
    """Wrapper for the Emby API."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        ssl: bool,
        session: ClientSession | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key
        self.ssl = ssl
        self._session = session
        self._server_name: str | None = None
        self._user_id: str | None = None

        self._url = f"{'https' if ssl else 'http'}://{host}:{port}"
        self._ws_url = (
            f"{'wss' if ssl else 'ws'}://{host}:{port}/embywebsocket"
            f"?api_key={api_key}&deviceId=homeassistant"
        )
        self._ws = None
        self._ws_task: asyncio.Task | None = None
        self._listeners: dict[str, list[Callable[[dict], None]]] = {}

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def validate_connection(self) -> dict:
        """Check the server is reachable and the API key works.

        Raises CannotConnect or InvalidAuth. Does not start the WebSocket.
        """
        if self._session is None:
            raise CannotConnect("No aiohttp session provided")
        try:
            info = await self.get_system_info()
        except (InvalidAuth, CannotConnect):
            raise
        except TimeoutError as err:
            raise CannotConnect("Timed out connecting to Emby") from err
        if not info.get("Id"):
            raise CannotConnect("No server ID returned")
        self._server_name = info.get("ServerName", "Emby Server")
        await self._find_user_id()
        return {"title": self._server_name, "unique_id": info["Id"]}

    def start_websocket(self) -> None:
        """Start the background WebSocket connection (idempotent)."""
        if self._ws_task is None:
            self._ws_task = asyncio.get_running_loop().create_task(
                self._websocket_loop()
            )

    async def close(self) -> None:
        """Stop the WebSocket task and close the socket."""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass
            self._ws_task = None
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self._listeners.clear()

    async def _find_user_id(self) -> None:
        """Find a user ID to use for user-scoped queries (library, browse)."""
        try:
            users = await self.api_request("GET", "Users/Query", params={"IsDisabled": "false"})
            items = (users or {}).get("Items") if isinstance(users, dict) else users
            if items:
                admins = [u for u in items if u.get("Policy", {}).get("IsAdministrator")]
                self._user_id = (admins or items)[0]["Id"]
                return
            sessions = await self.api_request("GET", "Sessions")
            for sess in sessions or []:
                if sess.get("UserId"):
                    self._user_id = sess["UserId"]
                    return
        except (CannotConnect, InvalidAuth):
            raise
        except Exception:  # pylint: disable=broad-except
            _LOGGER.debug("Could not determine an Emby user ID")

    # ------------------------------------------------------------------
    # REST
    # ------------------------------------------------------------------

    async def api_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> Any:
        """Make an API request. Returns parsed JSON, or None on 204/4xx/5xx."""
        headers = {"X-Emby-Token": self.api_key, "Accept": "application/json"}
        url = f"{self._url}/{endpoint}"
        try:
            async with self._session.request(
                method, url, headers=headers, params=params, json=json_data,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 401:
                    raise InvalidAuth("Invalid API key")
                if resp.status in (204, 404):
                    return None
                if resp.status >= 400:
                    text = ""
                    try:
                        text = await resp.text()
                    except Exception:  # pylint: disable=broad-except
                        pass
                    _LOGGER.error("Emby API error %s on %s: %s", resp.status, endpoint, text[:200])
                    return None
                try:
                    return await resp.json(content_type=None)
                except Exception:  # pylint: disable=broad-except
                    return None
        except ClientError as err:
            raise CannotConnect(f"Connection error: {type(err).__name__}") from err
        except TimeoutError as err:
            raise CannotConnect("Request timed out") from err

    async def get_system_info(self) -> dict:
        return await self.api_request("GET", "System/Info") or {}

    async def get_sessions(self) -> list[dict]:
        return await self.api_request("GET", "Sessions") or []

    async def get_devices(self) -> list[dict]:
        """All devices Emby knows about (admin only)."""
        result = await self.api_request("GET", "Devices", params={"SortOrder": "Descending"})
        return (result or {}).get("Items", [])

    async def _user_path(self) -> str | None:
        if not self._user_id:
            await self._find_user_id()
        return f"Users/{self._user_id}" if self._user_id else None

    async def get_media_folders(self) -> dict:
        path = await self._user_path()
        return await self.api_request("GET", f"{path}/Views") or {} if path else {}

    async def get_items(self, params: dict) -> dict:
        path = await self._user_path()
        return await self.api_request("GET", f"{path}/Items", params=params) or {} if path else {}

    async def get_item(self, item_id: str) -> dict:
        path = await self._user_path()
        return await self.api_request("GET", f"{path}/Items/{item_id}") or {} if path else {}

    async def get_live_tv_channels(self, limit: int = 30) -> dict:
        await self._user_path()
        params = {"Limit": limit, "EnableImages": "false"}
        if self._user_id:
            params["UserId"] = self._user_id
        return await self.api_request("GET", "LiveTv/Channels", params=params) or {}

    async def restart(self) -> None:
        await self.api_request("POST", "System/Restart")

    async def shutdown(self) -> None:
        await self.api_request("POST", "System/Shutdown")

    async def scan_libraries(self) -> None:
        await self.api_request("POST", "Library/Refresh")

    async def send_message(self, session_id: str, header: str, text: str, timeout_ms: int) -> None:
        await self.api_request(
            "POST", f"Sessions/{session_id}/Message",
            params={"Header": header, "Text": text, "TimeoutMs": timeout_ms},
        )

    async def playstate(self, session_id: str, command: str, params: dict | None = None) -> None:
        await self.api_request("POST", f"Sessions/{session_id}/Playing/{command}", params=params)

    async def seek(self, session_id: str, position: float) -> None:
        await self.playstate(
            session_id, "Seek", {"SeekPositionTicks": int(position * TICKS_PER_SECOND)}
        )

    async def general_command(self, session_id: str, name: str, arguments: dict | None = None) -> None:
        body: dict[str, Any] = {"Name": name}
        if arguments:
            body["Arguments"] = arguments
        await self.api_request("POST", f"Sessions/{session_id}/Command", json_data=body)

    async def play(self, session_id: str, item_ids: str, command: str = "PlayNow") -> None:
        await self.api_request(
            "POST", f"Sessions/{session_id}/Playing",
            params={"ItemIds": item_ids, "PlayCommand": command},
        )

    # ------------------------------------------------------------------
    # URLs
    # ------------------------------------------------------------------

    def get_artwork_url(self, item_id: str, image_type: str = "Primary", max_height: int = 400) -> str:
        return f"{self._url}/Items/{item_id}/Images/{image_type}?maxHeight={max_height}&Quality=90"

    def get_stream_url(self, item_id: str, media_type: str) -> tuple[str, str]:
        """URL and MIME type a browser can play (transcoded where needed)."""
        if media_type == "Audio":
            query = urlencode({
                "api_key": self.api_key, "UserId": self._user_id or "",
                "DeviceId": "homeassistant", "Container": "mp3,aac,m4a,flac,webma,webm,wav,ogg",
                "TranscodingContainer": "mp3", "TranscodingProtocol": "http", "AudioCodec": "mp3",
            })
            return f"{self._url}/Audio/{item_id}/universal?{query}", "audio/mpeg"
        query = urlencode({
            "api_key": self.api_key, "MediaSourceId": item_id, "DeviceId": "homeassistant",
            "VideoCodec": "h264", "AudioCodec": "aac", "SegmentContainer": "ts",
            "MaxStreamingBitrate": 20_000_000,
        })
        return f"{self._url}/Videos/{item_id}/master.m3u8?{query}", "application/vnd.apple.mpegurl"

    def get_server_name(self) -> str:
        return self._server_name or "Emby Server"

    def get_server_url(self) -> str:
        return self._url

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    def add_message_listener(self, message_type: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        """Register a callback for a WebSocket MessageType. Returns an unsubscribe."""
        self._listeners.setdefault(message_type, []).append(callback)

        def _remove() -> None:
            if callback in self._listeners.get(message_type, []):
                self._listeners[message_type].remove(callback)

        return _remove

    async def _websocket_loop(self) -> None:
        """Maintain the WebSocket connection, reconnecting on failure."""
        while True:
            try:
                async with self._session.ws_connect(self._ws_url, heartbeat=30) as ws:
                    self._ws = ws
                    _LOGGER.debug("Connected to Emby WebSocket")
                    # Ask for session updates: first after 0 ms, then every 1500 ms.
                    await ws.send_json({"MessageType": "SessionsStart", "Data": "0,1500"})
                    async for msg in ws:
                        if msg.type == WSMsgType.TEXT:
                            try:
                                data = msg.json()
                            except ValueError:
                                continue
                            for listener in list(self._listeners.get(data.get("MessageType"), [])):
                                try:
                                    listener(data)
                                except Exception:  # pylint: disable=broad-except
                                    _LOGGER.exception("Error in WebSocket listener")
                        elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSED):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:  # pylint: disable=broad-except
                # Log the type only: the URL in the message contains the API key.
                _LOGGER.debug("Emby WebSocket connection lost (%s)", type(err).__name__)
            self._ws = None
            await asyncio.sleep(WS_RECONNECT_DELAY)
