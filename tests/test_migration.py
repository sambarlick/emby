"""Upgrading from 1.2.x."""
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.emby_modern.const import CONF_CLIENTS, DOMAIN

from .conftest import ENTRY_DATA, SERVER_ID, setup


async def test_upgrade_keeps_devices_and_renames(hass, fake_emby):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERVER_ID, title="Sams-Server",
                            data=dict(ENTRY_DATA), version=1, minor_version=1)
    entry.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    server = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, SERVER_ID)}, name="Sams-Server")
    lounge = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "dev-lounge")},
                                         name="Lounge TV", model="AndroidTv")
    # Old-style entities, as v1.2.x created them
    ent_reg.async_get_or_create("button", DOMAIN, f"{SERVER_ID}-restart", config_entry=entry,
                                device_id=server.id, suggested_object_id="restart", original_name="Restart")
    ent_reg.async_get_or_create("media_player", DOMAIN, f"{SERVER_ID}-dev-lounge", config_entry=entry,
                                device_id=lounge.id, suggested_object_id=f"emby_modern_{SERVER_ID}_dev_lounge")
    ent_reg.async_get_or_create("remote", DOMAIN, "remote-sess-old", config_entry=entry, device_id=lounge.id)
    ent_reg.async_get_or_create("button", DOMAIN, "kill-sess-old", config_entry=entry, device_id=lounge.id)
    # A user-chosen ID that must be left alone
    ent_reg.async_get_or_create("sensor", DOMAIN, f"{SERVER_ID}-active-streams", config_entry=entry,
                                device_id=server.id, suggested_object_id="my_streams", original_name="Active Streams")

    await setup(hass, entry)

    assert entry.minor_version == 2
    assert set(entry.options[CONF_CLIENTS]) == {"dev-lounge"}
    assert ent_reg.async_get_entity_id("button", DOMAIN, f"{SERVER_ID}-restart") == "button.sams_server_restart"
    assert ent_reg.async_get_entity_id("media_player", DOMAIN, f"{SERVER_ID}-dev-lounge") == "media_player.lounge_tv"
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{SERVER_ID}-active-streams") == "sensor.my_streams"
    assert ent_reg.async_get_entity_id("remote", DOMAIN, "remote-sess-old") is None
    assert ent_reg.async_get_entity_id("button", DOMAIN, "kill-sess-old") is None
    assert hass.states.get("media_player.lounge_tv").state == "playing"
