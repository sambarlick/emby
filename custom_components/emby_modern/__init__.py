"""The Emby Modern integration."""
from __future__ import annotations

import inspect
import logging
import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

from .clients import async_clear_client_issues, async_flag_new_clients, selected_clients
from .const import CONF_CLIENTS, DOMAIN
from .coordinator import EmbyData, EmbyLibraryCoordinator, EmbyReleaseCoordinator, EmbySessionCoordinator
from .emby_client import CannotConnect, EmbyClient, InvalidAuth
from .entity import server_device_id

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
SEND_MESSAGE_SCHEMA = vol.Schema({
    vol.Required("message"): cv.string,
    vol.Optional("header", default="Home Assistant Alert"): cv.string,
    vol.Optional("timeout_ms", default=5000): vol.All(vol.Coerce(int), vol.Range(min=1000, max=60000)),
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type EmbyConfigEntry = ConfigEntry[EmbyData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the send_message service."""

    async def send_message(call: ServiceCall) -> None:
        entries = [
            e for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
            and (ATTR_CONFIG_ENTRY_ID not in call.data or e.entry_id == call.data[ATTR_CONFIG_ENTRY_ID])
        ]
        if not entries:
            raise ServiceValidationError("No loaded Emby server matches")
        for entry in entries:
            data: EmbyData = entry.runtime_data
            for sess in (data.sessions.data or {}).get("sessions", []):
                if not sess.get("SupportsRemoteControl"):
                    continue
                try:
                    await data.client.send_message(
                        sess["Id"], call.data["header"], call.data["message"], call.data["timeout_ms"]
                    )
                except CannotConnect as err:
                    _LOGGER.warning("Couldn't message %s: %s", sess.get("DeviceName"), err)

    hass.services.async_register(DOMAIN, "send_message", send_message, schema=SEND_MESSAGE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EmbyConfigEntry) -> bool:
    client = EmbyClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_API_KEY], entry.data[CONF_SSL],
        session=async_get_clientsession(hass),
    )
    try:
        await client.validate_connection()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed("Emby rejected the API key") from err
    except CannotConnect as err:
        raise ConfigEntryNotReady(f"Emby not reachable: {err}") from err

    data = EmbyData(
        client=client,
        sessions=EmbySessionCoordinator(hass, entry, client),
        libraries=EmbyLibraryCoordinator(hass, entry, client),
        releases=EmbyReleaseCoordinator(hass, entry),
    )
    await data.sessions.async_config_entry_first_refresh()
    await data.libraries.async_config_entry_first_refresh()
    await data.releases.async_refresh()  # GitHub being down must not block setup
    entry.runtime_data = data

    _async_cleanup_registry(hass, entry)

    # The server device must exist before client devices reference it.
    _async_register_devices(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not entry.data.get("entity_ids_migrated"):
        _async_migrate_entity_ids(hass, entry)
        hass.config_entries.async_update_entry(entry, data={**entry.data, "entity_ids_migrated": True})

    # WebSocket: live session updates, and library refresh when media changes.
    client.add_message_listener("Sessions", data.sessions.handle_sessions_push)

    @callback
    def _library_changed(_message: dict) -> None:
        hass.async_create_task(data.libraries.async_request_refresh())

    client.add_message_listener("LibraryChanged", _library_changed)
    client.start_websocket()

    # Repairs notice for clients that connect but aren't selected.
    seen: set[str] = set()

    @callback
    def _check_new_clients() -> None:
        async_flag_new_clients(hass, entry, (data.sessions.data or {}).get("sessions", []), seen)

    async_clear_client_issues(hass, entry)
    _check_new_clients()
    entry.async_on_unload(data.sessions.async_add_listener(_check_new_clients))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: EmbyConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EmbyConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Stop the WebSocket so a reload (e.g. after reconfigure) doesn't leave
        # the old connection running.
        data = getattr(entry, "runtime_data", None)
        if data is not None:
            await data.client.close()
    return unload_ok


async def async_remove_config_entry_device(hass: HomeAssistant, entry: EmbyConfigEntry, device: dr.DeviceEntry) -> bool:
    """Allow deleting a client device from the UI; also deselects it."""
    server = server_device_id(entry)
    ids = {i[1] for i in device.identifiers if i[0] == DOMAIN}
    if server in ids:
        return False
    clients = {k: v for k, v in selected_clients(hass, entry).items() if k not in ids}
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_CLIENTS: clients})
    return True


# ----------------------------------------------------------------------
# Upgrades
# ----------------------------------------------------------------------

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """1.1 -> 1.2: keep the client devices users already have as selected clients."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        server = server_device_id(entry)
        clients: dict[str, dict] = {}
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
            for domain, ident in device.identifiers:
                if domain == DOMAIN and ident != server:
                    clients[ident] = {"name": device.name or ident, "app": device.model}
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_CLIENTS: clients}, minor_version=2
        )
        _LOGGER.info("Emby: kept %d existing client devices as selected clients", len(clients))
    return True


@callback
def _async_cleanup_registry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove per-session entities from older versions and deselected clients."""
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        # Per-session entities from older versions, and a media player older
        # versions made for Home Assistant's own connection to Emby.
        if ent.unique_id.startswith(("remote-", "kill-")) or ent.unique_id == f"{server_device_id(entry)}-{server_device_id(entry)}":
            ent_reg.async_remove(ent.entity_id)

    selected = set(selected_clients(hass, entry))
    server = server_device_id(entry)
    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        ids = {i[1] for i in device.identifiers if i[0] == DOMAIN}
        if ids and server not in ids and not ids & selected:
            dev_reg.async_remove_device(device.id)


@callback
def _async_register_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create the server device, then each selected client linked to it."""
    dev_reg = dr.async_get(hass)
    data: EmbyData = entry.runtime_data
    info = (data.sessions.data or {}).get("system_info", {})
    server = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, server_device_id(entry))},
        manufacturer="Emby", model="Emby Server", name=entry.title,
        sw_version=info.get("Version"), configuration_url=data.client.get_server_url(),
    )
    # HA 2026.8+ links devices by registry ID; older versions by identifier.
    link = (
        {"via_device_id": server.id} if _SUPPORTS_VIA_DEVICE_ID
        else {"via_device": (DOMAIN, server_device_id(entry))}
    )
    for device_id, client_info in selected_clients(hass, entry).items():
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device_id)},
            manufacturer="Emby", model=client_info.get("app"), name=client_info["name"],
            **link,
        )


_SUPPORTS_VIA_DEVICE_ID = "via_device_id" in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters


# Object IDs older versions generated that didn't include the device name.
_LEGACY_IDS = {"emby_server_update", "emby", "emby_update"}


@callback
def _async_migrate_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename entity IDs older versions generated to '<device> <entity>' form.

    Only IDs matching the old automatic pattern are changed, so IDs a user
    picked themselves are left alone.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        device = dev_reg.async_get(ent.device_id) if ent.device_id else None
        if device is None:
            continue
        device_name = device.name_by_user or device.name or ""
        object_id = ent.entity_id.split(".", 1)[1]
        base = re.sub(r"_\d+$", "", object_id)
        legacy = {slugify(ent.original_name or "")} | _LEGACY_IDS
        if not (base in legacy or base.startswith("emby_modern_")):
            continue
        desired_name = f"{device_name} {ent.original_name}" if ent.original_name else device_name
        desired = f"{ent.domain}.{slugify(desired_name)}"
        if desired == ent.entity_id or ent_reg.async_get(desired):
            continue
        _LOGGER.info("Emby: renaming %s to %s", ent.entity_id, desired)
        ent_reg.async_update_entity(ent.entity_id, new_entity_id=desired)
