"""Support for Navien NaviLink water heaters."""
import logging

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    STATE_GAS,
    SUPPORT_AWAY_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, TEMP_CELSIUS, TEMP_FAHRENHEIT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity
)
from .navien_api import (
    NavienSmartControl,
    DeviceSorting,
    TemperatureType,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = (
    SUPPORT_AWAY_MODE | SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Navien water heater based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    navilink = NavienSmartControl(entry.data["username"],entry.data["password"])
    devices = []
    deviceNum = '1'
    _LOGGER.exception(coordinator.data)
    for gateway in coordinator.data:
        for channel in coordinator.data[gateway]["state"]:
            devices.append(NavienWaterHeaterEntity(coordinator, navilink, gateway, channel, deviceNum))
    async_add_entities(devices)


class NavienWaterHeaterEntity(CoordinatorEntity, WaterHeaterEntity):
    """Define a Navien water heater."""
 
    def __init__(self, coordinator, navilink, gateway, channel, deviceNum):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.deviceNum = deviceNum
        self.navilink = navilink
        self.channel = channel
        self.gateway = gateway
        self.channelInfo = coordinator.data[gateway]["channelInfo"]["channel"][channel]
        self._state = coordinator.data[gateway]["state"][channel][deviceNum]

    @property
    def available(self):
        """Return if the the device is online or not."""
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers = {(DOMAIN, self.gateway + "-" + str(self.channel))},
            manufacturer = "Navien",
            name = str(DeviceSorting(self._state["deviceSorting"]).name) + self.channel,
        )

    @property
    def name(self):
        """Return the name of the entity."""
        return "Navien " + str(DeviceSorting(self._state["deviceSorting"]).name) + " Channel " + self.channel

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.gateway + "-" + self.channel + "-" + self.deviceNum

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._state = self.coordinator.data[self.gateway]["state"][self.channel][self.deviceNum]
        self.async_write_ha_state()

    @property
    def temperature_unit(self):
        """Return temperature unit."""
        temp_unit = TEMP_CELSIUS
        if self.channelInfo["deviceTempFlag"] == TemperatureType.FAHRENHEIT.value:
            temp_unit = TEMP_FAHRENHEIT

        return temp_unit

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return not(self._state["powerStatus"])

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def current_operation(self):
        """Return current operation."""
        power_status = self._state["powerStatus"]
        _current_op = STATE_OFF
        if power_status:
            _current_op = STATE_GAS
        return _current_op

    @property
    def operation_list(self):
        """List of available operation modes."""
        return [STATE_GAS]
    
    @property
    def current_temperature(self):
        """Return the temperature we try to reach."""
        return self._state["hotWaterTemperature"]

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._state["hotWaterSettingTemperature"]

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.channelInfo["minimumSettingWaterTemperature"]

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.channelInfo["maximumSettingWaterTemperature"]

    async def async_set_temperature(self,**kwargs):
        """Set target water temperature"""
        if (target_temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.navilink.connect(self.gateway)
            await self.navilink.sendWaterTempControlRequest(self.gateway,int(self.channel),int(self.deviceNum),target_temp)
            await self.navilink.disconnect()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("A target temperature must be provided")

    async def async_turn_away_mode_on(self):
        """Turn away mode on."""
        await self.navilink.connect(self.gateway)
        await self.navilink.sendPowerControlRequest(self.gateway,int(self.channel),int(self.deviceNum),2)
        await self.navilink.disconnect()
        await self.coordinator.async_request_refresh()


    async def async_turn_away_mode_off(self):
        """Turn away mode off."""
        await self.navilink.connect(self.gateway)
        await self.navilink.sendPowerControlRequest(self.gateway,int(self.channel),int(self.deviceNum),1)
        await self.navilink.disconnect()
        await self.coordinator.async_request_refresh()
