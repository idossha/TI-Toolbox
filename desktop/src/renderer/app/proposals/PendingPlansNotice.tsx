/**
 * Plans waiting for the user, outside the Jobs page (the Overview): one compact line per pending
 * plan — who proposes what — and Review, which opens Jobs at that plan's card. The same
 * `useProposals` data the nav badge counts; the card itself is only ever on Jobs.
 */
import { useNavigate } from "react-router-dom";
import { Bot } from "lucide-react";
import { Button } from "../../ui/Button";
import { useProposals } from "./api";
import { proposer } from "./model";
import "./proposals.css";

export function PendingPlansNotice() {
  const navigate = useNavigate();
  const pending = (useProposals() ?? []).filter((p) => p.status === "pending");
  if (pending.length === 0) return null;
  return (
    <ul className="pending-plans" data-testid="pending-plans-notice" aria-label="Plans waiting for your approval">
      {pending.map((p) => (
        <li key={p.id} className="pending-plan">
          <Bot size={14} aria-hidden />
          <span className="pending-plan-text">
            {proposer(p)} proposes <strong>{p.title}</strong>
          </span>
          <Button size="sm" variant="secondary" onClick={() => navigate("/jobs", { state: { proposalId: p.id } })}>
            Review
          </Button>
        </li>
      ))}
    </ul>
  );
}
