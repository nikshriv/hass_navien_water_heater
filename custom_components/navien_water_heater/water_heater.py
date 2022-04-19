"""Support for Navien NaviLink water heaters."""
import logging

from homeassistant.components.water_heater import (
    STATE_GAS,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, TEMP_CELCIUS, TEMP_FARENHEIT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity
)
from .navien_api import (
    NavienSmartControl
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE | WaterHeaterEntityFeature.AWAY_MODE
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Navien water heater based on a config entry."""
    device_data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NavienWaterHeaterEntity(channel_data)
            for channel_data in device_data
        ],
    )


class NavienWaterHeaterEntity(CoordinatorEntity, WaterHeaterEntity):
    """Define a Navien water heater."""
 
    def __init__(self, channel_data):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(channel_data['coordinator'])
        self.gatewayID_bytes = channel_data["deviceID"]
        self.gatewayID_str = channel_data['gatewayID']
        self.channel = channel_data["controlChannelNum"]
        self.deviceNum = 1
        self.navien = NavienSmartControl(channel_data["username",""])
        self.channel_data = self.navien.convertChannelInformation(channel_data)["channel"][self.channel]
        self.state = self.coordinator.data[0]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.state = self.coordinator.data[0]
        self.async_write_ha_state()

    @property
    def temperature_unit(self):
        """Return temperature unit."""
        temp_unit = TEMP_CELCIUS
        if self.channel_data["deviceTempFlag"] == 'FARENHEIT':
            temp_unit = TEMP_FARENHEIT

        return temp_unit

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return not(self.state["powerStatus"])

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def current_temperature(self):
        """Return the temperature we try to reach."""
        return self.state["hotWaterCurrentTemperature"]

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.state["hotWaterSettingTemperature"]

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.channel_data["minimumSettingWaterTemperature"]

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.channel_data["maximumSettingWaterTemperature"]

    async def async_set_temperature(self,**kwargs):
        """Set target water temperature"""
        if (target_temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self.navien.connect(self.gatewayID_str)
            self.navien.sendWaterTempControlRequest(self.gatewayID_bytes,int(self.channel),self.deviceNum,target_temp)
            self.navien.disconnect()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("A target temperature must be provided")

    async def async_turn_away_mode_on(self):
        """Turn away mode on."""
        self.navien.connect(self.gatewayID_str)
        self.navien.sendPowerControlRequest(self.gatewayID_bytes,int(self.channel),self.deviceNum,2)
        self.navien.disconnect()
        await self.coordinator.async_request_refresh()


    async def async_turn_away_mode_off(self):
        """Turn away mode off."""
        self.navien.connect(self.gatewayID_str)
        self.navien.sendPowerControlRequest(self.gatewayID_bytes,int(self.channel),self.deviceNum,1)
        self.navien.disconnect()
        await self.coordinator.async_request_refresh()
