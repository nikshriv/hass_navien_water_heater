"""The Navien NaviLink Water Heater Integration."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from .navien_api import (
    NavilinkConnect
)
from .const import DOMAIN
import logging
import os
_LOGGER=logging.getLogger(__name__)

PLATFORMS: list[str] = ["water_heater","sensor","switch"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Navien NaviLink Water Heater Integration from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    aws_path = hass.config.path() 
    subdirs = ['custom_components','navien_water_heater','cert']
    for subdir in subdirs:
        aws_path = os.path.join(aws_path,subdir)
    navilink = NavilinkConnect(userId=entry.data.get("username",""), passwd=entry.data.get("password",""), polling_interval=entry.data.get("polling_interval",15), device_index=entry.data.get("device_index",0), aws_cert_path=os.path.join(aws_path,"AmazonRootCA1.pem"))
    hass.data[DOMAIN][entry.entry_id] = navilink
    await navilink.start()    

    # Register the NaviLink module itself, which owns the MAC address. Each
    # channel's device links to it through via_device_id, so the MAC shows in
    # the device registry without channels on the same module sharing one
    # connection.
    device_info = navilink.device_info.get("deviceInfo",{})
    mac_address = device_info.get("macAddress")
    connections = set()
    if mac_address:
        connections.add((dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac_address)))
    navilink_device = dr.async_get(hass).async_get_or_create(
        config_entry_id = entry.entry_id,
        identifiers = {(DOMAIN, mac_address or "unknown")},
        connections = connections,
        manufacturer = "Navien",
        model = "NaviLink",
        name = device_info.get("deviceName","unknown") + " NaviLink",
    )
    navilink.navilink_device_id = navilink_device.id

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

