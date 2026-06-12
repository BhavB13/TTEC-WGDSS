from typing import Any


class RecommendationEngine:
    """
    Rule-based recommendation engine.

    Evaluates weather conditions and generation status
    to determine whether additional generation should
    be started.
    """

    def evaluate(
        self,
        weather: dict[str, Any],
        forecast: dict[str, Any],
        grid_status: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a recommendation based on
        weather and grid conditions.
        """

        probability = 0.5
        reasons: list[str] = []

        wind_speed = forecast.get("wind_speed_kph", 0)
        reserve_margin = grid_status.get("reserve_margin_percent", 100)

        if wind_speed > 20:
            probability += 0.15
            reasons.append(
                "Elevated forecast wind speed detected."
            )

        if reserve_margin < 20:
            probability += 0.25
            reasons.append(
                "Reserve margin below operating threshold."
            )

        if probability >= 0.70:
            recommendation = "START"
        elif probability >= 0.50:
            recommendation = "MONITOR"
        else:
            recommendation = "NO_ACTION"

        return {
            "probability_score": round(probability, 2),
            "recommendation": recommendation,
            "reason": " ".join(reasons),
        }