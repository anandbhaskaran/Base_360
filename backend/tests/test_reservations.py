import asyncio
from unittest.mock import patch

from fastapi import HTTPException


def test_calculate_total_revenue_raises_503_when_pool_unavailable():
    """When the DB pool can't provide a session, we must surface HTTPException(503).
    The old code returned hardcoded per-property mock totals, silently misleading finance."""
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
