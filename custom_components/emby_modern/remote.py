"""Support for Emby Remote Control."""
from __future__ import annotations
from typing import Any, Iterable
import asyncio

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    DEFAULT_NUM_REPEATS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .const import IGNORED_CLIENTS
from .entity import EmbyEntity

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    added_ids = set()

    @callback
    def _update_remotes():
        sessions = coordinator.data.get("sessions", [])
        new_entities = []

        for session in sessions:
            if session.get("Client") in IGNORED_CLIENTS: continue
            if not session.get("SupportsRemoteControl", False): continue

            session_id = session.get("Id")
            
            if session_id and session_id not in added_ids:
                device_id = session.get("DeviceId") or session_id
                device_name = session.get("DeviceName") or "Unknown Device"
                client_name = session.get("Client")
                
                new_entities.append(EmbyRemote(coordinator, session_id, device_id, device_name, client_name))
                added_ids.add(session_id)
        
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_update_remotes))
    _update_remotes()

class EmbyRemote(EmbyEntity, RemoteEntity):
    """Emby Remote Control."""

    def __init__(self, coordinator, session_id, device_id, device_name, client_name):
        super().__init__(coordinator, device_id, device_name, client_name)
        self.session_id = session_id
        self._attr_unique_id = f"remote-{session_id}"
        self._attr_name = "Remote" 

    @property
    def available(self) -> bool:
        """Return True if the session exists and coordinator is happy."""
        if not super().available:
            return False
        current_ids = [s["Id"] for s in self.coordinator.data.get("sessions", [])]
        return self.session_id in current_ids

    @property
    def is_on(self) -> bool:
        """Return true if the session is still active."""
        return self.available

    # FIX: Added turn_on/off to prevent NotImplementedError crashes
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Do nothing, as we cannot usually turn on an Emby client remotely."""
        # We implementation this to prevent the NotImplementedError crash
        pass

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the remote off (Stop Playback)."""
        await self.coordinator.client.api_request("POST", f"Sessions/{self.session_id}/Playing/Stop")

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send a command to the device."""
        num_repeats = kwargs.get(ATTR_NUM_REPEATS, DEFAULT_NUM_REPEATS)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)

        for _ in range(num_repeats):
            for cmd in command:
                emby_cmd = cmd
                
                if cmd == "up": emby_cmd = "MoveUp"
                elif cmd == "down": emby_cmd = "MoveDown"
                elif cmd == "left": emby_cmd = "MoveLeft"
                elif cmd == "right": emby_cmd = "MoveRight"
                elif cmd == "select": emby_cmd = "Select"
                elif cmd == "back": emby_cmd = "Back"
                elif cmd == "home": emby_cmd = "GoHome"
                elif cmd == "menu": emby_cmd = "GoHome"
                
                if emby_cmd in ["Stop", "Pause", "Unpause", "NextTrack", "PreviousTrack"]:
                     await self.coordinator.client.api_request("POST", f"Sessions/{self.session_id}/Playing/{emby_cmd}")
                else:
                     await self.coordinator.client.api_request(
                         "POST", 
                         f"Sessions/{self.session_id}/Command", 
                         params={"Header": "Test", "Text": "Test"},
                         json_data={"Name": emby_cmd}
                     )

                if delay > 0:
                    await asyncio.sleep(delay)
