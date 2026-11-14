"""Shared fixtures: a simulated Emby server."""
from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.emby_modern.const import CONF_CLIENTS, DOMAIN
from custom_components.emby_modern.emby_client import EmbyClient

SERVER_ID = "9b049fd8de1240f38c23d6c2259878c8"
ENTRY_DATA = {CONF_HOST: "192.168.8.101", CONF_PORT: 8096, CONF_API_KEY: "secret-key", CONF_SSL: False}

SYSTEM_INFO = {"Id": SERVER_ID, "ServerName": "Sams-Server", "Version": "4.10.2.0",
               "CanSelfUpdate": False, "HasUpdateAvailable": False, "HasPendingRestart": False,
               "SystemUpdateLevel": "Release", "LocalAddresses": ["192.168.8.101"]}

LOUNGE = {"Id": "sess-lounge-1", "DeviceId": "dev-lounge", "DeviceName": "Lounge TV", "Client": "AndroidTv",
          "SupportsRemoteControl": True, "UserName": "sam", "LastActivityDate": "2026-11-14T00:00:00Z",
          "NowPlayingItem": {"Id": "ep1", "Name": "The Curse", "Type": "Episode", "ParentIndexNumber": 13,
                             "IndexNumber": 5, "SeriesName": "The Curse of Oak Island", "SeriesId": "ser1",
                             "RunTimeTicks": 2_640_000_000_0},
          "PlayState": {"IsPaused": False, "PositionTicks": 600_000_000_0, "VolumeLevel": 40}}
FIREFOX = {"Id": "sess-ff", "DeviceId": "dev-firefox-1", "DeviceName": "Firefox", "Client": "Emby Web",
           "SupportsRemoteControl": True, "LastActivityDate": "2026-11-14T00:00:00Z"}
DEVICES = [
    {"Id": "1", "ReportedDeviceId": "dev-lounge", "Name": "Lounge TV", "AppName": "AndroidTv"},
    {"Id": "2", "ReportedDeviceId": "dev-shield", "Name": "Shield", "AppName": "AndroidTv", "DateLastActivity": "2026-11-10T00:00:00Z"},
]
VIEWS = {"Items": [
    {"Id": "lib-movies", "Name": "Movies", "CollectionType": "movies"},
    {"Id": "lib-tv", "Name": "TV Shows", "CollectionType": "tvshows"},
    {"Id": "lib-photos", "Name": "Photos", "CollectionType": "photos"},
]}
COUNTS = {("lib-movies", "Movie"): 661, ("lib-tv", "Series"): 412, ("lib-tv", "Episode"): 7124, ("lib-photos", "Photo"): 0}


class FakeEmby:
    """Answers EmbyClient.api_request calls by endpoint and records POSTs."""

    def __init__(self) -> None:
        self.sessions = [copy.deepcopy(LOUNGE), copy.deepcopy(FIREFOX)]
        self.system_info = dict(SYSTEM_INFO)
        self.devices = copy.deepcopy(DEVICES)
        self.calls: list[tuple] = []
        self.fail_library: str | None = None
        self.auth_fail = False

    async def api_request(self, client, method, endpoint, params=None, json_data=None):
        from custom_components.emby_modern.emby_client import InvalidAuth
        if self.auth_fail:
            raise InvalidAuth("bad key")
        if method != "GET":
            self.calls.append((method, endpoint, params, json_data))
            return None
        params = params or {}
        if endpoint == "System/Info":
            return self.system_info
        if endpoint == "Sessions":
            return copy.deepcopy(self.sessions)
        if endpoint == "Devices":
            return {"Items": self.devices}
        if endpoint == "Users/Query":
            return {"Items": [{"Id": "u1", "Policy": {"IsAdministrator": True}}]}
        if endpoint.endswith("/Views"):
            return VIEWS
        if endpoint.endswith("/Items") and params.get("Limit") == 0:
            if params["ParentId"] == self.fail_library:
                from custom_components.emby_modern.emby_client import CannotConnect
                raise CannotConnect("boom")
            return {"Items": [], "TotalRecordCount": COUNTS.get((params["ParentId"], params["IncludeItemTypes"]), 0)}
        if endpoint.endswith("/Items"):
            if params.get("ParentId") == "lib-movies" and params.get("Limit") == 5:
                return {"Items": [{"Id": "m1", "Name": "Alien", "Type": "Movie", "ProductionYear": 1979}]}
            if params.get("ParentId") == "lib-movies":
                return {"Items": [{"Id": "m1", "Name": "Alien", "Type": "Movie", "ProductionYear": 1979, "ImageTags": {"Primary": "x"}}]}
            return {"Items": []}
        if "/Items/" in endpoint:
            item_id = endpoint.rsplit("/", 1)[1]
            if item_id == "lib-movies":
                return {"Id": "lib-movies", "Name": "Movies", "Type": "CollectionFolder", "IsFolder": True}
            if item_id == "m1":
                return {"Id": "m1", "Name": "Alien", "Type": "Movie", "MediaType": "Video"}
            return None
        return None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def fake_emby():
    fake = FakeEmby()

    async def _api(self, method, endpoint, params=None, json_data=None):
        return await fake.api_request(self, method, endpoint, params, json_data)

    releases = [
        {"version": "4.10.3.0", "prerelease": False, "url": "https://example/4.10.3.0", "notes": "Fixes"},
        {"version": "4.11.0.1-beta", "prerelease": True, "url": "https://example/beta", "notes": "Beta"},
    ]
    with patch.object(EmbyClient, "api_request", _api), \
         patch.object(EmbyClient, "start_websocket", lambda self: None), \
         patch("custom_components.emby_modern.coordinator.EmbyReleaseCoordinator._async_update_data",
               AsyncMock(return_value=releases)):
        yield fake


@pytest.fixture
def entry(hass):
    e = MockConfigEntry(
        domain=DOMAIN, unique_id=SERVER_ID, title="Sams-Server", data=dict(ENTRY_DATA),
        options={CONF_CLIENTS: {"dev-lounge": {"name": "Lounge TV", "app": "AndroidTv"},
                                "dev-shield": {"name": "Shield", "app": "AndroidTv"}}},
        version=1, minor_version=2,
    )
    e.add_to_hass(hass)
    return e


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data
