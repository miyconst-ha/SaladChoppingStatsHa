"""Read-only client for the Salad dashboard API."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from json import loads
import re
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout

API_URL = "https://app-api.salad.com"
COOKIE_VALUE = re.compile(r"[!#-+\--:<-\[\]-~]+")


class SaladError(Exception):
    """Salad could not supply usable data."""


class SaladAuthError(SaladError):
    """Salad rejected the session cookie."""


@dataclass(frozen=True)
class Machine:
    """A Salad machine and its reported lifetime earnings."""

    name: str
    lifetime_earnings: Decimal


@dataclass(frozen=True)
class Earnings:
    """An account balance and the machines returned by Salad."""

    balance: Decimal
    machines: dict[str, Machine]


def money(value: object) -> Decimal:
    """Parse a Salad amount without rounding sub-cent earnings."""
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise SaladError("Salad returned an invalid amount") from None
    if not amount.is_finite():
        raise SaladError("Salad returned a non-finite amount")
    return amount


class SaladClient:
    """Fetch Salad data using a dashboard session cookie."""

    def __init__(self, session: ClientSession, cookie: str) -> None:
        if not COOKIE_VALUE.fullmatch(cookie):
            raise SaladAuthError("Invalid Salad cookie format")
        self._session = session
        self._cookie = cookie

    async def _get(self, path: str, *, xsrf: str | None = None) -> dict:
        headers = {"Cookie": f"auth={self._cookie}", "Accept": "application/json"}
        if xsrf is not None:
            headers["X-XSRF-TOKEN"] = xsrf
        try:
            async with self._session.get(
                f"{API_URL}{path}",
                headers=headers,
                allow_redirects=False,
                timeout=ClientTimeout(total=15),
            ) as response:
                if response.status in (401, 403):
                    raise SaladAuthError("Salad rejected the session cookie")
                if response.status != 200:
                    raise SaladError(f"Salad returned HTTP {response.status}")
                payload = await response.json(
                    loads=lambda body: loads(body, parse_float=Decimal)
                )
        except (ClientError, TimeoutError, ValueError):
            raise SaladError("Could not read the Salad response") from None
        if not isinstance(payload, dict):
            raise SaladError("Salad returned an unexpected response")
        return payload

    async def account_id(self) -> str:
        """Get the stable account identifier for setup and reauthentication."""
        profile = await self._get("/api/v1/profile", xsrf="1")
        account_id = profile.get("id")
        if not isinstance(account_id, str) or not account_id:
            raise SaladError("Salad did not return an account ID")
        return account_id

    async def earnings(self) -> Earnings:
        """Get the account balance and lifetime earnings per machine."""
        balance = await self._get("/api/v1/profile/balance", xsrf=self._cookie)
        items = (await self._get("/api/v2/machines")).get("items")
        if not isinstance(items, list):
            raise SaladError("Salad did not return a machine list")

        machines = {}
        for item in items:
            machine_id = item.get("machine_id") if isinstance(item, dict) else None
            if not isinstance(machine_id, str) or not machine_id:
                raise SaladError("Salad returned a machine without an ID")
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                name = machine_id
            machines[machine_id] = Machine(name, money(item.get("lifetime_balance")))
        return Earnings(money(balance.get("currentBalance")), machines)

    async def hourly_history(self, machines: dict[str, Machine]) -> dict[datetime, Decimal]:
        """Read and combine Salad's hourly history for the listed machines."""
        hourly: dict[datetime, Decimal] = {}
        for machine_id in machines:
            payload = await self._get(
                f"/api/v2/machines/{quote(machine_id, safe='')}/earning-history?timeframe=30d"
            )
            entries = payload.get("earnings")
            if not isinstance(entries, dict):
                raise SaladError("Salad did not return earnings history")

            for timestamp, value in entries.items():
                try:
                    start = datetime.fromisoformat(timestamp)
                except ValueError:
                    raise SaladError("Salad returned an invalid earnings timestamp") from None
                if start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
                hour = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
                hourly[hour] = hourly.get(hour, Decimal(0)) + money(value)
        return hourly
