"""The Navien NaviLink Water Heater Integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .navien_api import (
    NavilinkConnect
)

from .const import DOMAIN

PLATFORMS: list[str] = ["water_heater","sensor","switch"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navien NaviLink Water Heater Integration from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    navilink = NavilinkConnect(userId=entry.data.get("username",""), passwd=entry.data.get("password",""), polling_interval=entry.data.get("polling_interval",15), device_index=entry.data.get("device_index",0), aws_cert_path="/config/custom_components/navien_water_heater/cert/AmazonRootCA1.pem")
    hass.data[DOMAIN][entry.entry_id] = navilink
    await navilink.start()    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    navilink = hass.data[DOMAIN][entry.entry_id]
    await navilink.disconnect()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

