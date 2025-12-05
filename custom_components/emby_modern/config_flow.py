"""Config flow for Emby Modern integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_API_KEY, CONF_SSL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .const import DOMAIN
from .emby_client import EmbyClient, CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

# Schema for the user form
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=8096): int,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_SSL, default=False): bool,
    }
)

class EmbyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emby Modern."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (Manual Setup)."""
        errors: dict[str, str] = {}

        # If the user has submitted the form
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            
            client = EmbyClient(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_API_KEY],
                user_input[CONF_SSL],
                self.hass.loop,
                session,
            )

            try:
                # 1. Test Connection
                await client.validate_connection()

                # 2. Fetch System Info to get the Unique Server ID
                system_info = await client.get_system_info()
                server_id = system_info.get("Id")
                server_name = system_info.get("ServerName", "Emby Server")

                if not server_id:
                    raise CannotConnect("No Server ID found")

                # 3. Set Unique ID to prevent duplicates
                # This ensures if you add it manually, SSDP won't discover it again
                await self.async_set_unique_id(server_id)
                self._abort_if_unique_id_configured()

                # 4. Create the Config Entry
                return self.async_create_entry(
                    title=server_name, 
                    data=user_input
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"

        # Show the form (Initial load or if errors occurred)
        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors
        )

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> FlowResult:
        """Handle SSDP discovery."""
        # 1. Parse the Unique ID (UDN) from the discovery info
        udn = discovery_info.upnp.get("udn", "")
        if udn.startswith("uuid:"):
            udn = udn[5:]
        
        # 2. Set the unique ID immediately
        # If this ID is already in your Config Entries, this will abort silently.
        await self.async_set_unique_id(udn)
        self._abort_if_unique_id_configured()

        # 3. If we are here, it is a NEW server.
        # Try to guess the host details to pre-fill the form
        
        # Use presentationURL if available, otherwise fallback to ssdp_location
        # (This is just for pre-filling; the user usually still needs to add the API key)
        discovery_url = discovery_info.upnp.get("presentationURL")
        
        # We generally redirect to the user form so they can input the API Key
        # We can pass the discovered host/port to 'user_input' if we wanted to be fancy,
        # but for now, letting the user confirm is safer.
        
        # Update the 'context' so the UI shows "Discovered" instead of generic add
        self.context["title_placeholders"] = {
            "name": discovery_info.upnp.get("friendlyName", "Emby Server")
        }

        return await self.async_step_user()
