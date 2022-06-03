"""Config flow for Navien Water Heater integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .navien_api import (
    NavienAccountInfo,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,       
    }
)

STEP_SET_POLLING_INTERVAL = vol.Schema(
    {
        vol.Required("polling_interval",default=15): vol.All(vol.Coerce(int), vol.Range(min=15))
    }
)

class NavienConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NaviLink."""

    def __init__(self):
        self.navien = None
        self.gateways = None
        self.username = ''
        self.gatewayID = ''
        self.polling_interval = 15

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user and password for NaviLink account."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            self.navien = NavienAccountInfo(user_input['username'],user_input['password'])
            self.gateways = await self.navien.login()
        except Exception:  # pylint: disable=broad-except
            errors["base"] = "invalid_auth"
        else:
            self.username = user_input['username']
            return await self.async_step_pick_gateway()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_pick_gateway(
        self, user_input=None
    ) -> FlowResult:
        """Handle choosing the gateway."""
        if user_input is None:
            return self.async_show_form(
                step_id="pick_gateway", data_schema= vol.Schema(
                    {
                        vol.Required("gatewayID", default=self.gateways[0]["GID"]): vol.In(
                            {
                                gateway["GID"]:gateway["NickName"] for gateway in self.gateways
                            }
                        ),
                    }
                )
            )

        self.gatewayID = user_input["gatewayID"]
        return await self.async_step_set_polling_interval()

    async def async_step_set_polling_interval(
        self, user_input = None
    ) -> FlowResult:
        """Handle polling interval for this gateway."""
        if user_input is None:
            return self.async_show_form(
                step_id="set_polling_interval", data_schema=STEP_SET_POLLING_INTERVAL
            )

        title = 'navien_' + self.username + '_' + self.gatewayID
        existing_entry = await self.async_set_unique_id(title)
        if not existing_entry:
            return self.async_create_entry(title=title, data={"username":self.username, "gatewayID":self.gatewayID, "polling_interval":user_input["polling_interval"]})
        else:
            self.hass.config_entries.async_update_entry(existing_entry, data={"username":self.username, "gatewayID":self.gatewayID, "polling_interval":user_input["polling_interval"]})
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")
