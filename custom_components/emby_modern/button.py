"""Support for Emby buttons."""
from __future__ import annotations
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .entity import EmbyEntity
from .emby_client import CannotConnect
from .const import IGNORED_CLIENTS

SERVER_BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(key="restart", name="Restart", icon="mdi:restart"),
    ButtonEntityDescription(key="shutdown", name="Shutdown", icon="mdi:power"),
    ButtonEntityDescription(key="scan", name="Scan Library", icon="mdi:database-refresh"),
)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    
    # 1. Server Buttons
    entities = [EmbyServerButton(coordinator, desc) for desc in SERVER_BUTTONS]
    
    # 2. Dynamic Session Buttons
    added_sessions = set()

    @callback
    def _update_session_buttons():
        sessions = coordinator.data.get("sessions", [])
        new_buttons = []
        
        for session in sessions:
            session_id = session.get("Id")
            
            if session.get("Client") in IGNORED_CLIENTS: continue
            if not session.get("SupportsRemoteControl", False): continue

            if session_id and session_id not in added_sessions:
                device_id = session.get("DeviceId") or session_id
                device_name = session.get("DeviceName") or "Unknown Device"
                client_name = session.get("Client")
                
                new_buttons.append(EmbyKillButton(coordinator, session_id, device_id, device_name, client_name))
                added_sessions.add(session_id)
        
        if new_buttons:
            async_add_entities(new_buttons)

    entry.async_on_unload(coordinator.async_add_listener(_update_session_buttons))
    _update_session_buttons()
    async_add_entities(entities)

class EmbyServerButton(EmbyEntity, ButtonEntity):
    def __init__(self, coordinator, description):
        super().__init__(
            coordinator, 
            device_id=None,
            client_name="Emby Server"
        )
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.unique_id}-{description.key}"
        # Entity name will be handled by base class + description.name 
        # e.g. "Emby Server" + "Restart"

    async def async_press(self) -> None:
        if self.entity_description.key == "restart":
            await self.coordinator.client.api_request("POST", "System/Restart")
        elif self.entity_description.key == "shutdown":
            await self.coordinator.client.api_request("POST", "System/Shutdown")
        elif self.entity_description.key == "scan":
            await self.coordinator.client.api_request("POST", "Library/Refresh")

class EmbyKillButton(EmbyEntity, ButtonEntity):
    _attr_name = "Stop Session"
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, coordinator, session_id, device_id, device_name, client_name):
        super().__init__(coordinator, device_id, device_name, client_name)
        self.session_id = session_id
        self._attr_unique_id = f"kill-{session_id}"

    @property
    def available(self) -> bool:
        current_ids = [s["Id"] for s in self.coordinator.data.get("sessions", [])]
        return self.session_id in current_ids

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.api_request("POST", f"Sessions/{self.session_id}/Playing/Stop")
            await self.coordinator.client.api_request("DELETE", f"Sessions/{self.session_id}")
        except CannotConnect:
            pass
        await self.coordinator.async_request_refresh()
