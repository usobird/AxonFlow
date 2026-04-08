"""系统状态 API"""

from fastapi import APIRouter
from axonflow.api.deps import get_engine

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
async def get_status():
    engine = get_engine()
    return engine.status()
