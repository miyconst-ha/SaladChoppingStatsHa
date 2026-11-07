"""Publish completed Salad earnings buckets to Home Assistant Recorder."""

from datetime import datetime, timedelta
from decimal import Decimal

from homeassistant.components.recorder.models import StatisticData, StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_import_statistics,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN

SERIES = (("earnings_24h", "hourly"), ("earnings_30d", "daily"))


def publish_entity_statistics(
    hass: HomeAssistant,
    entity_id: str,
    name: str,
    period: str,
    buckets: dict[datetime, Decimal],
    previous: dict[datetime, Decimal] | None,
) -> None:
    """Backfill the exact sensor IDs selected by native suggested cards.

    Recorder stores hourly rows. Repeat each completed daily total in all 24
    UTC hours so daily means remain that total even when live Recorder rows
    already exist. Min/max equal the same bucket amount, making HA's default
    mean/min/max suggestions usable as well.
    """
    current_start = next(reversed(buckets), None)
    previous_current = next(reversed(previous), None) if previous else None
    points: list[StatisticData] = []
    for start, amount in buckets.items():
        if start == current_start:
            continue
        if previous is not None and start != previous_current and previous.get(start) == amount:
            continue
        value = float(amount)
        for hour in range(24 if period == "day" else 1):
            points.append({
                "start": start + timedelta(hours=hour),
                "mean": value,
                "min": value,
                "max": value,
            })
    if points:
        async_import_statistics(
            hass,
            {
                "statistic_id": entity_id,
                "source": "recorder",
                "name": name,
                "unit_of_measurement": "USD",
                "unit_class": None,
                "mean_type": StatisticMeanType.ARITHMETIC,
                "has_sum": False,
            },
            points,
        )


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
