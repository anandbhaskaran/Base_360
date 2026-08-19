import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException


def _fake_pool_with_session(execute_impl):
    """Build a DatabasePool double whose sessions call execute_impl(query, params)."""
    session = MagicMock()
    session.execute = execute_impl
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.session_factory = True
    pool.initialize = AsyncMock()
    pool.get_session = AsyncMock(return_value=session)
    return pool


def test_calculate_total_revenue_raises_503_when_pool_unavailable():
    """DB pool without session_factory must raise 503, not fake mock data."""
    from app.services import reservations

    class FakePool:
        session_factory = None

        async def initialize(self):
            pass

    with patch("app.core.database_pool.DatabasePool", FakePool):
        try:
            asyncio.run(reservations.calculate_total_revenue("prop-001", "tenant-a"))
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("expected HTTPException(503), got a result (mock leaked through)")


def test_calculate_monthly_revenue_uses_property_timezone_bounds():
    """A reservation at 2024-02-29 23:30 UTC (= 2024-03-01 00:30 Europe/Paris)
    must count as March for a Paris property. The SUM query must be bound
    with tz-aware datetimes in the property's timezone."""
    from app.services import reservations

    executed = []

    async def execute(query, params):
        executed.append((str(query), params))
        row = MagicMock()
        if "properties" in str(query).lower():
            row.timezone = "Europe/Paris"
        else:
            row.total_revenue = Decimal("1250.000")
            row.reservation_count = 1
        result = MagicMock()
        result.fetchone = MagicMock(return_value=row)
        return result

    pool = _fake_pool_with_session(execute)

    with patch("app.core.database_pool.DatabasePool", return_value=pool):
        result = asyncio.run(
            reservations.calculate_monthly_revenue("prop-001", "tenant-a", 3, 2024)
        )

    assert len(executed) == 2, "expected a property-tz lookup then a SUM query"
    _, sum_params = executed[1]
    paris = ZoneInfo("Europe/Paris")
    assert sum_params["start"] == datetime(2024, 3, 1, tzinfo=paris)
    assert sum_params["end"] == datetime(2024, 4, 1, tzinfo=paris)
    assert result["total"] == "1250.000"
    assert result["count"] == 1


def test_calculate_monthly_revenue_handles_december_year_rollover():
    """December → January bounds must roll the year forward."""
    from app.services import reservations

    executed = []

    async def execute(query, params):
        executed.append((str(query), params))
        row = MagicMock()
        if "properties" in str(query).lower():
            row.timezone = "America/New_York"
        else:
            row.total_revenue = None
            row.reservation_count = 0
        result = MagicMock()
        result.fetchone = MagicMock(return_value=row)
        return result

    pool = _fake_pool_with_session(execute)

    with patch("app.core.database_pool.DatabasePool", return_value=pool):
        result = asyncio.run(
            reservations.calculate_monthly_revenue("prop-004", "tenant-b", 12, 2024)
        )

    ny = ZoneInfo("America/New_York")
    _, sum_params = executed[1]
    assert sum_params["start"] == datetime(2024, 12, 1, tzinfo=ny)
    assert sum_params["end"] == datetime(2025, 1, 1, tzinfo=ny)
    assert result["total"] == "0.00"
    assert result["count"] == 0
