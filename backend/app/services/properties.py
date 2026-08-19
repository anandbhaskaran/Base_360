import logging
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


_LIST_PROPERTIES_QUERY = text(
    "SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY name"
)


async def list_properties_for_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    """Return the caller tenant's properties (id, name, timezone)."""
    from app.core.database_pool import DatabasePool

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        logger.error("Properties: database pool unavailable for %s", tenant_id)
        raise HTTPException(status_code=503, detail="Properties service unavailable")

    try:
        session = await db_pool.get_session()
        async with session:
            result = await session.execute(_LIST_PROPERTIES_QUERY, {"tenant_id": tenant_id})
            rows = result.fetchall()
    except SQLAlchemyError as exc:
        logger.error("Properties: DB error for %s: %s", tenant_id, exc)
        raise HTTPException(status_code=503, detail="Properties service unavailable")

    return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in rows]
