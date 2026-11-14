"""Repairs for Emby Modern: adding a newly seen client."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir

from .const import CONF_CLIENTS


class NewClientRepairFlow(RepairsFlow):
    """Offer to add a client Emby reported that isn't selected yet."""

    def __init__(self, issue_id: str, data: dict[str, Any]) -> None:
        self._issue_id = issue_id
        self._data = data

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["add", "ignore"],
            description_placeholders={"name": self._data["name"], "app": self._data.get("app") or "Emby"},
        )

    async def async_step_ignore(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Same as Ignore on the Repairs page: the notice stays hidden."""
        from .const import DOMAIN
        ir.async_ignore_issue(self.hass, DOMAIN, self._issue_id, True)
        return self.async_abort(reason="ignored", description_placeholders={"name": self._data["name"]})

    async def async_step_add(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_confirm({})

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._data["entry_id"])
            if entry is not None:
                clients = dict(entry.options.get(CONF_CLIENTS, {}))
                clients[self._data["device_id"]] = {"name": self._data["name"], "app": self._data.get("app")}
                # The update listener reloads the entry, which adds the device.
                self.hass.config_entries.async_update_entry(
                    entry, options={**entry.options, CONF_CLIENTS: clients}
                )
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm", data_schema=vol.Schema({}),
            description_placeholders={"name": self._data["name"]},
        )


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    return NewClientRepairFlow(issue_id, data or {})
