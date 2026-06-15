import { GridStatus } from "../types/dashboard";

interface GridStatusCardProps {
  gridStatus: GridStatus;
}

export default function GridStatusCard({
  gridStatus,
}: GridStatusCardProps) {
  return (
    <div>
      <h2>Grid Status</h2>

      <p>
        Available Capacity:
        {gridStatus.total_available_capacity_mw} MW
      </p>

      <p>
        Generation:
        {gridStatus.total_generation_mw} MW
      </p>

      <p>
        Reserve Margin:
        {gridStatus.reserve_margin_percent}%
      </p>

      <p>Status: {gridStatus.grid_status}</p>
    </div>
  );
}