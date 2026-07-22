from fastapi import APIRouter, HTTPException

from app.schemas.capacity_plan import (
    CapacityPlanEvaluateRequest,
    CapacityPlanResponse,
)
from app.services.capacity_planning_service import (
    CapacityPlanContextExpired,
    CapacityPlanContextNotFound,
    InvalidCapacityPlan,
    capacity_planning_service,
)


router = APIRouter()


@router.post(
    "/capacity-plan/evaluate",
    response_model=CapacityPlanResponse,
)
async def evaluate_capacity_plan(
    request: CapacityPlanEvaluateRequest,
) -> CapacityPlanResponse:
    """Evaluate an app-local what-if plan; this endpoint cannot control SCADA."""

    try:
        return capacity_planning_service.evaluate_what_if(request)
    except CapacityPlanContextNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CapacityPlanContextExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidCapacityPlan as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
