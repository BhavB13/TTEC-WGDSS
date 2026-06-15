interface RecommendationHistoryItem {
  timestamp: string;
  recommendation: string;
  confidence: number;
}

interface RecommendationHistoryTableProps {
  history: RecommendationHistoryItem[];
}

export default function RecommendationHistoryTable({
  history,
}: RecommendationHistoryTableProps) {
  return (
    <div>
      <h2>Recommendation History</h2>

      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Recommendation</th>
            <th>Confidence</th>
          </tr>
        </thead>

        <tbody>
          {history.map((item) => (
            <tr key={item.timestamp}>
              <td>{item.timestamp}</td>
              <td>{item.recommendation}</td>
              <td>{item.confidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}