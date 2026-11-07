"""Publish completed Salad earnings buckets to Home Assistant Recorder."""

from datetime import datetime
from decimal import Decimal

from homeassistant.components.recorder.models import StatisticData, StatisticMeanType
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant

from .const import DOMAIN

SERIES = (("earnings_24h", "hourly"), ("earnings_30d", "daily"))


def publish_statistics(
    hass: HomeAssistant,
    entry_id: str,
    history: dict[str, dict[datetime, Decimal]],
    previous: dict[str, dict[datetime, Decimal]] | None,
) -> None:
    """Upsert new or corrected completed buckets by their original timestamps."""
    for window_key, period in SERIES:
        buckets = history[window_key]
        previous_buckets = previous[window_key] if previous is not None else {}
        current_start = next(reversed(buckets))
        previous_current = next(reversed(previous_buckets), None)
        points: list[StatisticData] = [
            {"start": start, "mean": float(amount)}
            for start, amount in buckets.items()
            if start != current_start
            and (start == previous_current or previous_buckets.get(start) != amount)
        ]
        if points:
            async_add_external_statistics(
                hass,
                {
                    "statistic_id": f"{DOMAIN}:earnings_{period}_{entry_id.lower()}",
                    "source": DOMAIN,
                    "name": f"Salad earnings {period}",
                    "unit_of_measurement": "USD",
                    "unit_class": None,
                    "mean_type": StatisticMeanType.ARITHMETIC,
                    "has_sum": False,
                },
                points,
            )
