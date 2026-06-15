from pydantic import BaseModel


class GridStatusResponse(BaseModel):
    total_available_capacity_mw: float
    total_generation_mw: float
    reserve_margin_percent: float
    grid_status: str