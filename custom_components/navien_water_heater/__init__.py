"""The Navien NaviLink Water Heater Integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from datetime import timedelta
import logging
from .navien_api import (
    NavienSmartControl,
    DeviceSorting
)

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed
)

_LOGGER = logging.getLogger(__name__)

from .const import DOMAIN

PLATFORMS: list[str] = ["water_heater","sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navien NaviLink Water Heater Integration from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    for channelInfo in entry.data:
        hass.data[DOMAIN][entry.entry_id][bytes.hex(channelInfo["deviceID"])] = NaviLinkCoordinator(hass, channelInfo, entry.title.replace("navien_",""))
        await hass.data[DOMAIN][entry.entry_id][bytes.hex(channelInfo["deviceID"])].async_config_entry_first_refresh()
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

class NaviLinkCoordinator(DataUpdateCoordinator):
    """NaviLink coordinator."""

    def __init__(self, hass, channelInfo, username):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="NaviLink" + "-" + bytes.hex(channelInfo['deviceID']),
            update_interval=timedelta(seconds=60),
        )
        self.channelInfo = channelInfo
        self.navilink = NavienSmartControl(username,"")

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        deviceStates = {}
        try:
            await self.navilink.connect(self.channelInfo["deviceID"])         
            for channelNum in range(1,4):
                if self.channelInfo["channel"][str(channelNum)]["deviceSorting"] != DeviceSorting.NO_DEVICE.value:
                    for deviceNum in range(1,self.channelInfo["channel"][str(channelNum)]["deviceCount"] + 1):
                        try:
                            state = await self.navilink.sendStateRequest(self.channelInfo["deviceID"],channelNum,deviceNum)
                            state = self.navilink.convertState(state,self.channelInfo["deviceTempFlag"])
                            deviceStates[str(channelNum)][str(deviceNum)] = state
                        except:
                            pass
            try:    
                await self.navilink.disconnect()
            except:
                pass
            return deviceStates
        except:
            raise UpdateFailed

