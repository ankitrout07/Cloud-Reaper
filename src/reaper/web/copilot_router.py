# src/reaper/web/copilot_router.py
from functools import lru_cache
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from reaper.engine.copilot.engine import KnapsackCopilotEngine

copilot_router = APIRouter()


@lru_cache(maxsize=1)
def get_engine():
    return KnapsackCopilotEngine()


@copilot_router.post("/api/v1/copilot/optimize")
async def process_optimization_request(payload: dict[str, Any] | None = None):
    payload = payload or {}
    provider = payload.get("provider", "azure").strip().lower()
    user_intent = payload.get("intent", "").strip()
    budget_limit = payload.get("budget_cap")

    if not user_intent or budget_limit is None:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Missing mandatory params: 'intent' and 'budget_cap'.",
            },
        )

    try:
        budget_float = float(budget_limit)
        engine = get_engine()
        optimized_result = engine.compile_max_performance_infrastructure(
            cloud_provider=provider, user_intent=user_intent, budget_limit=budget_float
        )
        return {"status": "success", "blueprint": optimized_result.model_dump()}

    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Invalid type constraint: 'budget_cap' must be a numeric value.",
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Pipeline Execution Fault: {e!s}"},
        )
