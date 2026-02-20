from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.changes import router as changes_router
from app.api.connectors import router as connectors_router
from app.api.dashboard import router as dashboard_router
from app.api.graph import router as graph_router
from app.api.lab import router as lab_router
from app.api.policies import router as policies_router
from app.api.risk import router as risk_router
from app.api.simulation import router as simulation_router
from app.api.workflow import router as workflow_router
from app.services import llm_service

router = APIRouter(prefix="/v1")


@router.get("/status", tags=["system"])
async def status() -> dict[str, str]:
    return {"api": "up"}


@router.get("/llm-diag", tags=["system"])
async def llm_diagnostics():
    """Quick health check for LLM integration — no auth required."""
    import time
    from app.core.config import settings

    diag: dict = {
        "api_key_set": bool(settings.gemini_api_key),
        "api_key_prefix": settings.gemini_api_key[:12] + "..." if settings.gemini_api_key else None,
        "models": llm_service._MODEL_CANDIDATES,
        "is_available": llm_service.is_available(),
        "model_initialized": llm_service._model is not None,
    }

    # Quick test: send a tiny prompt and measure timing
    if llm_service.is_available():
        model = llm_service._get_model()
        if model:
            try:
                t0 = time.monotonic()
                response = await model.generate_content_async(
                    ["Return exactly: {\"status\": \"ok\"}"],
                    generation_config={
                        "temperature": 0.0,
                        "max_output_tokens": 64,
                        "response_mime_type": "application/json",
                    },
                )
                elapsed = time.monotonic() - t0
                text = response.text.strip() if hasattr(response, "text") else ""
                finish_reason = "N/A"
                if hasattr(response, "candidates") and response.candidates:
                    finish_reason = str(getattr(response.candidates[0], "finish_reason", "unknown"))
                diag["ping"] = {
                    "status": "ok",
                    "response": text[:200],
                    "elapsed_seconds": round(elapsed, 2),
                    "finish_reason": finish_reason,
                }
            except Exception as e:
                diag["ping"] = {
                    "status": "error",
                    "error": str(e)[:500],
                }
    return diag


router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(graph_router)
router.include_router(changes_router)
router.include_router(risk_router)
router.include_router(workflow_router)
router.include_router(connectors_router)
router.include_router(simulation_router)
router.include_router(policies_router)
router.include_router(lab_router)

api_router = APIRouter()
api_router.include_router(router)
