from collections import OrderedDict
from dataclasses import dataclass
import datetime
import logging

from homeassistant import config_entries, core
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .pysuez1 import SuezClient, SuezError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
) -> None:
    """
    Setup sensors from a config entry created in the integrations UI
    """
    config = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug(f'async_setup_entry {config=}')
    coordinator = SuezCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()
    async_add_entities(
        SuezSensor(coordinator, idx, ent) for idx, ent in enumerate(coordinator.data)
    )


@dataclass
class SuezSensorData:
    name: str
    value: int
    counter_id: int
    valid: bool
    state_class: str
    attribution: str


suez_attributes_map = OrderedDict([
    ('yesterday_delta'      , {'attr': 'last', 'index': 0, 'state_class': None}),
    ('yesterday_total'      , {'attr': 'last', 'index': 1, 'state_class' : SensorStateClass.TOTAL}),
    ('last_year_delta'      , {'attr': 'last_year_overall', 'index': None, 'state_class': None}),
    ('this_year_delta'      , {'attr': 'this_year_overall', 'index': None, 'state_class': None}),
    ('highest_monthly_delta', {'attr': 'highest_monthly', 'index': None, 'state_class': None}),
])


class SuezCoordinator(DataUpdateCoordinator):
    """
    SuezCoordinator is the central place of updating all the sensors

    It is scheduled to update once per hour (may be less...) and sends updates
    to all the sensors that are created
    """

    POLL_DELAY_HOURS = 4

    def __init__(self, hass, info):
        """
        Initialize Suez Ccoordinator
        """
        super().__init__(
            hass,
            _LOGGER,
            name="suez_coordinator",
            update_interval=datetime.timedelta(hours=self.POLL_DELAY_HOURS)
        )
        self.counter_id = info['counter_id']
        self.suez = SuezClient(
            username=info['username'],
            password=info['password'],
            counter_id=info['counter_id'],
            provider=info['provider'],
            logger=_LOGGER)

    def _suez_value(self, suez, desc):
        """
        Convert value received from suez API to what sensors expect
        """
        _LOGGER.debug(f"Trying to get attr {desc['attr']}")
        try:
            value = getattr(suez, desc['attr'])
            index = desc['index']
            return value if index is None else value[index]
        except Exception as exc:
            _LOGGER.error(f"When getting {desc['attr']}, exception happened: {exc}; returning None")
            return None

    async def _async_update_data(self):
        """
        Get updates from Suez, and then return updated values for sensors
        """
        _LOGGER.debug("Update!")
        valid = False
        try:
            await self.suez.update_async()
            valid = self.suez.uptodate
        except SuezError as exc:
            _LOGGER.error(f"When updating, exception happened: {exc}")
        sensors = [SuezSensorData(
            name=key,
            value=self._suez_value(self.suez, desc),
            counter_id=self.counter_id,
            valid=valid,
            state_class=desc['state_class'],
            attribution=self.suez.attribution
        ) for (key, desc) in suez_attributes_map.items()]
        return sensors


class SuezSensor(CoordinatorEntity, SensorEntity):

    """
    Representation of SuezSensor. Fortunately, there are not so much.
    Each sensor returns the value (in cubic meters) and may be serving
    as a source for the Energy dashboard
    """

    def __init__(self, coordinator, idx, entry):
        """
        Initialize the sensor
        """
        super().__init__(coordinator, context=idx)
        _LOGGER.debug(f'Initializing with {idx=}, {entry=}')
        self._counter_id = entry.counter_id
        self._idx = idx
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_attribution = entry.attribution
        if entry.valid:
            self._attr_native_value = entry.value
        self._attr_state_class = entry.state_class
        self._attr_icon = "mdi:water-pump"
        self._attr_unique_id = f"suez_{entry.counter_id}_{idx}"
        self._attr_name = f'suez_{entry.counter_id}_{entry.name}'
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"suez_{self._counter_id}")},
            "name": "SUEZ client",
            "sw_version": "None",
            "model": "",
            "manufacturer": "SUEZ",
        }

    @core.callback
    def _handle_coordinator_update(self) -> None:
        """
        Handle updated data from the coordinator
        """
        _LOGGER.info(f"Updating with {self.coordinator.data[self._idx]}")
        sensor_data = self.coordinator.data[self._idx]
        if sensor_data.valid:
            _LOGGER.debug(f"{sensor_data.valid=}, updating the value")
            self._attr_native_value = sensor_data.value
            self.async_write_ha_state()
