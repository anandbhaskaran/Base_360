import json
import os
from typing import Any, Dict, Optional

import redis.asyncio as redis

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch revenue summary (lifetime by default; monthly when month/year given).
    Cache key is scoped by (tenant_id, property_id, period) to prevent leaks."""
    if month is not None and year is not None:
        cache_key = f"revenue:{tenant_id}:{property_id}:{year}-{month:02d}"
    else:
        cache_key = f"revenue:{tenant_id}:{property_id}"

    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.reservations import calculate_monthly_revenue, calculate_total_revenue

    if month is not None and year is not None:
        result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    else:
        result = await calculate_total_revenue(property_id, tenant_id)

    await redis_client.setex(cache_key, 300, json.dumps(result))
    return result
