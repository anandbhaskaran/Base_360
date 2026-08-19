import asyncio
from unittest.mock import patch


def test_cache_key_scopes_by_tenant():
    """prop-001 exists for both tenant-a and tenant-b (composite PK in schema.sql).
    A cached revenue payload for one tenant must never be served to the other."""
    from app.services import cache

    storage: dict = {}

    async def fake_get(key):
        return storage.get(key)

    async def fake_setex(key, _ttl, value):
        storage[key] = value
        return True

    calls: list = []

    async def fake_calculate(property_id, tenant_id):
        calls.append(tenant_id)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": f"{tenant_id}-total",
            "currency": "USD",
            "count": 1,
        }

    fake_redis = type("R", (), {"get": staticmethod(fake_get), "setex": staticmethod(fake_setex)})()

    async def scenario():
        with (
            patch.object(cache, "redis_client", fake_redis),
            patch("app.services.reservations.calculate_total_revenue", fake_calculate),
        ):
            first = await cache.get_revenue_summary("prop-001", "tenant-a")
            second = await cache.get_revenue_summary("prop-001", "tenant-b")
        return first, second

    first, second = asyncio.run(scenario())

    assert first["total"] == "tenant-a-total"
    assert second["total"] == "tenant-b-total", "tenant-b got tenant-a's cached value"
    assert calls == ["tenant-a", "tenant-b"], "cache short-circuited tenant-b's fresh compute"
