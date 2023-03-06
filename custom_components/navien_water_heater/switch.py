"""Support for Navien NaviLink water heaters On Demand/External Recirculator."""
from homeassistant.components.switch import (
    SwitchEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .navien_api import DeviceSorting
from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Navien On Demand switch based on a config entry."""
    navilink = hass.data[DOMAIN][entry.entry_id]
    devices = []
    for channel in navilink.channels.values():
        if channel.channel_info.get("onDemandUse",2) == 1:
            devices.append(NavienOnDemandSwitchEntity(navilink, channel))
        devices.append(NavienPowerSwitchEntity(navilink, channel))        
    async_add_entities(devices)


class NavienOnDemandSwitchEntity(SwitchEntity):
    """Define a Navien Hot Button/On Demand/External Recirculator Entity."""

    def __init__(self, navilink, channel):
        self.navilink = navilink
        self.channel = channel

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.channel.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.channel.deregister_callback(self.async_write_ha_state)

    @property
    def available(self):
        """Return if the the device is online or not."""
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers = {(DOMAIN, self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + "_" + str(self.channel.channel_number))},
            manufacturer = "Navien",
            name = self.navilink.device_info.get("deviceInfo",{}).get("deviceName","unknown") + " CH" + str(self.channel.channel_number)
        )

    @property
    def name(self):
        """Return the name of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("deviceName","UNKNOWN") + " Hot Button CH" + str(self.channel.channel_number)

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + str(self.channel.channel_number) + "hot_button"

    @property
    def is_on(self):
        """Return the current On Demand state."""
        return self.channel.channel_status.get("onDemandUseFlag",False)

    async def async_turn_on(self):
        """Turn On Hot Button."""
        await self.channel.set_hot_button_state(True)

    async def async_turn_off(self):
        """Turn Off Hot Button."""
        await self.channel.set_hot_button_state(False)


class NavienPowerSwitchEntity(SwitchEntity):
    """Define a Power Switch Entity."""

    def __init__(self, navilink, channel):
        self.navilink = navilink
        self.channel = channel

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.channel.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.channel.deregister_callback(self.async_write_ha_state)

    @property
    def available(self):
        """Return if the the device is online or not."""
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers = {(DOMAIN, self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + "_" + str(self.channel.channel_number))},
            manufacturer = "Navien",
            name = self.navilink.device_info.get("deviceInfo",{}).get("deviceName","unknown") + " CH" + str(self.channel.channel_number)
        )

    @property
    def name(self):
        """Return the name of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("deviceName","UNKNOWN") + " Power CH" + str(self.channel.channel_number)


    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + str(self.channel.channel_number) + "power_button"

    @property
    def is_on(self):
        """Return the current On Demand state."""
        return self.channel.channel_status.get("powerStatus",False)

    async def async_turn_on(self):
        """Turn On Power."""
        await self.channel.set_power_state(True)

    async def async_turn_off(self):
        """Turn Off Power."""
        await self.channel.set_power_state(False)