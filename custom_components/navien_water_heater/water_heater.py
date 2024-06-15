"""Support for Navien NaviLink water heaters."""
import logging

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
    STATE_GAS,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .navien_api import TemperatureType
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = (
    WaterHeaterEntityFeature.AWAY_MODE | WaterHeaterEntityFeature.TARGET_TEMPERATURE | WaterHeaterEntityFeature.OPERATION_MODE
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Navien water heater based on a config entry."""
    navilink = hass.data[DOMAIN][entry.entry_id]
    devices = []
    for channel in navilink.channels.values():
        devices.append(NavienWaterHeaterEntity(hass, channel,navilink))
    async_add_entities(devices)


class NavienWaterHeaterEntity(WaterHeaterEntity):
    """Define a Navien water heater."""

    def __init__(self, hass, channel, navilink):
        self.hass = hass
        self.channel = channel
        self.navilink = navilink

    @property
    def available(self):
        """Return if the the device is online or not."""
        return self.channel.is_available()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers = {(DOMAIN, self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + "_" + str(self.channel.channel_number))},
            manufacturer = "Navien",
            name = self.navilink.device_info.get("deviceInfo",{}).get("deviceName","unknown") + " CH" + str(self.channel.channel_number),
        )

    @property
    def name(self):
        """Return the name of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("deviceName","UNKNOWN") + " CH" + str(self.channel.channel_number)

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + str(self.channel.channel_number)

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.channel.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.channel.deregister_callback(self.async_write_ha_state)

    @property
    def temperature_unit(self):
        """Return temperature unit."""
        temp_unit = UnitOfTemperature.CELSIUS
        if self.channel.channel_info["temperatureType"] == TemperatureType.FAHRENHEIT.value:
            temp_unit = UnitOfTemperature.FAHRENHEIT
        return temp_unit

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return not(self.channel.channel_status.get("powerStatus",False))

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def current_operation(self):
        """Return current operation."""
        _current_op = STATE_OFF
        if self.channel.channel_status.get("powerStatus",False):
            _current_op = STATE_GAS
        return _current_op

    @property
    def operation_list(self):
        """List of available operation modes."""
        return [STATE_OFF, STATE_GAS]
    
    @property
    def current_temperature(self):
        """Return the current hot water temperature."""
        unit_list = self.channel.channel_status.get("unitInfo",{}).get("unitStatusList",[])
        if len(unit_list) > 0:
            return round(sum([unit_info.get("currentOutletTemp") for unit_info in unit_list])/len(unit_list))
        else:
            _LOGGER.warning("No channel status information available for " + self.name)

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.channel.channel_status.get("DHWSettingTemp",0)

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.channel.channel_info.get("setupDHWTempMin",0)

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.channel.channel_info.get("setupDHWTempMax",0)

    async def async_set_temperature(self,**kwargs):
        """Set target water temperature"""
        hass_units = "us_customary" if self.hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else "metric"
        navien_units = "us_customary" if self.channel.channel_info.get("temperatureType",2) == TemperatureType.FAHRENHEIT.value else "metric"
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if hass_units == navien_units:
            if self.temperature_unit == UnitOfTemperature.CELSIUS:
                target_temp = round(2 * target_temp)
        else:
            if hass_units == "metric":
                target_temp == round((target_temp*9/5) + 32)
            else:
                target_temp == round((target_temp-32)*10/9)
        await self.channel.set_temperature(target_temp)


    async def async_turn_away_mode_on(self):
        """Turn away mode on."""
        await self.channel.set_power_state(False)

    async def async_turn_away_mode_off(self):
        """Turn away mode off."""
        await self.channel.set_power_state(True)

    async def async_set_operation_mode(self,operation_mode):
        """Set operation mode"""
        if operation_mode == STATE_GAS:
            power_state = True
        else:
            power_state = False
        await self.channel.set_power_state(power_state)
