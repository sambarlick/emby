"""Config flow for Emby Modern integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_API_KEY, CONF_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .const import DOMAIN
from .emby_client import EmbyClient, CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8096


def _clean_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise the host field: strip whitespace, protocol and trailing slash.

    If the user typed https://, the SSL option is switched on for them.
    """
    data = dict(user_input)
    host = data[CONF_HOST].strip()

    if host.startswith("http://"):
        host = host[7:]
    elif host.startswith("https://"):
        host = host[8:]
        data[CONF_SSL] = True

    data[CONF_HOST] = host.rstrip("/")

    if CONF_API_KEY in data:
        data[CONF_API_KEY] = data[CONF_API_KEY].strip()
    return data


class EmbyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emby Modern."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT

    async def _async_get_server_info(self, data: dict[str, Any]) -> tuple[str, str]:
        """Connect with the given settings and return (server_id, server_name).

        Uses a plain API call rather than validate_connection() so that no
        background WebSocket is started from inside the config flow.

        Raises CannotConnect or InvalidAuth.
        """
        client = EmbyClient(
            data[CONF_HOST],
            data[CONF_PORT],
            data[CONF_API_KEY],
            data[CONF_SSL],
            session=async_get_clientsession(self.hass),
        )
        try:
            system_info = await client.get_system_info()
        except TimeoutError as err:
            raise CannotConnect("Timed out connecting to Emby") from err

        server_id = system_info.get("Id")
        if not server_id:
            raise CannotConnect("No Server ID found")
        return server_id, system_info.get("ServerName", "Emby Server")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step (Manual Setup)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _clean_input(user_input)
            try:
                server_id, server_name = await self._async_get_server_info(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"
            else:
                # Unique ID prevents duplicates (and stops SSDP re-discovering
                # a server that was added manually).
                await self.async_set_unique_id(server_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=server_name, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._discovered_host or vol.UNDEFINED): str,
                vol.Optional(CONF_PORT, default=self._discovered_port): int,
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_SSL, default=False): bool,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the connection details of an existing entry.

        Lets the user update host, port, HTTPS and (optionally) the API key
        without deleting the integration. The server ID must match the
        original, so entities, devices and automations are preserved.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            # A blank API key means "keep the current one".
            if not user_input.get(CONF_API_KEY, "").strip():
                user_input[CONF_API_KEY] = entry.data[CONF_API_KEY]
            user_input = _clean_input(user_input)

            try:
                server_id, _ = await self._async_get_server_info(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(server_id)
                self._abort_if_unique_id_mismatch(reason="wrong_server")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_SSL: user_input[CONF_SSL],
                        CONF_API_KEY: user_input[CONF_API_KEY],
                    },
                )

        current = {**entry.data, **(user_input or {})}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current[CONF_HOST]): str,
                vol.Optional(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_API_KEY, default=""): str,
                vol.Optional(CONF_SSL, default=current.get(CONF_SSL, False)): bool,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> ConfigFlowResult:
        """Handle SSDP discovery."""
        # 1. Parse the Unique ID (UDN)
        udn = discovery_info.upnp.get("udn", "")
        if udn.startswith("uuid:"):
            udn = udn[5:]

        # SSDP sends 416809c9-1f52..., the Emby API sends 416809c91f52...
        # Normalise to the API format to prevent duplicates.
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
