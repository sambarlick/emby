"""Diagnostics download for Emby Modern (secrets removed)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.core import HomeAssistant

TO_REDACT = {CONF_API_KEY, CONF_HOST, "LocalAddress", "LocalAddresses", "RemoteAddresses",
             "WanAddress", "MacAddress", "BroadcastAddress", "RemoteEndPoint", "IpAddress",
             "UserId", "UserName", "ProgramDataPath", "LogPath", "CachePath", "InternalMetadataPath",
             "TranscodingTempPath", "ItemsByNamePath", "WakeOnLanInfo"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    data = entry.runtime_data
    sessions = (data.sessions.data or {}).get("sessions", [])
    return async_redact_data({
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "system_info": (data.sessions.data or {}).get("system_info", {}),
        "sessions": [
            {k: s.get(k) for k in ("DeviceId", "DeviceName", "Client", "ApplicationVersion",
                                   "SupportsRemoteControl", "PlayState", "DeviceType")}
            | {"NowPlayingType": (s.get("NowPlayingItem") or {}).get("Type")}
            for s in sessions
        ],
        "libraries": [
            {k: lib.get(k) for k in ("Name", "Type", "Count", "Counts")}
            for lib in (data.libraries.data or {}).values()
        ],
        "release_check_ok": data.releases.last_update_success,
        "websocket_connected": data.client.ws_connected,
    }, TO_REDACT)
