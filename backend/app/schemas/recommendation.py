from pydantic import BaseModel


class RecommendationResponse(BaseModel):
    """
    Response model for recommendation results.
    """

    probability_score: float
    recommendation: str
    reason: str