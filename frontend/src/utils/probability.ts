export function formatRiskProbability(score: number): string {
  const percent = Math.max(0, Math.min(1, score)) * 100;

  if (percent === 0) {
    return "0.000%";
  }
  if (percent < 0.001) {
    return "<0.001%";
  }
  if (percent < 0.01) {
    return `${percent.toFixed(3)}%`;
  }
  if (percent < 1) {
    return `${percent.toFixed(2)}%`;
  }
  return `${percent.toFixed(1)}%`;
}
