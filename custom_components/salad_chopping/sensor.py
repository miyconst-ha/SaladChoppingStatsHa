"""Salad balance and earnings sensors."""

from decimal import Decimal

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EVENT_RECORDER_HOURLY_STATISTICS_GENERATED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SaladConfigEntry, SaladCoordinator
from .const import DOMAIN
from .history import WINDOWS, HistoryWindow
from .statistics import publish_entity_statistics


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SaladConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the balance and discover new machines as they appear."""
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    if rate_entity_id := registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_earnings_rate"
    ):
        registry.async_remove(rate_entity_id)
    known_machines: set[str] = set()
    async_add_entities(
        [
            SaladBalanceSensor(coordinator, entry.entry_id),
            SaladCompletedPeriodSensor(
                coordinator, entry.entry_id, "hour", "earnings_24h"
            ),
            SaladCompletedPeriodSensor(
                coordinator, entry.entry_id, "day", "earnings_30d"
            ),
            *(SaladHistorySensor(coordinator, entry.entry_id, window) for window in WINDOWS),
        ]
    )

    @callback
    def add_machines() -> None:
        machines = coordinator.data.earnings.machines
        new_machines = machines.keys() - known_machines
        if new_machines:
            async_add_entities(
                SaladMachineSensor(coordinator, entry.entry_id, machine_id)
                for machine_id in sorted(new_machines)
            )
            known_machines.update(new_machines)

    add_machines()
    entry.async_on_unload(coordinator.async_add_listener(add_machines))


class SaladMoneySensor(CoordinatorEntity[SaladCoordinator], SensorEntity):
    """Shared attributes for a Salad monetary sensor."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator: SaladCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Salad",
            name="Salad Chopping Statistics",
        )


class SaladBalanceSensor(SaladMoneySensor):
    """The account balance available for redemption."""

    _attr_name = "Salad current balance"

    def __init__(self, coordinator: SaladCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_balance"

    @property
    def native_value(self) -> Decimal:
        return self.coordinator.data.earnings.balance


class SaladMachineSensor(SaladMoneySensor):
    """Lifetime earnings reported for one machine."""

    def __init__(self, coordinator: SaladCoordinator, entry_id: str, machine_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._machine_id = machine_id
        self._attr_unique_id = f"{entry_id}_{machine_id}_lifetime_earnings"
        name = coordinator.data.earnings.machines[machine_id].name
        self._attr_name = f"Salad {name} lifetime earnings"

    @property
    def available(self) -> bool:
        return super().available and self._machine_id in self.coordinator.data.earnings.machines

    @property
    def native_value(self) -> Decimal | None:
        machine = self.coordinator.data.earnings.machines.get(self._machine_id)
        return machine.lifetime_earnings if machine else None


class SaladHistorySensor(SaladMoneySensor):
    """A rolling earnings total with the individual chart buckets."""

    _attr_state_class = None
    _unrecorded_attributes = frozenset({"earnings"})

    def __init__(self, coordinator: SaladCoordinator, entry_id: str, window: HistoryWindow) -> None:
        super().__init__(coordinator, entry_id)
        self._window = window
        self._attr_unique_id = f"{entry_id}_{window.key}"
        self._attr_name = window.name

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.history is not None

    @property
    def native_value(self) -> Decimal | None:
        history = self.coordinator.data.history
        return sum(history[self._window.key].values(), Decimal(0)) if history else None

    @property
    def extra_state_attributes(self) -> dict:
        history = self.coordinator.data.history
        if history is None:
            return {}
        return {
            "earnings": [
                [int(start.timestamp() * 1000), float(amount)]
                for start, amount in history[self._window.key].items()
            ]
        }


class SaladCompletedPeriodSensor(SaladMoneySensor):
    """Expose API earnings with statistics attached to this sensor's entity ID."""

    # Monetary device class only supports totals. These are independent bucket
    # observations, with mean/min/max used by HA's native chart suggestions.
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-areaspline"

    def __init__(
        self, coordinator: SaladCoordinator, entry_id: str, period: str, window_key: str
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._window_key = window_key
        self._period = period
        self._published_buckets = None
        self._published_entity_id = None
        # Preserve existing entity IDs and dashboard references on upgrade.
        self._attr_unique_id = f"{entry_id}_earnings_last_completed_{period}"
        self._attr_name = f"Salad earnings {'hourly' if period == 'hour' else 'daily'}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Only now is the real entity ID assigned, including user renames and
        # suffixes for multiple accounts. The card picker uses this exact ID.
        self._publish_statistics()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_RECORDER_HOURLY_STATISTICS_GENERATED,
                self._statistics_generated,
            )
        )

    @callback
    def _statistics_generated(self, event) -> None:
        # Recorder averages live states each hour. Restore API buckets after
        # that job so completed earnings never become averages of stale states.
        self._publish_statistics(force=True)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._publish_statistics()
        super()._handle_coordinator_update()

    @callback
    def _publish_statistics(self, *, force: bool = False) -> None:
        history = self.coordinator.data.history
        if history is None:
            return
        buckets = history[self._window_key]
        previous = self._published_buckets
        if force or self._published_entity_id != self.entity_id:
            previous = None
        publish_entity_statistics(
            self.hass, self.entity_id, self.name, self._period, buckets, previous
        )
        self._published_buckets = buckets.copy()
        self._published_entity_id = self.entity_id

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.history is not None

    @property
    def native_value(self) -> Decimal | None:
        history = self.coordinator.data.history
        if history is None:
            return None
        # Buckets are chronological and the last one is still in progress.
        buckets = history[self._window_key]
        latest_buckets = reversed(buckets.values())
        next(latest_buckets, None)
        return next(latest_buckets, None)
