from fastapi import APIRouter, HTTPException

from app.schemas.live_scada_experiment import (
    LiveScadaExperimentStatus,
    LiveScadaTestSession,
)
from app.services.live_scada_experiment_service import LiveScadaExperimentService


router = APIRouter(prefix="/experiments/live-scada-snapshot")


@router.get("/status", response_model=LiveScadaExperimentStatus)
def get_status() -> LiveScadaExperimentStatus:
    return LiveScadaExperimentService().status()


@router.get("/sessions/latest", response_model=LiveScadaTestSession)
def get_latest_session() -> LiveScadaTestSession:
    session = LiveScadaExperimentService().repository.latest()
    if session is None:
        raise HTTPException(status_code=404, detail="No experimental session exists")
    return session


@router.post("/sessions/run", response_model=LiveScadaTestSession)
async def run_session() -> LiveScadaTestSession:
    service = LiveScadaExperimentService()
    if not service.status().configured_source:
        raise HTTPException(
            status_code=409,
            detail="LIVE_SCADA_SNAPSHOT_PATH is not configured",
        )
    try:
        return await service.run()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
