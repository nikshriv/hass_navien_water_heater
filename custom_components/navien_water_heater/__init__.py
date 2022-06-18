"""The Navien NaviLink Water Heater Integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from datetime import timedelta
from datetime import datetime
import logging
from .navien_api import (
    NavienSmartControl,
)

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed
)

_LOGGER = logging.getLogger(__name__)

from .const import DOMAIN

PLATFORMS: list[str] = ["water_heater","sensor","switch"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navien NaviLink Water Heater Integration from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    navilink = NavienSmartControl(entry.data["username"],entry.data["gatewayID"])
    await navilink.connect()
    
    async def _update_method():
        """Get the latest data from Navien."""
        try:
            for channelNum in range(1,4):
                if navilink.channelInfo["channel"][str(channelNum)]["deviceSorting"] > 0:
                    for deviceNum in range(1,navilink.channelInfo["channel"][str(channelNum)]["deviceCount"] + 1):
                        time_diff = 15
                        if navilink.last_state.get(str(channelNum)) is not None:
                            time_diff  = (datetime.now() - navilink.last_state[str(channelNum)][str(deviceNum)]['last_update']).total_seconds()

                        if time_diff > 5:                        
                            await navilink.sendStateRequest(channelNum, deviceNum)

        except Exception as e:
            _LOGGER.error(str(type(e).__name__) + ": " + str(e))
            raise UpdateFailed
            
        return navilink.last_state

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_update_method,
        update_interval=timedelta(seconds=entry.data["polling_interval"]),
    )
    
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = (navilink,coordinator)

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

