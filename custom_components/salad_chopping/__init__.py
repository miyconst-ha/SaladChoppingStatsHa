"""Home Assistant integration for Salad Chopping."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
from time import monotonic_ns

from aiohttp import DummyCookieJar
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Earnings, SaladAuthError, SaladClient, SaladError
from .const import CONF_AUTH_COOKIE
from .history import WINDOWS
from .statistics import publish_statistics

PLATFORMS = [Platform.SENSOR]
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SaladData:
    """Current readings and historical chart points from one poll."""

    earnings: Earnings
    history: dict[str, dict[datetime, Decimal]] | None
    sampled_at_ns: int
    earnings_rate: Decimal | None


def _earnings_rate(
    previous: SaladData | None, earnings: Earnings, sampled_at_ns: int
) -> Decimal | None:
    """Measure credited earnings per hour between successful polls."""
    if previous is None or sampled_at_ns <= previous.sampled_at_ns:
        return None
    previous_machines = previous.earnings.machines
    if previous_machines.keys() != earnings.machines.keys():
        return None

    change = Decimal(0)
    for machine_id, machine in earnings.machines.items():
        delta = machine.lifetime_earnings - previous_machines[machine_id].lifetime_earnings
        if delta < 0:
            return None
        change += delta

    elapsed_ns = sampled_at_ns - previous.sampled_at_ns
    return change * Decimal(3_600_000_000_000) / elapsed_ns


class SaladCoordinator(DataUpdateCoordinator[SaladData]):
    """Poll Salad once for all sensors on the account."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(minutes=5),
            always_update=False,
        )
        session = async_create_clientsession(hass, cookie_jar=DummyCookieJar())
        self._entry_id = entry.entry_id
        self.client = SaladClient(session, entry.data[CONF_AUTH_COOKIE])

    async def _async_update_data(self) -> SaladData:
        try:
            earnings = await self.client.earnings()
        except SaladAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SaladError as err:
            raise UpdateFailed(str(err)) from err

        sampled_at_ns = monotonic_ns()
        earnings_rate = _earnings_rate(self.data, earnings, sampled_at_ns)

        try:
            hourly = await self.client.hourly_history(earnings.machines)
        except SaladError as err:
            if self.data is None or self.data.history is not None:
                LOGGER.warning("Could not update Salad earnings history: %s", err)
            return SaladData(earnings, None, sampled_at_ns, earnings_rate)

        now = datetime.now(UTC)
        history = {window.key: window.buckets(hourly, now) for window in WINDOWS}
        publish_statistics(
            self.hass, self._entry_id, history, self.data.history if self.data else None
        )
        return SaladData(earnings, history, sampled_at_ns, earnings_rate)


SaladConfigEntry = ConfigEntry[SaladCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SaladConfigEntry) -> bool:
    """Set up Salad Chopping from a config entry."""
    coordinator = SaladCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SaladConfigEntry) -> bool:
    """Unload Salad Chopping."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
