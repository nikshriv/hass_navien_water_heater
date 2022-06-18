"""Support for Navien NaviLink water heaters On Demand/External Recirculator."""
import logging
import asyncio

from homeassistant.components.switch import (
    SwitchEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity
)
from .navien_api import (
    DeviceSorting,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Navien On Demand switch based on a config entry."""
    navilink,coordinator = hass.data[DOMAIN][entry.entry_id]
    devices = []
    deviceNum = '1'
    for channel in navilink.last_state:
        if navilink.channelInfo["channel"][str(channel)]["useOnDemand"]:
            devices.append(NavienOnDemandSwitchEntity(coordinator, navilink, channel, deviceNum))
        devices.append(NavienPowerSwitchEntity(coordinator, navilink, channel, deviceNum))        
    async_add_entities(devices)


class NavienOnDemandSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Define a Navien Hot Button/On Demand/External Recirculator Entity."""

    def __init__(self, coordinator, navilink, channel, deviceNum):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.deviceNum = deviceNum
        self.navilink = navilink
        self.channel = channel
        self.gatewayID = navilink.channelInfo["deviceID"]
        self.channelInfo = navilink.channelInfo["channel"][channel]
        self._state = navilink.last_state[channel][deviceNum]

    @property
    def available(self):
        """Return if the the device is online or not."""
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers = {(DOMAIN, self.gatewayID + "_" + str(self.channel))},
            manufacturer = "Navien",
            name = str(DeviceSorting(self._state["deviceSorting"]).name) + "_" + self.channel + "_hot_button" ,
        )

    @property
    def name(self):
        """Return the name of the entity."""
        return str(DeviceSorting(self._state["deviceSorting"]).name) + " CH " + self.channel + " Hot Button"

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.gatewayID + "_" + self.channel + "_" + self.deviceNum + "_hot_button"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._state = self.navilink.last_state[self.channel][self.deviceNum]
        self.async_write_ha_state()

    @property
    def is_on(self):
        """Return the current On Demand state."""
        return self._state["useOnDemand"]

    async def async_turn_on(self):
        """Toggle Hot Button."""
        new_state = await self.navilink.sendOnDemandControlRequest(int(self.channel),int(self.deviceNum))
        self._state = new_state[self.channel][self.deviceNum]
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Toggle Hot Button."""
        new_state = await self.navilink.sendOnDemandControlRequest(int(self.channel),int(self.deviceNum))
        self._state = new_state[self.channel][self.deviceNum]
        self.async_write_ha_state()

class NavienPowerSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Define a Power Switch Entity."""

    def __init__(self, coordinator, navilink, channel, deviceNum):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.deviceNum = deviceNum
        self.navilink = navilink
        self.channel = channel
        self.gatewayID = navilink.channelInfo["deviceID"]
        self.channelInfo = navilink.channelInfo["channel"][channel]
        self._state = navilink.last_state[channel][deviceNum]

    @property
    def available(self):
        """Return if the the device is online or not."""
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers = {(DOMAIN, self.gatewayID + "_" + str(self.channel))},
            manufacturer = "Navien",
            name = str(DeviceSorting(self._state["deviceSorting"]).name) + "_" + self.channel + "_power" ,
        )

    @property
    def name(self):
        """Return the name of the entity."""
        return str(DeviceSorting(self._state["deviceSorting"]).name) + " CH " + self.channel + " Power"

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.gatewayID + "_" + self.channel + "_" + self.deviceNum + "_power"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._state = self.navilink.last_state[self.channel][self.deviceNum]
        self.async_write_ha_state()

    @property
    def is_on(self):
        """Return the current On Demand state."""
        return self._state["powerStatus"]

    async def async_turn_on(self):
        """Turn on power"""
        new_state = await self.navilink.sendPowerControlRequest(int(self.channel),int(self.deviceNum),1)
        self._state = new_state[self.channel][self.deviceNum]
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off power"""
        new_state = await self.navilink.sendPowerControlRequest(int(self.channel),int(self.deviceNum),2)
        self._state = new_state[self.channel][self.deviceNum]
        self.async_write_ha_state()