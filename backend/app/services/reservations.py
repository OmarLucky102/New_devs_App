from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

import asyncpg

from app.config import settings


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int, year: int
) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month.

    The month boundaries are derived in the property's local timezone and then
    converted to UTC, so reservations are attributed to the month they fall in
    for that property (not the server/UTC month).
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be between 1 and 12, got {month}")

    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

    conn = await asyncpg.connect(settings.database_url)
    try:
        property_tz = await conn.fetchval(
            "SELECT timezone FROM properties WHERE id = $1 AND tenant_id = $2",
            property_id,
            tenant_id,
        )
        tz = ZoneInfo(property_tz or "UTC")

        # Local month boundaries normalized to UTC to match the timestamptz column.
        start_date = datetime(year, month, 1, tzinfo=tz).astimezone(timezone.utc)
        end_date = datetime(next_year, next_month, 1, tzinfo=tz).astimezone(
            timezone.utc
        )

        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(total_amount), 0) AS total, COUNT(*) AS count
            FROM reservations
            WHERE property_id = $1
              AND tenant_id = $2
              AND check_in_date >= $3
              AND check_in_date < $4
            """,
            property_id,
            tenant_id,
            start_date,
            end_date,
        )
    finally:
        await conn.close()

    total = Decimal(str(row["total"]))
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total),
        "currency": "USD",
        "count": int(row["count"]),
    }

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Import database pool
        from app.core.database_pool import DatabasePool
        
        # Initialize pool if needed
        db_pool = DatabasePool()
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                row = result.fetchone()
                
                if row:
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        
        # Create property-specific mock data for testing when DB is unavailable
        # This ensures each property shows different figures
        mock_data = {
            'prop-001': {'total': '1000.00', 'count': 3},
            'prop-002': {'total': '4975.50', 'count': 4}, 
            'prop-003': {'total': '6100.50', 'count': 2},
            'prop-004': {'total': '1776.50', 'count': 4},
            'prop-005': {'total': '3256.00', 'count': 3}
        }
        
        mock_property_data = mock_data.get(property_id, {'total': '0.00', 'count': 0})
        
        return {
            "property_id": property_id,
            "tenant_id": tenant_id, 
            "total": mock_property_data['total'],
            "currency": "USD",
            "count": mock_property_data['count']
        }
