"""Data update coordinators for Emby Modern."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_COUNT_TYPES,
    EMBY_RELEASES_URL,
    LIBRARY_CHANGE_DEBOUNCE,
    LIBRARY_COUNT_TYPES,
    LIBRARY_SCAN_INTERVAL,
    SESSION_SCAN_INTERVAL,
    UPDATE_CHECK_INTERVAL,
)
from .emby_client import CannotConnect, EmbyClient, InvalidAuth

_LOGGER = logging.getLogger(__name__)


class EmbySessionCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Sessions and server info, polled every 10 s and pushed over the WebSocket."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: EmbyClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name="Emby sessions",
            update_interval=SESSION_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            sessions, system_info = await asyncio.gather(
                self.client.get_sessions(), self.client.get_system_info()
            )
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Emby rejected the API key") from err
        except CannotConnect as err:
            raise UpdateFailed(f"Cannot reach Emby: {err}") from err
        if not system_info:
            raise UpdateFailed("Emby returned no server info")
        return {"sessions": sessions, "system_info": system_info}

    @callback
    def handle_sessions_push(self, message: dict) -> None:
        """Apply a WebSocket 'Sessions' push.

        Updates listeners without resetting the poll timer, so server info
        keeps refreshing on schedule while pushes arrive.
        """
        sessions = message.get("Data")
        if not isinstance(sessions, list) or not self.data:
            return
        self.data = {**self.data, "sessions": sessions}
        self.async_update_listeners()


class EmbyLibraryCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Library counts. Refreshed hourly and shortly after Emby reports a change."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: EmbyClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name="Emby libraries",
            update_interval=LIBRARY_SCAN_INTERVAL,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=LIBRARY_CHANGE_DEBOUNCE, immediate=False
            ),
        )
        self.client = client
        self._semaphore = asyncio.Semaphore(3)

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            folders = await self.client.get_media_folders()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Emby rejected the API key") from err
        except CannotConnect as err:
            raise UpdateFailed(f"Cannot reach Emby: {err}") from err

        previous = self.data or {}
        items = folders.get("Items", [])
        results = await asyncio.gather(
            *(self._fetch_library(item) for item in items), return_exceptions=True
        )
        libraries: dict[str, dict] = {}
        for item, result in zip(items, results):
            if isinstance(result, dict):
                libraries[item["Id"]] = result
            else:
                _LOGGER.warning("Emby library %s failed to refresh: %s", item.get("Name"), result)
                if item["Id"] in previous:
                    # Keep the last good count rather than dropping to 0.
                    libraries[item["Id"]] = previous[item["Id"]]
        return libraries

    async def _fetch_library(self, item: dict) -> dict:
        async with self._semaphore:
            col_type = item.get("CollectionType")
            base = {"Id": item["Id"], "Name": item["Name"], "Type": col_type or "mixed"}

            if col_type == "livetv":
                channels = await self.client.get_live_tv_channels()
                return {
                    **base,
                    "Count": channels.get("TotalRecordCount", 0),
                    "Counts": {},
                    "Latest": [
                        {"Name": ch.get("Name", "Unknown"),
                         "Program": (ch.get("CurrentProgram") or {}).get("Name", "Off air")}
                        for ch in channels.get("Items", [])
                    ],
                }

            types = LIBRARY_COUNT_TYPES.get(col_type, DEFAULT_COUNT_TYPES)
            if col_type in LIBRARY_COUNT_TYPES:
                counts = {}
                for item_type in types:
                    resp = await self.client.get_items({
                        "ParentId": item["Id"], "Recursive": "true",
                        "IncludeItemTypes": item_type, "Limit": 0,
                    })
                    counts[item_type] = resp.get("TotalRecordCount", 0)
                count = counts[types[0]]
            else:
                resp = await self.client.get_items({
                    "ParentId": item["Id"], "Recursive": "true",
                    "IncludeItemTypes": ",".join(types), "Limit": 0,
                })
                counts = {}
                count = resp.get("TotalRecordCount", 0)

            latest_types = "Episode" if col_type == "tvshows" else ",".join(types)
            latest = await self.client.get_items({
                "ParentId": item["Id"], "Recursive": "true", "Limit": 5,
                "SortBy": "DateCreated", "SortOrder": "Descending",
                "IncludeItemTypes": latest_types,
            })
            return {**base, "Count": count, "Counts": counts, "Latest": latest.get("Items", [])}


class EmbyReleaseCoordinator(DataUpdateCoordinator[list[dict]]):
    """Emby Server releases from GitHub, used for the update entity."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name="Emby releases",
            update_interval=UPDATE_CHECK_INTERVAL,
        )

    async def _async_update_data(self) -> list[dict]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                EMBY_RELEASES_URL, params={"per_page": 20},
                headers={"Accept": "application/vnd.github+json"}, timeout=15,
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"GitHub returned {resp.status}")
                releases = await resp.json()
        except UpdateFailed:
            raise
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(f"Could not fetch Emby releases: {type(err).__name__}") from err
        return [
            {"version": r["tag_name"], "prerelease": r.get("prerelease", False),
             "url": r.get("html_url"), "notes": r.get("body") or ""}
            for r in releases if not r.get("draft")
        ]


@dataclass
class EmbyData:
    """Runtime data stored on the config entry."""

    client: EmbyClient
    sessions: EmbySessionCoordinator
    libraries: EmbyLibraryCoordinator
    releases: EmbyReleaseCoordinator
    unsubscribers: list = field(default_factory=list)
