import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def test_list_properties_scopes_to_caller_tenant():
    """The service query must bind tenant_id from the caller so a tenant never
    sees another tenant's properties (prop-001 exists in both tenants)."""
    from app.services import properties

    captured = {}

    async def execute(_query, params):
        captured["params"] = params
        row = MagicMock()
        row.id = "prop-001"
        row.name = "Beach House Alpha"
        row.timezone = "Europe/Paris"
        result = MagicMock()
        result.fetchall = MagicMock(return_value=[row])
        return result

    session = MagicMock()
    session.execute = execute
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.session_factory = True
    pool.initialize = AsyncMock()
    pool.get_session = AsyncMock(return_value=session)

    with patch("app.core.database_pool.DatabasePool", return_value=pool):
        result = asyncio.run(properties.list_properties_for_tenant("tenant-a"))

    assert captured["params"] == {"tenant_id": "tenant-a"}
    assert result == [
        {"id": "prop-001", "name": "Beach House Alpha", "timezone": "Europe/Paris"}
    ]
