from fastapi import APIRouter

from app.api.lab import router as base_lab_router

router = APIRouter(prefix="/v1")
router.include_router(base_lab_router)
