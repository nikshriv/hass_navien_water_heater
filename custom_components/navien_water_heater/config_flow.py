"""Config flow for Navien Water Heater integration."""
from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN
from .navien_api import NavilinkConnect

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,       
    }
)

STEP_SET_POLLING_INTERVAL = vol.Schema(
    {
        vol.Required("polling_interval",default=10): vol.All(vol.Coerce(int), vol.Range(min=10, max=120))
    }
)

class NavienConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NaviLink."""

    def __init__(self):
        self.username = ''
        self.password = ''
        self.device_info = None
        self.device_index = 0
        self.polling_interval = 30

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
            navien = NavilinkConnect(user_input['username'],user_input['password'],polling_interval=0)
            self.device_info = await navien.login()
        except Exception:  # pylint: disable=broad-except
            errors["base"] = "invalid_auth"
        else:
            self.username = user_input['username']
            self.password = user_input['password']
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
                        vol.Required("gatewayID", default=0): vol.In(
                            {
                                self.device_info.index(device):device.get("deviceInfo",{}).get("deviceName","UKNOWN") for device in self.device_info
                            }
                        ),
                    }
                )
            )

        self.device_index = user_input["gatewayID"]
        return await self.async_step_set_polling_interval()

    async def async_step_set_polling_interval(
        self, user_input = None
    ) -> FlowResult:
        """Handle polling interval for this gateway."""
        if user_input is None:
            return self.async_show_form(
                step_id="set_polling_interval", data_schema=STEP_SET_POLLING_INTERVAL
            )

        title = 'navien_' + self.username + '_' + self.device_info[self.device_index].get("deviceInfo",{}).get("macAddress","UNKNOWN")
        existing_entry = await self.async_set_unique_id(title)
        if not existing_entry:
            return self.async_create_entry(title=title, data={"username":self.username, "password":self.password, "device_index":self.device_index, "polling_interval":user_input["polling_interval"]})
        else:
            self.hass.config_entries.async_update_entry(existing_entry, data={"username":self.username, "password":self.password, "device_index":self.device_index, "polling_interval":user_input["polling_interval"]})
            await self.hass.config_entries.async_reload(existing_entry.entry_id)
            return self.async_abort(reason="reauth_successful")
