import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

async def calculate_monthly_revenue(property_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month.
    """

    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)
        
    print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date}")

    # SQL Simulation (This would be executed against the actual DB)
    query = """
        SELECT SUM(total_amount) as total
        FROM reservations
        WHERE property_id = $1
        AND tenant_id = $2
        AND check_in_date >= $3
        AND check_in_date < $4
    """
    
    # In production this query executes against a database session.
    # result = await db.fetch_val(query, property_id, tenant_id, start_date, end_date)
    # return result or Decimal('0')
    
    return Decimal('0') # Placeholder for now until DB connection is finalized

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
