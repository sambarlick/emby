"""Setup, reconfigure, reauth and the settings cog."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.emby_modern.const import CONF_CLIENTS, DOMAIN
from custom_components.emby_modern.emby_client import CannotConnect, EmbyClient, InvalidAuth

from .conftest import ENTRY_DATA, SERVER_ID, setup

NEW = {CONF_HOST: " http://192.168.8.50/ ", CONF_PORT: 8920, CONF_API_KEY: "", CONF_SSL: False}


async def test_user_flow_with_client_picker(hass, fake_emby):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.emby_modern.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(r["flow_id"],
            {CONF_HOST: "https://192.168.8.101/", CONF_PORT: 8096, CONF_API_KEY: "k", CONF_SSL: False})
        assert r["step_id"] == "clients"
        options = {o["value"]: o["label"] for o in r["data_schema"].schema[CONF_CLIENTS].config["options"]}
        # Active sessions plus offline devices from Emby's device list, no duplicates
        assert set(options) == {"dev-lounge", "dev-firefox-1", "dev-shield"}
        assert options["dev-shield"] == "Shield (AndroidTv), last seen 2026-11-10"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_CLIENTS: ["dev-lounge"]})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["title"] == "Sams-Server"
    assert r["data"][CONF_HOST] == "192.168.8.101" and r["data"][CONF_SSL] is True
    assert r["options"] == {CONF_CLIENTS: {"dev-lounge": {"name": "Lounge TV", "app": "AndroidTv"}}}
    assert r["result"].unique_id == SERVER_ID


async def test_reconfigure_keeps_key(hass, entry, fake_emby):
    r = await entry.start_reconfigure_flow(hass)
    with patch("custom_components.emby_modern.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], NEW)
    assert r["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.8.50" and entry.data[CONF_API_KEY] == "secret-key"


async def test_reconfigure_wrong_server(hass, entry, fake_emby):
    fake_emby.system_info["Id"] = "other"
    r = await entry.start_reconfigure_flow(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], NEW)
    assert r["reason"] == "wrong_server" and entry.data == ENTRY_DATA


@pytest.mark.parametrize("exc,err", [(CannotConnect("x"), "cannot_connect"), (TimeoutError(), "cannot_connect"),
                                     (InvalidAuth("x"), "invalid_auth"), (ValueError(), "unknown")])
async def test_reconfigure_errors(hass, entry, fake_emby, exc, err):
    r = await entry.start_reconfigure_flow(hass)
    with patch.object(EmbyClient, "get_system_info", AsyncMock(side_effect=exc)):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], NEW)
    assert r["errors"] == {"base": err}


async def test_reauth(hass, entry, fake_emby):
    fake_emby.auth_fail = True
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"
    fake_emby.auth_fail = False
    with patch("custom_components.emby_modern.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {CONF_API_KEY: "new-key"})
    assert r["reason"] == "reauth_successful" and entry.data[CONF_API_KEY] == "new-key"


async def test_options_flow(hass, entry, fake_emby):
    await setup(hass, entry)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    defaults = r["data_schema"].schema
    r = await hass.config_entries.options.async_configure(r["flow_id"], {CONF_CLIENTS: ["dev-lounge", "dev-firefox-1"]})
    await hass.async_block_till_done()
    assert set(entry.options[CONF_CLIENTS]) == {"dev-lounge", "dev-firefox-1"}
    assert hass.states.get("media_player.firefox") is not None
    assert hass.states.get("media_player.shield") is None


async def test_picker_order(hass, entry, fake_emby):
    fake_emby.devices.append({"Id": "3", "ReportedDeviceId": "dev-old", "Name": "Old Phone", "AppName": "Emby", "DateLastActivity": "2026-01-01T00:00:00Z"})
    fake_emby.devices.append({"Id": "4", "ReportedDeviceId": "dev-new", "Name": "Aardvark", "AppName": "Emby", "DateLastActivity": "2026-11-12T00:00:00Z"})
    await setup(hass, entry)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    order = [o["value"] for o in r["data_schema"].schema[CONF_CLIENTS].config["options"]]
    # ticked A-Z, then connected now, then last seen newest first
    assert order == ["dev-lounge", "dev-shield", "dev-firefox-1", "dev-new", "dev-old"]
