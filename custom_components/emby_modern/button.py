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
    ButtonEntityDescription(key="shutdown", name="Shutdown", icon="mdi:power"), # ADDED: Shutdown
    ButtonEntityDescription(key="scan", name="Scan Library", icon="mdi:database-refresh"),
)

# ... async_setup_entry remains unchanged ...

class EmbyServerButton(EmbyEntity, ButtonEntity):
# ... __init__ remains unchanged ...

    async def async_press(self) -> None:
        if self.entity_description.key == "restart":
            await self.coordinator.client.api_request("POST", "System/Restart")
        elif self.entity_description.key == "shutdown": # ADDED: Shutdown command
            await self.coordinator.client.api_request("POST", "System/Shutdown")
        elif self.entity_description.key == "scan":
            await self.coordinator.client.api_request("POST", "Library/Refresh")

# ... EmbyKillButton remains unchanged ...
