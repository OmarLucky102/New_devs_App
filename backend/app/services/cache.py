import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os
from datetime import datetime, timezone

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if month is None or year is None:
        now = datetime.now(timezone.utc)
        month = month if month is not None else now.month
        year = year if year is not None else now.year

    # Scope the cache key to the tenant and period so one tenant can never be
    # served another tenant's revenue (or a different month for the same property).
    cache_key = f"revenue:{tenant_id}:{property_id}:{year}-{month:02d}"

    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_monthly_revenue
    
    # Calculate revenue for the requested month
    result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    
    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))
    
    return result
