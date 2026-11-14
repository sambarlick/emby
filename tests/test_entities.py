"""Devices, entity names/IDs, defaults and behaviour."""
from datetime import timedelta
from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.emby_modern.const import CONF_CLIENTS, DOMAIN

from .conftest import setup


async def test_entities_and_ids(hass, entry, fake_emby):
    await setup(hass, entry)
    reg = er.async_get(hass)
    ids = {e.entity_id: e for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    expected = {
        "media_player.lounge_tv", "media_player.shield",
        "remote.lounge_tv_remote", "remote.shield_remote",
        "button.lounge_tv_stop_session", "button.shield_stop_session",
        "button.sams_server_restart", "button.sams_server_scan_library", "button.sams_server_shutdown",
        "switch.sams_server_shutdown_courtesy_mode", "sensor.sams_server_server_status",
        "sensor.sams_server_active_streams", "sensor.sams_server_movies",
        "sensor.sams_server_tv_shows", "sensor.sams_server_photos", "update.sams_server_update",
    }
    assert expected == set(ids), set(ids) ^ expected
    # Superfluous entities and empty libraries start disabled
    for eid in ("remote.lounge_tv_remote", "button.lounge_tv_stop_session",
                "button.sams_server_shutdown", "sensor.sams_server_photos"):
        assert ids[eid].disabled_by is er.RegistryEntryDisabler.INTEGRATION, eid
    # Firefox wasn't selected: no device, but a Repairs notice
    assert not any("firefox" in e for e in ids)
    issues = ir.async_get(hass).issues
    assert (DOMAIN, f"new_client_{entry.entry_id}_dev-firefox-1") in issues


async def test_media_player(hass, entry, fake_emby):
    await setup(hass, entry)
    st = hass.states.get("media_player.lounge_tv")
    assert st.state == "playing"
    assert st.attributes["friendly_name"] == "Lounge TV"
    assert st.attributes["media_title"] == "S13:E05 - The Curse"
    assert st.attributes["media_duration"] == 2640
    assert st.attributes["media_position"] == 600
    assert st.attributes["icon"] == "mdi:television"
    # Shield is selected but offline: Off, not unavailable
    assert hass.states.get("media_player.shield").state == "off"

    await hass.services.async_call("media_player", "media_seek",
        {"entity_id": "media_player.lounge_tv", "seek_position": 120}, blocking=True)
    assert ("POST", "Sessions/sess-lounge-1/Playing/Seek", {"SeekPositionTicks": 1_200_000_000}, None) in fake_emby.calls


async def test_library_counts(hass, entry, fake_emby):
    await setup(hass, entry)
    tv = hass.states.get("sensor.sams_server_tv_shows")
    assert tv.state == "412"  # series, not series + episodes
    assert tv.attributes["episode_count"] == 7124
    movies = hass.states.get("sensor.sams_server_movies")
    assert movies.state == "661" and movies.attributes["latest"] == ["Alien (1979)"]
    # A library that fails keeps its last count
    fake_emby.fail_library = "lib-movies"
    await entry.runtime_data.libraries.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sams_server_movies").state == "661"


async def test_sessions_push_does_not_postpone_poll(hass, entry, fake_emby):
    data = await setup(hass, entry)
    before = data.sessions._unsub_refresh
    data.sessions.handle_sessions_push({"MessageType": "Sessions", "Data": []})
    await hass.async_block_till_done()
    assert data.sessions._unsub_refresh is before  # timer untouched
    assert hass.states.get("media_player.lounge_tv").state == "off"


async def test_server_status_and_courtesy(hass, entry, fake_emby):
    data = await setup(hass, entry)
    await hass.services.async_call("switch", "turn_on",
        {"entity_id": "switch.sams_server_shutdown_courtesy_mode"}, blocking=True)
    for cb in list(data.client._listeners["ServerRestarting"]):
        cb({"MessageType": "ServerRestarting"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sams_server_server_status").state == "restarting"
    msgs = [c for c in fake_emby.calls if c[1].endswith("/Message")]
    assert {c[1] for c in msgs} == {"Sessions/sess-lounge-1/Message", "Sessions/sess-ff/Message"}


async def test_update_entity(hass, entry, fake_emby):
    await setup(hass, entry)
    st = hass.states.get("update.sams_server_update")
    assert st.state == "on"
    assert st.attributes["installed_version"] == "4.10.2.0"
    assert st.attributes["latest_version"] == "4.10.3.0"  # beta skipped on Release channel
    assert not st.attributes["supported_features"] & 1  # no Install: CanSelfUpdate false


async def test_repair_adds_client(hass, entry, fake_emby):
    await setup(hass, entry)
    from custom_components.emby_modern.repairs import async_create_fix_flow
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"new_client_{entry.entry_id}_dev-firefox-1")
    flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass
    await flow.async_step_confirm({})
    await hass.async_block_till_done()
    assert "dev-firefox-1" in entry.options[CONF_CLIENTS]
    assert hass.states.get("media_player.firefox") is not None


async def test_unselect_removes_device(hass, entry, fake_emby):
    await setup(hass, entry)
    hass.config_entries.async_update_entry(entry, options={CONF_CLIENTS: {"dev-lounge": {"name": "Lounge TV"}}})
    await hass.async_block_till_done()
    assert hass.states.get("media_player.shield") is None
    assert er.async_get(hass).async_get("media_player.shield") is None


async def test_browse_and_media_source(hass, entry, fake_emby):
    await setup(hass, entry)
    from homeassistant.components.media_player import async_process_play_media_url  # noqa: F401
    player = hass.data["entity_components"]["media_player"].get_entity("media_player.lounge_tv")
    root = await player.async_browse_media()
    assert [c.title for c in root.children] == ["Movies", "TV Shows", "Photos"]
    movies = await player.async_browse_media("library", "lib-movies")
    assert movies.children[0].title == "Alien (1979)" and movies.children[0].can_play

    from homeassistant.components.media_source import MediaSourceItem
    from custom_components.emby_modern.media_source import EmbyMediaSource
    src = EmbyMediaSource(hass)
    browse = await src.async_browse_media(MediaSourceItem(hass, DOMAIN, "", None))
    assert browse.children[0].identifier == f"{entry.entry_id}/lib-movies"
    play = await src.async_resolve_media(MediaSourceItem(hass, DOMAIN, f"{entry.entry_id}/m1", None))
    assert "/Videos/m1/master.m3u8" in play.url and play.mime_type == "application/vnd.apple.mpegurl"

    await hass.services.async_call("media_player", "play_media", {
        "entity_id": "media_player.lounge_tv", "media_content_type": "movie",
        "media_content_id": f"media-source://{DOMAIN}/{entry.entry_id}/m1"}, blocking=True)
    assert ("POST", "Sessions/sess-lounge-1/Playing", {"ItemIds": "m1", "PlayCommand": "PlayNow"}, None) in fake_emby.calls


async def test_diagnostics_redacts(hass, entry, fake_emby):
    await setup(hass, entry)
    from custom_components.emby_modern.diagnostics import async_get_config_entry_diagnostics
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    assert "secret-key" not in text and "192.168.8.101" not in text


async def test_unload_closes(hass, entry, fake_emby):
    data = await setup(hass, entry)
    with patch.object(type(data.client), "close") as close:
        assert await hass.config_entries.async_unload(entry.entry_id)
    close.assert_called_once()


async def test_library_changed_triggers_refresh(hass, entry, fake_emby):
    data = await setup(hass, entry)
    with patch.object(type(data.libraries), "async_request_refresh") as refresh:
        for cb in list(data.client._listeners["LibraryChanged"]):
            cb({"MessageType": "LibraryChanged", "Data": {}})
        await hass.async_block_till_done()
    refresh.assert_called_once()


async def test_websocket_dispatch(hass):
    from custom_components.emby_modern.emby_client import EmbyClient
    client = EmbyClient("h", 1, "k", False, session=None)
    got = []
    remove = client.add_message_listener("Sessions", got.append)
    for listener in client._listeners["Sessions"]:
        listener({"MessageType": "Sessions", "Data": []})
    remove()
    assert got and client._listeners["Sessions"] == []
