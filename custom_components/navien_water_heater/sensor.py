"""Support for Navien NaviLink sensors."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from .navien_api import (TemperatureType)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    VOLUME_CUBIC_METERS,
    VOLUME_CUBIC_FEET,
    POWER_BTU_PER_HOUR,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
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

SENSORS = {
    "imperial":{
        "avgCalorie": SensorEntityDescription(
            key = "avgCalorie",
            device_class = SensorDeviceClass.POWER_FACTOR,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            name="Heating Capacity",
        ),
        "gasInstantUsage": SensorEntityDescription(
            key = "gasInstantUsage",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=POWER_BTU_PER_HOUR,
            name="Current Gas Use",
        ),
        "accumulatedGasUsage": SensorEntityDescription(
            key = "accumulatedGasUsage",
            device_class=SensorDeviceClass.GAS,
            state_class = SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=VOLUME_CUBIC_FEET,
            name="Cumulative Gas Use",
        ),
        "DHWFlowRate": SensorEntityDescription(
            key = "DHWFlowRate",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=FLOW_GALLONS_PER_MIN,
            name="Hot Water Flow",
        ),
        "currentInletTemp": SensorEntityDescription(
            key = "currentInletTemp",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=TEMP_FAHRENHEIT,
            name="Inlet Temp",
        ),
        "currentOutletTemp": SensorEntityDescription(
            key = "currentOutletTemp",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=TEMP_FAHRENHEIT,
            name="Hot Water Temp",
        )
    },
    "metric":{
        "avgCalorie": SensorEntityDescription(
            key = "avgCalorie",
            device_class = SensorDeviceClass.POWER_FACTOR,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            name="Heating Capacity",
        ),
        "gasInstantUsage": SensorEntityDescription(
            key = "gasInstantUsage",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=POWER_KCAL_PER_HOUR,
            name="Current Gas Use",
        ),
        "accumulatedGasUsage": SensorEntityDescription(
            key = "accumulatedGasUsage",
            device_class=SensorDeviceClass.GAS,
            state_class = SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=VOLUME_CUBIC_METERS,
            name="Cumulative Gas Use",
        ),
        "DHWFlowRate": SensorEntityDescription(
            key = "DHWFlowRate",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=FLOW_LITERS_PER_MIN,
            name="Hot Water Flow",
        ),
        "currentInletTemp": SensorEntityDescription(
            key = "currentInletTemp",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=TEMP_CELSIUS,
            name="Inlet Temp",
        ),
        "currentOutletTemp": SensorEntityDescription(
            key = "currentOutletTemp",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=TEMP_CELSIUS,
            name="Hot Water Temp",
        )
    }
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Navien sensor."""

    navilink = hass.data[DOMAIN][entry.entry_id]
    sensors = []
    for channel in navilink.channels.values():
        if channel.channel_info["temperatureType"] == TemperatureType.FAHRENHEIT.value:
            units = "imperial"
        else:
            units = "metric"
        sensors.append(NavienSensor(navilink, channel, {}, SENSORS[units]["avgCalorie"],"avgCalorie"))
        for unit_info in channel.channel_status.get("unitInfo",{}).get("unitStatusList",[]):
            for sensor_type in SENSORS[units]:
                if sensor_type != "avgCalorie":
                    sensors.append(NavienSensor(navilink, channel, unit_info, SENSORS[units][sensor_type], sensor_type))
    async_add_entities(sensors)


class NavienSensor(SensorEntity):
    """Representation of a Navien Sensor device."""

    def __init__(self, navilink, channel, unit_info, sensor_description, sensor_type):
        """Initialize the sensor."""
        self.navilink = navilink
        self.sensor_description = sensor_description
        self.unit_number = unit_info.get("unitNumber","")
        self.unit_info = unit_info
        self.channel = channel
        self.sensor_type = sensor_type

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self.channel.register_callback(self.update_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self.channel.deregister_callback(self.update_state)

    def update_state(self):
        if len(self.unit_info):
            for unit_info in self.channel.channel_status.get("unitInfo",{}).get("unitStatusList",[]):
                if unit_info.get("unitNumber","") == self.unit_number:
                    self.unit_info = unit_info
        self.async_write_ha_state()

    @property
    def available(self):
        """Return if the the sensor is online or not."""
        return True

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
        if self.sensor_type != "avgCalorie":
            return self.unit_info.get(self.sensor_type,0)
        else:
            return self.channel.channel_status.get(self.sensor_type,0)