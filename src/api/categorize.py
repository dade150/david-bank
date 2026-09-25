from fastapi import APIRouter

from src.services.categorize_service import categorize as categorize_service
from src.types.categorize import CategorizeRequest, CategorizeResponse

router = APIRouter(prefix="/api/ai", tags=["Categorize"])


@router.post("/categorize", response_model=CategorizeResponse)
async def categorize_endpoint(req: CategorizeRequest) -> CategorizeResponse:
    return await categorize_service(req)
