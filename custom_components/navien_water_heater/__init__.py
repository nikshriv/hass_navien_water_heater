"""The Navien NaviLink Water Heater Integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from datetime import timedelta
import logging
from .navien_api import (
    NavienSmartControl
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
    hass.data[DOMAIN][entry.entry_id] = entry.data
    for devIndex in range(0,len(entry.data)):
        hass.data[DOMAIN][entry.entry_id][devIndex]['coordinator'] = NaviLinkCoordinator(hass, entry.data[devIndex])
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

    def __init__(self, hass, channelInfo):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="NaviLink" + "-" + str(channelInfo['gatewayID']) + "-" + channelInfo['controlChannelNum'],
            update_interval=timedelta(seconds=60),
        )
        self.device_config = channelInfo
        self.navilink = NavienSmartControl(channelInfo["username"],"")

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        deviceStates = []
        try:
            channelInfo = self.navilink.connect(self.device_config["gatewayID"])
            for devNum in range(1,channelInfo["channel"][self.device_config["controlChannelNum"]]["deviceCount"] + 1):
                state = self.navilink.sendStateRequest(channelInfo["deviceID"],int(self.device_config["controlChannelNum"]),devNum)
                state = self.navilink.convertState(state)
                deviceStates.append(state)
            self.navilink.disconnect()
            return deviceStates
        except:
            raise UpdateFailed

