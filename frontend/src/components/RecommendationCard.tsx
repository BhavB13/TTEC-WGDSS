import { Recommendation } from "../types/dashboard";

interface RecommendationCardProps {
  recommendation: Recommendation;
}

export default function RecommendationCard({
  recommendation,
}: RecommendationCardProps) {
  return (
    <div>
      <h2>Recommendation</h2>

      <p>
        Action:
        {recommendation.recommendation}
      </p>

      <p>
        Confidence:
        {recommendation.probability_score}
      </p>

      <p>
        Reason:
        {recommendation.reason}
      </p>
    </div>
  );
}
