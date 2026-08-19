from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import authenticate_request as get_current_user
from app.services.properties import list_properties_for_tenant

router = APIRouter()


@router.get("/properties")
async def get_properties(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    items: List[Dict[str, Any]] = await list_properties_for_tenant(tenant_id)
    return {"items": items, "total": len(items)}
