from fastapi import APIRouter

from app.schemas.replay import ReplayControlRequest, ReplayStatusResponse
from app.services.demo_replay_service import DemoReplayService


router = APIRouter()
replay_service = DemoReplayService()


@router.get("/replay/status", response_model=ReplayStatusResponse)
def get_replay_status() -> ReplayStatusResponse:
    return replay_service.get_status()


@router.post("/replay/control", response_model=ReplayStatusResponse)
def control_replay(request: ReplayControlRequest) -> ReplayStatusResponse:
    return replay_service.control(request)
