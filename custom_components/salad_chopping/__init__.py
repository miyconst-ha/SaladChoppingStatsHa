"""Home Assistant integration for Salad Chopping."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging

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

        try:
            hourly = await self.client.hourly_history(earnings.machines)
        except SaladError as err:
            if self.data is None or self.data.history is not None:
                LOGGER.warning("Could not update Salad earnings history: %s", err)
            return SaladData(earnings, None)

        now = datetime.now(UTC)
        history = {window.key: window.buckets(hourly, now) for window in WINDOWS}
        publish_statistics(
            self.hass, self._entry_id, history, self.data.history if self.data else None
        )
        return SaladData(earnings, history)


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
