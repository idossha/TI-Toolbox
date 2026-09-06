/**
 * One node on the canvas.
 *
 * The card is at the app's density (DESIGN §3.2/§3.3): a 20px header row of kind icon + name +
 * status chip, a two-line 12/16 summary, and — when the server says a required input is neither
 * wired nor set — one chip per unbound port. The chip is a button: it opens the node's editor at
 * that field, and wiring the port removes it, so a card always states what it is still missing
 * without the user having to read the receipt to find out.
 *
 * Port handles are typed and coloured by port type, with the port's name shown on hover, so a
 * handle never has to be guessed at from its position.
 */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { JobStateChip, type JobState } from "../../ui/Status";
import { KIND_ICON, KIND_TITLE, PORTS, PORT_LABEL, type NodeKind, type PortType } from "./graph";

export interface CardData extends Record<string, unknown> {
  kind: NodeKind;
  title: string;
  summary: string;
  state: JobState | null;
  invalid: boolean;
  /** Required inputs the server reported as unbound (`missing_input` issues), in port order. */
  needs: PortType[];
  onNeedClick: (nodeId: string, port: PortType) => void;
}

/** Vertical offset of one handle, so several ports of a kind do not overlap. */
const handleTop = (index: number, total: number) => `${((index + 1) / (total + 1)) * 100}%`;

export function NodeCard({ data, id }: NodeProps) {
  const card = data as CardData;
  const ports = PORTS[card.kind];
  const Icon = KIND_ICON[card.kind];
  const running = card.state === "running";

  return (
    <div
      className={`pipeline-card${card.invalid ? " is-invalid" : ""}${running ? " is-running" : ""}`}
      data-testid={`pipeline-node-${id}`}
      data-kind={card.kind}
      data-state={card.state ?? "none"}
    >
      {ports.inputs.map((port, i) => (
        <span key={`in-${port}`} className="pipeline-port-slot">
          <Handle
            type="target"
            id={port}
            position={Position.Left}
            style={{ top: handleTop(i, ports.inputs.length) }}
            className={`pipeline-handle port-${port}`}
            data-testid={`pipeline-in-${id}-${port}`}
          />
          <span className="pipeline-port pipeline-port-in" style={{ top: handleTop(i, ports.inputs.length) }} aria-hidden>
            {PORT_LABEL[port]}
          </span>
        </span>
      ))}

      {/* Icon + name + status, and nothing else. The kind's name used to be spelled out here too,
          which cost half the row and truncated the thing a user actually chose — the step's own
          name — to "Head ..." and "Measure the R...". The icon is the kind, and the `title` spells
          it out for anyone who needs the words. */}
      <div className="pipeline-card-head">
        <Icon size={14} aria-hidden />
        <span className="pipeline-card-name" title={`${card.title} — ${KIND_TITLE[card.kind]}`}>
          {card.title}
        </span>
        {card.state && <JobStateChip state={card.state} pulse={running} />}
      </div>

      <span className="pipeline-card-summary">{card.summary}</span>

      {card.needs.length > 0 && (
        <div className="pipeline-card-chips">
          {card.needs.map((port) => (
            <button
              key={port}
              type="button"
              className="pipeline-need nodrag"
              data-testid={`pipeline-need-${id}-${port}`}
              title={`${PORT_LABEL[port]} is required: wire it from an upstream step, or set it in this step's form.`}
              onClick={(e) => {
                e.stopPropagation();
                card.onNeedClick(id, port);
              }}
            >
              needs: {port}
            </button>
          ))}
        </div>
      )}

      {ports.outputs.map((port, i) => (
        <span key={`out-${port}`} className="pipeline-port-slot">
          <Handle
            type="source"
            id={port}
            position={Position.Right}
            style={{ top: handleTop(i, ports.outputs.length) }}
            className={`pipeline-handle port-${port}`}
            data-testid={`pipeline-out-${id}-${port}`}
          />
          <span className="pipeline-port pipeline-port-out" style={{ top: handleTop(i, ports.outputs.length) }} aria-hidden>
            {PORT_LABEL[port]}
          </span>
        </span>
      ))}
    </div>
  );
}
