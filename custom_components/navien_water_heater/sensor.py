"""Support for Navien NaviLink sensors."""
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from .navien_api import (
    DeviceSorting,
    TemperatureType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    VOLUME_CUBIC_METERS,
    VOLUME_CUBIC_FEET,
    POWER_BTU_PER_HOUR,
)

POWER_KCAL_PER_HOUR = 'kcal/hr'
FLOW_GALLONS_PER_MIN = 'gal/min'
FLOW_LITERS_PER_MIN = 'liters/min'

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SENSORS = {
    "imperial":{
        "averageCalorimeter": SensorEntityDescription(
            key = "averageCalorimeter",
            device_class = SensorDeviceClass.POWER_FACTOR,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            name="Heating Capacity",
        ),
        "gasInstantUse": SensorEntityDescription(
            key = "gasInstantUse",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=POWER_BTU_PER_HOUR,
            name="Power",
        ),
        "gasAccumulatedUse": SensorEntityDescription(
            key = "gasAccumulatedUse",
            device_class=SensorDeviceClass.GAS,
            state_class = SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=VOLUME_CUBIC_FEET,
            name="Total Gas Usage",
        ),
        "hotWaterFlowRate": SensorEntityDescription(
            key = "hotWaterFlowRate",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=FLOW_GALLONS_PER_MIN,
            name="Hot Water Flow",
        )
    },
    "metric":{
        "averageCalorimeter": SensorEntityDescription(
            key = "averageCalorimeter",
            device_class = SensorDeviceClass.POWER_FACTOR,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            name="Heating Capacity",
        ),
        "gasInstantUse": SensorEntityDescription(
            key = "gasInstantUse",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=POWER_KCAL_PER_HOUR,
            name="Power",
        ),
        "gasAccumulatedUse": SensorEntityDescription(
            key = "gasAccumulatedUse",
            device_class=SensorDeviceClass.GAS,
            state_class = SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=VOLUME_CUBIC_METERS,
            name="Total Gas Usage",
        ),
        "hotWaterFlowRate": SensorEntityDescription(
            key = "hotWaterFlowRate",
            device_class = None,
            state_class = SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=FLOW_LITERS_PER_MIN,
            name="Hot Water Flow",
        )
    }
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Airthings sensor."""

    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = []
    for gateway in coordinator.data:
        for channel in coordinator.data[gateway]["state"]:
            units = "metric"
            if coordinator.data[gateway]["channelInfo"]["channel"][channel]["deviceTempFlag"] == TemperatureType.FAHRENHEIT.value:
                units = "imperial"
            for deviceNum in coordinator.data[gateway]["state"][channel]:
                for sensor_type in SENSORS[units]:
                    sensors.append(NavienSensor(coordinator, gateway, channel, deviceNum, SENSORS[units][sensor_type], sensor_type))
    async_add_entities(sensors)


class NavienSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Navien Sensor device."""

    def __init__(self, coordinator, gateway, channel, deviceNum, sensor_description, sensor_type):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.sensor_description = sensor_description
        self.deviceNum = deviceNum
        self.channel = channel
        self.gateway = gateway
        self.channelInfo = coordinator.data[gateway]["channelInfo"]["channel"][channel]
        self._state = coordinator.data[gateway]["state"][channel][deviceNum]
        self.sensor_type = sensor_type

    @property
    def available(self):
        """Return if the the sensor is online or not."""
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return DeviceInfo(
            identifiers = {(DOMAIN, self.gateway + "_" + str(self.channel))},
            manufacturer = "Navien",
            name = str(DeviceSorting(self._state["deviceSorting"]).name) + "_" + self.channel + "_" + self.deviceNum,
        )

    @property
    def name(self):
        """Return the name of the entity."""
        return self.sensor_description.name + " Ch" + self.channel + " Dev" + self.deviceNum

    @property
    def unique_id(self):
        """Return the unique ID of the entity."""
        return self.gateway + "_" + self.channel + "_" + self.deviceNum + "_" + self.sensor_type

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the class of this entity."""
        return self.sensor_description.device_class

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class of this entity, if any."""
        return self.sensor_description.state_class

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._state = self.coordinator.data[self.gateway]["state"][self.channel][self.deviceNum]
        self.async_write_ha_state()

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self._state[self.sensor_type]
