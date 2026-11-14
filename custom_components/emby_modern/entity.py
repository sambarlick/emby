"""Base entities for Emby Modern."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN
from .coordinator import EmbyData


def server_device_id(entry) -> str:
    """Identifier of the Emby server device."""
    return entry.unique_id or entry.entry_id


class EmbyServerEntity(CoordinatorEntity):
    """An entity that belongs to the Emby server device."""

    _attr_has_entity_name = True

    def __init__(self, data: EmbyData, coordinator: DataUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.emby = data
        self.client = data.client
        entry = coordinator.config_entry
        self._attr_unique_id = f"{server_device_id(entry)}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, server_device_id(entry))},
            manufacturer="Emby",
            model="Emby Server",
            name=entry.title,
            configuration_url=data.client.get_server_url(),
        )

    @property
    def system_info(self) -> dict:
        return (self.emby.sessions.data or {}).get("system_info", {})


class EmbyClientEntity(CoordinatorEntity):
    """An entity that belongs to an Emby client device (TV, phone, browser)."""

    _attr_has_entity_name = True

    def __init__(self, data: EmbyData, device_id: str, device_name: str,
                 app_name: str | None, key: str | None) -> None:
        super().__init__(data.sessions)
        self.emby = data
        self.client = data.client
        self.device_id = device_id
        server_id = server_device_id(data.sessions.config_entry)
        self._attr_unique_id = f"{server_id}-{device_id}" + (f"-{key}" if key else "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="Emby",
            model=app_name,
            name=device_name,
            via_device=(DOMAIN, server_id),
        )

    @property
    def session(self) -> dict:
        """The client's current session, or {} when it isn't connected."""
        sessions = (self.coordinator.data or {}).get("sessions", [])
        matches = [s for s in sessions if s.get("DeviceId") == self.device_id]
        if not matches:
            return {}
        # Prefer a session that is playing, then the most recent.
        matches.sort(key=lambda s: ("NowPlayingItem" in s, s.get("LastActivityDate", "")), reverse=True)
        return matches[0]

    @property
    def session_id(self) -> str | None:
        return self.session.get("Id")
