"""Aggregate Salad's hourly earnings into the dashboard windows."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class HistoryWindow:
    """A fixed number of hourly or daily chart buckets."""

    key: str
    name: str
    bucket_size: timedelta
    count: int

    def buckets(
        self, hourly: dict[datetime, Decimal], now: datetime
    ) -> dict[datetime, Decimal]:
        """Return ordered UTC buckets, including the current partial bucket."""
        current = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        if self.bucket_size.days:
            current = current.replace(hour=0)
        first = current - self.bucket_size * (self.count - 1)
        buckets = {first + self.bucket_size * index: Decimal(0) for index in range(self.count)}
        for hour, amount in hourly.items():
            if first <= hour <= now:
                bucket = first + self.bucket_size * ((hour - first) // self.bucket_size)
                buckets[bucket] += amount
        return buckets


WINDOWS = (
    HistoryWindow("earnings_24h", "Salad earnings 24h", timedelta(hours=1), 24),
    HistoryWindow("earnings_7d", "Salad earnings 7d", timedelta(days=1), 7),
    HistoryWindow("earnings_30d", "Salad earnings 30d", timedelta(days=1), 30),
)
