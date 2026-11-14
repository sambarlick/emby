"""Emby client remotes, for navigation commands in scripts."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    DEFAULT_NUM_REPEATS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .clients import selected_clients
from .entity import EmbyClientEntity

COMMAND_MAP = {
    "up": "MoveUp", "down": "MoveDown", "left": "MoveLeft", "right": "MoveRight",
    "select": "Select", "back": "Back", "home": "GoHome", "menu": "GoHome",
}
PLAYSTATE_COMMANDS = {"Stop", "Pause", "Unpause", "NextTrack", "PreviousTrack", "PlayPause"}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    data = entry.runtime_data
    async_add_entities(
        EmbyRemote(data, device_id, info["name"], info.get("app"))
        for device_id, info in selected_clients(hass, entry).items()
    )


class EmbyRemote(EmbyClientEntity, RemoteEntity):
    """Disabled by default: only adds navigation commands beyond the media player."""

    _attr_name = "Remote"
    _attr_entity_registry_enabled_default = False

    def __init__(self, data, device_id, device_name, app_name) -> None:
        super().__init__(data, device_id, device_name, app_name, key="remote")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        return bool(self.session)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Emby can't wake a client remotely, so this does nothing."""

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop playback on the client."""
        if self.session_id:
            await self.client.playstate(self.session_id, "Stop")

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        if not self.session_id:
            raise HomeAssistantError("That client isn't connected")
        repeats = kwargs.get(ATTR_NUM_REPEATS, DEFAULT_NUM_REPEATS)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        for _ in range(repeats):
            for cmd in command:
                emby_cmd = COMMAND_MAP.get(cmd, cmd)
                if emby_cmd in PLAYSTATE_COMMANDS:
                    await self.client.playstate(self.session_id, emby_cmd)
                else:
                    await self.client.general_command(self.session_id, emby_cmd)
                if delay:
                    await asyncio.sleep(delay)
