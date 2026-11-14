"""Config flow for Emby Modern."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .clients import async_known_clients, client_label
from .const import CONF_CLIENTS, DOMAIN
from .emby_client import CannotConnect, EmbyClient, InvalidAuth

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8096


def _clean_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Strip whitespace, protocol and trailing slash from the host.

    Typing https:// switches the HTTPS option on.
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


def _client(hass, data: Mapping[str, Any]) -> EmbyClient:
    return EmbyClient(
        data[CONF_HOST], data[CONF_PORT], data[CONF_API_KEY], data[CONF_SSL],
        session=async_get_clientsession(hass),
    )


async def _server_info(hass, data: Mapping[str, Any]) -> tuple[str, str]:
    """Return (server_id, server_name). Raises CannotConnect or InvalidAuth.

    Doesn't start a WebSocket, so nothing is left running by the flow.
    """
    client = _client(hass, data)
    try:
        info = await client.get_system_info()
    except TimeoutError as err:
        raise CannotConnect("Timed out connecting to Emby") from err
    if not info.get("Id"):
        raise CannotConnect("No server ID found")
    return info["Id"], info.get("ServerName", "Emby Server")


def _clients_schema(known: dict[str, dict], selected: Mapping[str, Any]) -> vol.Schema:
    choices = {**dict(selected), **known}
    options = [{"value": device_id, "label": client_label(info)} for device_id, info in choices.items()]
    return vol.Schema({
        vol.Optional(CONF_CLIENTS, default=list(selected)): SelectSelector(
            SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)
        )
    })


def _selected_to_options(ids: list[str], known: Mapping[str, dict], previous: Mapping[str, dict]) -> dict[str, dict]:
    result = {}
    for device_id in ids:
        info = known.get(device_id) or previous.get(device_id) or {"name": device_id}
        result[device_id] = {"name": info["name"], "app": info.get("app")}
    return result


def _errors_for(err: Exception) -> dict[str, str]:
    if isinstance(err, InvalidAuth):
        return {"base": "invalid_auth"}
    if isinstance(err, CannotConnect):
        return {"base": "cannot_connect"}
    _LOGGER.exception("Unexpected error talking to Emby")
    return {"base": "unknown"}


class EmbyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emby Modern."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._data: dict[str, Any] = {}
        self._title = "Emby Server"
        self._known: dict[str, dict] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EmbyOptionsFlow()

    # ---------------- setup ----------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _clean_input(user_input)
            try:
                server_id, self._title = await _server_info(self.hass, user_input)
            except Exception as err:  # pylint: disable=broad-except
                errors = _errors_for(err)
            else:
                await self.async_set_unique_id(server_id)
                self._abort_if_unique_id_configured()
                self._data = user_input
                return await self.async_step_clients()

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=self._discovered_host or vol.UNDEFINED): str,
            vol.Optional(CONF_PORT, default=self._discovered_port): int,
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_SSL, default=False): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_clients(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick which Emby clients become devices."""
        if user_input is not None:
            clients = _selected_to_options(user_input.get(CONF_CLIENTS, []), self._known, {})
            return self.async_create_entry(title=self._title, data=self._data, options={CONF_CLIENTS: clients})
        try:
            self._known = await async_known_clients(_client(self.hass, self._data))
        except Exception:  # pylint: disable=broad-except
            self._known = {}
        return self.async_show_form(step_id="clients", data_schema=_clients_schema(self._known, {}))

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> ConfigFlowResult:
        udn = discovery_info.upnp.get("udn", "")
        if udn.startswith("uuid:"):
            udn = udn[5:]
        # SSDP sends 416809c9-1f52..., the Emby API 416809c91f52...
        await self.async_set_unique_id(udn.replace("-", ""))
        self._abort_if_unique_id_configured()
        presentation_url = discovery_info.upnp.get("presentationURL")
        if presentation_url:
            parsed = urlparse(presentation_url)
            self._discovered_host = parsed.hostname
            if parsed.port:
                self._discovered_port = parsed.port
        self.context["title_placeholders"] = {"name": discovery_info.upnp.get("friendlyName", "Emby Server")}
        return await self.async_step_user()

    # ---------------- reconfigure ----------------

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change host, port, HTTPS or API key without removing the integration."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_API_KEY, "").strip():
                user_input[CONF_API_KEY] = entry.data[CONF_API_KEY]
            user_input = _clean_input(user_input)
            try:
                server_id, _ = await _server_info(self.hass, user_input)
            except Exception as err:  # pylint: disable=broad-except
                errors = _errors_for(err)
            else:
                await self.async_set_unique_id(server_id)
                self._abort_if_unique_id_mismatch(reason="wrong_server")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={k: user_input[k] for k in (CONF_HOST, CONF_PORT, CONF_SSL, CONF_API_KEY)},
                )

        current = {**entry.data, **(user_input or {})}
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=current[CONF_HOST]): str,
            vol.Optional(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_API_KEY, default=""): str,
            vol.Optional(CONF_SSL, default=current.get(CONF_SSL, False)): bool,
        })
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors,
            description_placeholders={"name": entry.title},
        )

    # ---------------- reauth ----------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for a new API key when Emby stops accepting the old one."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY].strip()}
            try:
                server_id, _ = await _server_info(self.hass, data)
            except Exception as err:  # pylint: disable=broad-except
                errors = _errors_for(err)
            else:
                await self.async_set_unique_id(server_id)
                self._abort_if_unique_id_mismatch(reason="wrong_server")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: data[CONF_API_KEY]})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors, description_placeholders={"name": entry.title},
        )


class EmbyOptionsFlow(OptionsFlow):
    """The settings cog: choose which Emby clients are devices."""

    def __init__(self) -> None:
        self._known: dict[str, dict] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        previous = self.config_entry.options.get(CONF_CLIENTS, {})
        if user_input is not None:
            clients = _selected_to_options(user_input.get(CONF_CLIENTS, []), self._known, previous)
            return self.async_create_entry(data={**self.config_entry.options, CONF_CLIENTS: clients})
        try:
            self._known = await async_known_clients(self.config_entry.runtime_data.client)
        except Exception:  # pylint: disable=broad-except
            self._known = {}
        return self.async_show_form(step_id="init", data_schema=_clients_schema(self._known, previous))
