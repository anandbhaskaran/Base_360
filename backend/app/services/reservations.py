import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


_PROPERTY_TZ_QUERY = text(
    "SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"
)

_MONTHLY_REVENUE_QUERY = text("""
    SELECT
        SUM(total_amount) AS total_revenue,
        COUNT(*) AS reservation_count
    FROM reservations
    WHERE property_id = :property_id
      AND tenant_id = :tenant_id
      AND check_in_date >= :start
      AND check_in_date < :end
""")


_MONTHLY_BREAKDOWN_QUERY = text("""
    SELECT
        EXTRACT(YEAR FROM (check_in_date AT TIME ZONE :tz))::int AS y,
        EXTRACT(MONTH FROM (check_in_date AT TIME ZONE :tz))::int AS m,
        SUM(total_amount) AS total,
        COUNT(*) AS count
    FROM reservations
    WHERE property_id = :property_id
      AND tenant_id = :tenant_id
    GROUP BY y, m
    ORDER BY y, m
""")


def _month_bounds(month: int, year: int, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Build a [start, end) window covering `month`/`year` in `tz`."""
    start = datetime(year, month, 1, tzinfo=tz)
    end_year = year + (1 if month == 12 else 0)
    end_month = 1 if month == 12 else month + 1
    end = datetime(end_year, end_month, 1, tzinfo=tz)
    return start, end


async def calculate_monthly_breakdown(
    property_id: str, tenant_id: str
) -> list[Dict[str, Any]]:
    """Return per-month revenue buckets for a property in its local timezone.
    Only months with activity are returned."""
    from app.core.database_pool import DatabasePool

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        logger.error("Revenue: database pool unavailable for %s/%s", property_id, tenant_id)
        raise HTTPException(status_code=503, detail="Revenue service unavailable")

    try:
        session = await db_pool.get_session()
        async with session:
            tz_result = await session.execute(
                _PROPERTY_TZ_QUERY,
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            tz_row = tz_result.fetchone()
            if tz_row is None:
                raise HTTPException(status_code=404, detail="Property not found")

            tz_name = tz_row.timezone or "UTC"
            rows = (
                await session.execute(
                    _MONTHLY_BREAKDOWN_QUERY,
                    {"property_id": property_id, "tenant_id": tenant_id, "tz": tz_name},
                )
            ).fetchall()
    except SQLAlchemyError as exc:
        logger.error("Revenue: DB error for %s/%s breakdown: %s", property_id, tenant_id, exc)
        raise HTTPException(status_code=503, detail="Revenue service unavailable")

    return [
        {
            "year": r.y,
            "month": r.m,
            "total": str(Decimal(str(r.total))),
            "count": r.count,
        }
        for r in rows
    ]


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int, year: int
) -> Dict[str, Any]:
    """Aggregate revenue for a property in a specific month, using the
    property's local timezone for the month boundaries."""
    from app.core.database_pool import DatabasePool

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        logger.error("Revenue: database pool unavailable for %s/%s", property_id, tenant_id)
        raise HTTPException(status_code=503, detail="Revenue service unavailable")

    try:
        session = await db_pool.get_session()
        async with session:
            tz_result = await session.execute(
                _PROPERTY_TZ_QUERY,
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            tz_row = tz_result.fetchone()
            if tz_row is None:
                raise HTTPException(status_code=404, detail="Property not found")

            tz = ZoneInfo(tz_row.timezone or "UTC")
            start, end = _month_bounds(month, year, tz)

            sum_result = await session.execute(
                _MONTHLY_REVENUE_QUERY,
                {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "start": start,
                    "end": end,
                },
            )
            row = sum_result.fetchone()
    except SQLAlchemyError as exc:
        logger.error("Revenue: DB error for %s/%s %d-%d: %s", property_id, tenant_id, year, month, exc)
        raise HTTPException(status_code=503, detail="Revenue service unavailable")

    if row is None or row.total_revenue is None:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": row.reservation_count if row else 0,
        }

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count,
    }

_REVENUE_QUERY = text("""
    SELECT
        property_id,
        SUM(total_amount) AS total_revenue,
        COUNT(*) AS reservation_count
    FROM reservations
    WHERE property_id = :property_id AND tenant_id = :tenant_id
    GROUP BY property_id
""")


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Aggregate revenue for a property from the database.

    Raises HTTPException(503) if the database is unavailable. Silent mock
    fallbacks were removed; finance cannot distinguish real numbers from mocks.
    """
    from app.core.database_pool import DatabasePool

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        logger.error("Revenue: database pool unavailable for %s/%s", property_id, tenant_id)
        raise HTTPException(status_code=503, detail="Revenue service unavailable")

    try:
        session = await db_pool.get_session()
        async with session:
            result = await session.execute(
                _REVENUE_QUERY,
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            row = result.fetchone()
    except SQLAlchemyError as exc:
        logger.error("Revenue: DB error for %s/%s: %s", property_id, tenant_id, exc)
        raise HTTPException(status_code=503, detail="Revenue service unavailable")

    if row is None:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0,
        }

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count,
    }
