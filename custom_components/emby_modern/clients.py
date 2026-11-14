"""Choosing which Emby clients become Home Assistant devices."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import CONF_CLIENTS, DOMAIN
from .emby_client import EmbyClient

_LOGGER = logging.getLogger(__name__)

# Home Assistant's own connections show up in Emby as clients. They aren't
# playback devices, so they're never offered.
OWN_DEVICE_IDS = {"homeassistant"}
OWN_CLIENT_APPS = {"Emby_Modern (HA)", "Home Assistant", "pyEmby"}


def _is_own(device_id: str | None, app: str | None, server_id: str | None) -> bool:
    return not device_id or device_id in OWN_DEVICE_IDS or device_id == server_id or app in OWN_CLIENT_APPS


def selected_clients(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, dict]:
    """{device_id: {"name": ..., "app": ...}} for the clients the user selected."""
    return dict(entry.options.get(CONF_CLIENTS, {}))


async def async_known_clients(client: EmbyClient, server_id: str | None = None) -> dict[str, dict]:
    """Every client Emby knows about, connected or not.

    Active sessions come first because their DeviceId is what playback uses.
    Emby's device list adds clients that aren't connected right now.
    """
    known: dict[str, dict] = {}
    for sess in await client.get_sessions():
        device_id = sess.get("DeviceId")
        if not _is_own(device_id, sess.get("Client"), server_id) and device_id not in known:
            known[device_id] = {
                "name": sess.get("DeviceName") or device_id,
                "app": sess.get("Client"),
            }
    try:
        devices = await client.get_devices()
    except Exception:  # pylint: disable=broad-except
        _LOGGER.debug("Could not read Emby's device list")
        devices = []
    for dev in devices:
        device_id = dev.get("ReportedDeviceId") or dev.get("Id")
        if not _is_own(device_id, dev.get("AppName"), server_id) and device_id not in known:
            known[device_id] = {
                "name": dev.get("Name") or device_id,
                "app": dev.get("AppName"),
                "last_seen": (dev.get("DateLastActivity") or "")[:10],
            }
    return known


def client_label(info: dict) -> str:
    """'Lounge TV (AndroidTv)' style label for the picker."""
    label = info["name"]
    if info.get("app"):
        label += f" ({info['app']})"
    if info.get("last_seen"):
        label += f", last seen {info['last_seen']}"
    return label


def issue_id(entry: ConfigEntry, device_id: str) -> str:
    return f"new_client_{entry.entry_id}_{device_id}"


@callback
def async_flag_new_clients(hass: HomeAssistant, entry: ConfigEntry, sessions: list[dict], seen: set[str]) -> None:
    """Raise a Repairs notice for each connected client that isn't selected.

    A notice the user ignores stays ignored (Home Assistant remembers it).
    """
    selected = selected_clients(hass, entry)
    for sess in sessions:
        device_id = sess.get("DeviceId")
        if _is_own(device_id, sess.get("Client"), entry.unique_id) or device_id in selected or device_id in seen:
            continue
        # Integrations and tools (Home Assistant, Music Assistant, Infuse)
        # can't be controlled, so they aren't offered as devices.
        if not sess.get("SupportsRemoteControl"):
            ir.async_delete_issue(hass, DOMAIN, issue_id(entry, device_id))  # from beta 1
            continue
        seen.add(device_id)
        name = sess.get("DeviceName") or device_id
        ir.async_create_issue(
            hass, DOMAIN, issue_id(entry, device_id),
            is_fixable=True, is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="new_client",
            translation_placeholders={"name": name, "app": sess.get("Client") or "Emby", "server": entry.title},
            data={"entry_id": entry.entry_id, "device_id": device_id,
                  "name": name, "app": sess.get("Client")},
        )


@callback
def async_clear_client_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove notices for clients that are now selected."""
    for device_id in selected_clients(hass, entry):
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry, device_id))
