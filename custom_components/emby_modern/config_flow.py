"""Config flow for Emby Modern integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_API_KEY, CONF_SSL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .const import DOMAIN
from .emby_client import EmbyClient, CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

class EmbyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emby Modern."""

    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self._discovered_host: str | None = None
        self._discovered_port: int = 8096

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

        # Define schema with defaults (using discovered values if available)
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._discovered_host or vol.UNDEFINED): str,
                vol.Optional(CONF_PORT, default=self._discovered_port): int,
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_SSL, default=False): bool,
            }
        )

        # Show the form
        return self.async_show_form(
            step_id="user", 
            data_schema=schema, 
            errors=errors
        )

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> FlowResult:
        """Handle SSDP discovery."""
        # 1. Parse the Unique ID (UDN)
        udn = discovery_info.upnp.get("udn", "")
        if udn.startswith("uuid:"):
            udn = udn[5:]
        
        # FIX: Remove hyphens to match Emby's internal System ID format
        # SSDP sends: 416809c9-1f52...
        # Emby API sends: 416809c91f52...
        # We must normalize to the API format to prevent duplicates.
        udn = udn.replace("-", "")
        
        # 2. Set the unique ID immediately
        await self.async_set_unique_id(udn)
        self._abort_if_unique_id_configured()

        # 3. Extract Host and Port from presentationURL
        presentation_url = discovery_info.upnp.get("presentationURL")
        if presentation_url:
            parsed = urlparse(presentation_url)
            self._discovered_host = parsed.hostname
            if parsed.port:
                self._discovered_port = parsed.port

        # 4. Update the UI Title
        friendly_name = discovery_info.upnp.get("friendlyName", "Emby Server")
        self.context["title_placeholders"] = {"name": friendly_name}

        # 5. Redirect to the User Form
        return await self.async_step_user()
