/** The nav rail's Jobs-row count of plans waiting for the user, and the toast when one arrives. */
import { useProposalToasts, useProposals } from "./api";
import { pendingCount } from "./model";
import "./proposals.css";

export function PendingProposalsBadge() {
  const proposals = useProposals();
  useProposalToasts(proposals);
  const count = pendingCount(proposals);
  if (count === 0) return null;
  const label = count === 1 ? "1 plan waiting for your approval" : `${count} plans waiting for your approval`;
  return (
    <span className="nav-badge tabular-nums" data-testid="nav-proposals-badge" title={label} aria-label={label}>
      {count}
    </span>
  );
}
