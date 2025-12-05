"""Config flow for Emby Modern integration."""
from __future__ import annotations
import logging
from typing import Any
from urllib.parse import urlparse
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_API_KEY, CONF_SSL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .const import DOMAIN
from .emby_client import EmbyClient, CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    client = EmbyClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        api_key=data[CONF_API_KEY],
        ssl=data[CONF_SSL],
        loop=hass.loop,
        session=session
    )

    try:
        # Returns {"title": "Emby Server", "unique_id": "GUID..."}
        info = await client.validate_connection()
    except (CannotConnect, InvalidAuth) as err:
        raise err
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect(f"Unexpected error: {err}")

    return info

class EmbyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emby Modern."""

    VERSION = 1
    
    def __init__(self):
        """Initialize flow."""
        self.discovery_info = {}

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo):
        """Handle SSDP discovery."""
        # 1. Parse URL
        url = discovery_info.ssdp_location
        if not url:
            return self.async_abort(reason="no_url")

        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 8096

        # 2. Get Unique ID (System ID)
        # Emby sends "uuid:YOUR-GUID-HERE". We strip the prefix.
        udn = discovery_info.upnp.get("udn", "")
        if udn.startswith("uuid:"):
            unique_id = udn[5:]
        else:
            unique_id = udn

        # 3. Set Unique ID immediately
        # This prevents duplicate discovery cards if the server spams SSDP
        await self.async_set_unique_id(unique_id)
        
        # 4. Abort if this ID is already configured
        # If the IP changed, this updates the existing entry's host/port automatically!
        self._abort_if_unique_id_configured(updates={
            CONF_HOST: host, 
            CONF_PORT: port
        })

        # 5. Store for the user step
        self.discovery_info = {
            CONF_HOST: host,
            CONF_PORT: port
        }
        
        # 6. Context: Show the actual server name in the discovery card title
        self.context["title_placeholders"] = {
            "name": discovery_info.upnp.get("friendlyName", "Emby Server")
        }
        
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        # Pre-fill defaults from discovery if available
        default_host = self.discovery_info.get(CONF_HOST, "")
        default_port = self.discovery_info.get(CONF_PORT, 8096)
        default_ssl = False

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                # Check for duplicates based on System ID (not Name)
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)
                
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
                
            # If we fail, remember what the user typed
            default_host = user_input[CONF_HOST]
            default_port = user_input[CONF_PORT]
            default_ssl = user_input[CONF_SSL]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=default_host): str,
                vol.Required(CONF_PORT, default=default_port): int,
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_SSL, default=default_ssl): bool,
            }),
            errors=errors,
            description_placeholders={"device": "Emby Server"},
        )
        
