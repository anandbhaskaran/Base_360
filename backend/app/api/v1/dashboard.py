from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import authenticate_request as get_current_user
from app.services.cache import get_revenue_breakdown, get_revenue_summary

router = APIRouter()


@router.get("/dashboard/breakdown")
async def get_dashboard_breakdown(
    property_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    buckets = await get_revenue_breakdown(property_id, tenant_id)
    return {"property_id": property_id, "buckets": buckets}


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    if (month is None) != (year is None):
        raise HTTPException(status_code=400, detail="month and year must be provided together")

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)

    period = f"{year}-{month:02d}" if month is not None else "lifetime"

    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": float(revenue_data["total"]),
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "period": period,
    }
