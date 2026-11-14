"""Emby Server update entity."""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import EmbyServerEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([EmbyServerUpdate(entry.runtime_data)])


class EmbyServerUpdate(EmbyServerEntity, UpdateEntity):
    """Shows when a newer Emby Server is out.

    Install is only offered when Emby reports it can update itself
    (CanSelfUpdate). Linux service installs, Docker and LXC report false and
    have to be updated outside Emby.
    """

    _attr_name = "Update"
    _attr_title = "Emby Server"
    _attr_device_class = UpdateDeviceClass.FIRMWARE

    def __init__(self, data) -> None:
        super().__init__(data, data.sessions, "update")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.emby.releases.async_add_listener(self.async_write_ha_state))

    def _release(self) -> dict | None:
        """Newest release on the server's update channel (Release or Beta)."""
        releases = self.emby.releases.data or []
        beta = str(self.system_info.get("SystemUpdateLevel", "Release")).lower() == "beta"
        for rel in releases:
            if beta or not rel["prerelease"]:
                return rel
        return None

    @property
    def installed_version(self) -> str | None:
        return self.system_info.get("Version")

    @property
    def latest_version(self) -> str | None:
        release = self._release()
        if release:
            return release["version"]
        if self.system_info.get("HasUpdateAvailable"):
            return "newer version available"
        return self.installed_version

    @property
    def release_url(self) -> str | None:
        release = self._release()
        return release["url"] if release else None

    @property
    def release_summary(self) -> str | None:
        release = self._release()
        return release["notes"][:250] if release and release["notes"] else None

    @property
    def supported_features(self) -> UpdateEntityFeature:
        if self.system_info.get("CanSelfUpdate"):
            return UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
        return UpdateEntityFeature.RELEASE_NOTES

    async def async_release_notes(self) -> str | None:
        release = self._release()
        return release["notes"] if release else None

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        """Self-updating servers download updates themselves; a restart applies them."""
        if not self.system_info.get("CanSelfUpdate"):
            raise HomeAssistantError("This Emby server can't update itself")
        if not self.system_info.get("HasPendingRestart"):
            raise HomeAssistantError("Emby hasn't downloaded the update yet. Try again later.")
        await self.client.restart()
