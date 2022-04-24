"""Config flow for Navien Water Heater integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .navien_api import (
    NavienSmartControl,
    DeviceSorting,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,       
    }
)

class NavienConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NaviLink."""

    def __init__(self):
        self.navien = None
        self.gateway_data = None
        self.device_data = {}

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
            self.navien = NavienSmartControl(user_input['username'],user_input['password'])
            self.gateway_data = await self.navien.login()
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            for gateway in self.gateway_data:
                try:
                    channelInfo = await self.navien.connect(gateway["GID"])
                    self.device_data[gateway["GID"]] = channelInfo
                except:
                    return self.async_abort(reason="no_devices_available")
            title = 'navien_' + user_input['username']
            if len(self.device_data) > 0:
                existing_entry = await self.async_set_unique_id(title)
                if not existing_entry:              
                    return self.async_create_entry(title=title, data=self.device_data)
                else:
                    self.hass.config_entries.async_update_entry(existing_entry, data=self.device_data)
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")
            else:
                return self.async_abort(reason="no_devices_available")

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
