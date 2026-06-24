from pydantic import BaseModel

from app.schemas.probability import ProbabilityResponse


class RecommendationResponse(ProbabilityResponse):
    recommendation: str
