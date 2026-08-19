import asyncio
from unittest.mock import patch


def _fake_redis():
    """Tiny in-memory redis double with get/setex."""
    storage: dict = {}

    async def fake_get(key):
        return storage.get(key)

    async def fake_setex(key, _ttl, value):
        storage[key] = value
        return True

    return storage, type("R", (), {"get": staticmethod(fake_get), "setex": staticmethod(fake_setex)})()


def test_cache_key_scopes_by_tenant():
    """prop-001 exists for both tenant-a and tenant-b (composite PK in schema.sql).
    A cached revenue payload for one tenant must never be served to the other."""
    from app.services import cache

    _, fake_redis = _fake_redis()
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


def test_cache_key_scopes_by_month_year():
    """Same (tenant, property) with different months must not collide.
    March cache must not be served to an April request."""
    from app.services import cache

    storage, fake_redis = _fake_redis()

    async def fake_monthly(property_id, tenant_id, month, year):
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": f"{year}-{month:02d}-total",
            "currency": "USD",
            "count": 1,
        }

    async def scenario():
        with (
            patch.object(cache, "redis_client", fake_redis),
            patch("app.services.reservations.calculate_monthly_revenue", fake_monthly),
        ):
            march = await cache.get_revenue_summary("prop-001", "tenant-a", month=3, year=2024)
            april = await cache.get_revenue_summary("prop-001", "tenant-a", month=4, year=2024)
        return march, april

    march, april = asyncio.run(scenario())

    assert march["total"] == "2024-03-total"
    assert april["total"] == "2024-04-total"
    assert len(storage) == 2, "different months must produce distinct cache keys"
