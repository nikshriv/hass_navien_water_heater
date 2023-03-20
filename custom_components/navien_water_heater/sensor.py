"""Support for Navien NaviLink sensors."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from .navien_api import (TemperatureType)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    VOLUME_CUBIC_METERS,
    VOLUME_CUBIC_FEET,
    POWER_BTU_PER_HOUR,
    UnitOfTemperature,
)

POWER_KCAL_PER_HOUR = 'kcal/hr'
FLOW_GALLONS_PER_MIN = 'gal/min'
FLOW_LITERS_PER_MIN = 'liters/min'

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from .const import DOMAIN
from asyncio import sleep
import logging
_LOGGER=logging.getLogger(__name__)

class GenericSensorDescription():
    """Class to convert values from metric to imperial and vice versa"""
    def __init__(self, state_class, native_unit_of_measurement, name, conversion_factor, device_class=None) -> None:
        self.state_class = state_class
        self.native_unit_of_measurement = native_unit_of_measurement
        self.name = name
        self.conversion_factor = conversion_factor
        self.device_class = device_class

    def convert(self,val):
        return round(val*self.conversion_factor, 1)

class TempSensorDescription():
    """Class to convert temperature values"""
    def __init__(self, state_class, native_unit_of_measurement, name, convert_to, device_class=None) -> None:
        self.state_class = state_class
        self.native_unit_of_measurement = native_unit_of_measurement
        self.name = name
        self.convert_to = convert_to
        self.device_class = device_class

    def convert(self,temp):
        if self.convert_to == UnitOfTemperature.CELSIUS:
            return round((temp-32)*5/9, 1)
        elif self.convert_to == UnitOfTemperature.FAHRENHEIT:
            return round((temp*9/5) + 32)
        else:
            return temp

def get_description(hass_units,navien_units,sensor_type):    
    return {
        "gasInstantUsage": GenericSensorDescription(
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=POWER_KCAL_PER_HOUR if hass_units == "metric" else POWER_BTU_PER_HOUR,
            name="Current Gas Use",
            conversion_factor = 1 if hass_units == navien_units else 3.96567 if hass_units == "us_customary" else 0.2521646022
        ),
        "accumulatedGasUsage": GenericSensorDescription(
            state_class = SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=VOLUME_CUBIC_METERS if hass_units == "metric" else VOLUME_CUBIC_FEET,
            name="Cumulative Gas Use",
            conversion_factor = 1 if hass_units == navien_units else 35.3147 if hass_units == "us_customary" else 0.0283168732,
            device_class=SensorDeviceClass.GAS
        ),
        "DHWFlowRate": GenericSensorDescription(
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=FLOW_LITERS_PER_MIN if hass_units == "metric" else FLOW_GALLONS_PER_MIN,
            name="Hot Water Flow",
            conversion_factor = 1 if hass_units == navien_units else 0.264172 if hass_units == "us_customary" else 3.78541
        ),
        "currentInletTemp": TempSensorDescription(
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS if hass_units == "metric" else UnitOfTemperature.FAHRENHEIT,
            name="Inlet Temp",
            convert_to = "None" if hass_units == navien_units else UnitOfTemperature.FAHRENHEIT if hass_units == "us_customary" else UnitOfTemperature.CELSIUS
        ),
        "currentOutletTemp": TempSensorDescription(
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS if hass_units == "metric" else UnitOfTemperature.FAHRENHEIT,
            name="Hot Water Temp",
            convert_to = "None" if hass_units == navien_units else UnitOfTemperature.FAHRENHEIT if hass_units == "us_customary" else UnitOfTemperature.CELSIUS
        )
    }.get(sensor_type,{})

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Navien sensor."""

    navilink = hass.data[DOMAIN][entry.entry_id]
    sensors = []
    for channel in navilink.channels.values():
        navien_units = "us_customary" if channel.channel_info.get("temperatureType",2) == TemperatureType.FAHRENHEIT.value else "metric"
        hass_units = "us_customary" if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else "metric"
        sensors.append(NavienAvgCalorieSensor(navilink, channel))
        for unit_info in channel.channel_status.get("unitInfo",{}).get("unitStatusList",[]):
            for sensor_type in ["gasInstantUsage","accumulatedGasUsage","DHWFlowRate","currentInletTemp","currentOutletTemp"]:
                sensors.append(NavienSensor(hass, navilink, channel, unit_info, sensor_type, get_description(hass_units,navien_units,sensor_type)))
    async_add_entities(sensors)

class NavienAvgCalorieSensor(SensorEntity):
    """Representation of a Navien Sensor device."""

    def __init__(self, navilink, channel):
        """Initialize the sensor."""
        self.navilink = navilink
        self.channel = channel

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.channel.register_callback(self.update_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.channel.deregister_callback(self.update_state)

    def update_state(self):
        self.async_write_ha_state()

    @property
    def available(self):
        """Return if the the sensor is online or not."""
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
        return "CH" + str(self.channel.channel_number) + " Heating Power"

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + str(self.channel.channel_number) + "avgCalorie"

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the class of this entity."""
        return SensorDeviceClass.POWER_FACTOR

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class of this entity, if any."""
        return SensorStateClass.MEASUREMENT


    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return PERCENTAGE
    
    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self.channel.channel_status.get("avgCalorie",0)
        
class NavienSensor(SensorEntity):
    """Representation of a Navien Sensor device."""

    def __init__(self, hass, navilink, channel, unit_info, sensor_type, sensor_description):
        """Initialize the sensor."""
        self.navilink = navilink
        self.channel = channel
        self.unit_info = unit_info
        self.sensor_type = sensor_type
        self.sensor_description = sensor_description
        self.unit_number = unit_info.get("unitNumber","")
        self.hass = hass

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.channel.register_callback(self.update_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.channel.deregister_callback(self.update_state)

    def update_state(self):
        hass_units = "us_customary" if self.hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else "metric"
        navien_units = "us_customary" if self.channel.channel_info.get("temperatureType",2) == TemperatureType.FAHRENHEIT.value else "metric"
        for unit_info in self.channel.channel_status.get("unitInfo",{}).get("unitStatusList",[]):
            if unit_info.get("unitNumber","") == self.unit_number:
                self.unit_info = unit_info
        self.sensor_description = get_description(hass_units,navien_units,self.sensor_type)
        self.async_write_ha_state()

    @property
    def available(self):
        """Return if the the sensor is online or not."""
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
        if unit_number := self.unit_info.get("unitNumber", None):
            return "CH" + str(self.channel.channel_number) + "_UNIT" + str(unit_number) + " " + self.sensor_description.name
        else:
            return "CH" + str(self.channel.channel_number) + " " + self.sensor_description.name

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.navilink.device_info.get("deviceInfo",{}).get("macAddress","unknown") + str(self.channel.channel_number) + str(self.unit_info.get("unitNumber","")) + self.sensor_type

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the class of this entity."""
        return self.sensor_description.device_class

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class of this entity, if any."""
        return self.sensor_description.state_class


    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self.sensor_description.native_unit_of_measurement
    
    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self.sensor_description.convert(self.unit_info.get(self.sensor_type,0))