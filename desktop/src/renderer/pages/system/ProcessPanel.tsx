/**
 * The process table, htop-shaped: everything running inside the container, busiest first, with
 * what each process *belongs to*.
 *
 * Two decisions worth stating.
 *
 * **It lists everything, not a keyword allowlist.** The old Host tab showed only processes whose
 * name matched a list of tools TI-Toolbox spawns, which meant the one process actually eating the
 * CPU was invisible whenever it was not on the list. The keyword match survives as a `toolbox`
 * marker on the row.
 *
 * **The stop affordance is only on owned rows.** A process the server can attribute to a job or a
 * kernel can be stopped *through that job's own cancel*, which unwinds its lock, its events and
 * its sibling containers. An unowned pid has no such path, and a monitoring page has no business
 * offering to raw-kill an arbitrary process inside the container — so those rows simply have no
 * button. (`POST /api/system/terminate` still exists, keyword-gated, for the Host tab.)
 */
import { useMemo, useState } from "react";
import { Square } from "lucide-react";
import type { SystemSnapshot } from "../../api/client";
import { IconButton } from "../../ui/Button";
import { AlertDialog } from "../../ui/Overlay";
import { Skeleton } from "../../ui/Feedback";
import { bytes } from "../../ui/utils";
import { isStoppable, metricsOf, sortProcesses, type Process, type ProcessSort } from "./model";
import { Panel } from "./parts";

const COLUMNS: { id: ProcessSort; label: string; numeric?: boolean }[] = [
  { id: "pid", label: "PID", numeric: true },
  { id: "name", label: "Process" },
  { id: "cpu", label: "CPU", numeric: true },
  { id: "mem", label: "MEM", numeric: true },
];

export function ProcessPanel({
  snapshot,
  onStop,
}: {
  snapshot: SystemSnapshot | undefined;
  /** Stops the job or kernel a row belongs to. Never a raw kill. */
  onStop: (process: Process) => void;
}) {
  const [sort, setSort] = useState<ProcessSort>("cpu");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<Process | null>(null);

  const rows = useMemo(() => sortProcesses(snapshot?.processes ?? [], sort), [snapshot?.processes, sort]);
  const total = snapshot?.process_total ?? rows.length;

  return (
    <Panel
      title="Processes"
      // The count, not a cap. "top 3 of 4" told the reader they were being shown a selection when
      // they were being shown everything; the server's limit is high enough that a truncation is
      // the exception, and it says so only when it actually happens.
      aside={total > rows.length ? `${rows.length} of ${total}` : `${rows.length}`}
      className="system-panel-processes"
      testId="system-processes"
      metrics={metricsOf("processes")}
    >
      {!snapshot ? (
        <Skeleton rows={8} />
      ) : (
        <div className="system-proc-scroll">
          <table className="system-proc">
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c.id} data-align={c.numeric ? "right" : undefined}>
                    <button
                      type="button"
                      className="system-proc-sort"
                      data-active={sort === c.id || undefined}
                      onClick={() => setSort(c.id)}
                      aria-pressed={sort === c.id}
                    >
                      {c.label}
                    </button>
                  </th>
                ))}
                <th>Owner</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const open = expanded === p.pid;
                return (
                  <tr key={p.pid} data-toolbox={p.relevant || undefined} data-owned={p.owner_kind ?? undefined}>
                    <td className="system-proc-num tabular-nums">{p.pid}</td>
                    <td>
                      {/* The command line is the useful part and never fits: the name is always
                          shown, and clicking the row reveals the full command in place rather
                          than in a tooltip nobody can copy out of. */}
                      <button
                        type="button"
                        className="system-proc-name"
                        onClick={() => setExpanded(open ? null : p.pid)}
                        aria-expanded={open}
                      >
                        <span className="system-proc-strong">{p.name}</span>
                        <span className={open ? "system-proc-cmd system-proc-cmd-open mono" : "system-proc-cmd mono"}>
                          {p.cmdline || "—"}
                        </span>
                      </button>
                    </td>
                    <td className="system-proc-num tabular-nums" data-hot={p.cpu_percent >= 75 || undefined}>
                      {p.cpu_percent.toFixed(1)}
                    </td>
                    <td className="system-proc-num tabular-nums">{bytes(p.rss)}</td>
                    <td className="system-proc-owner text-caption">
                      {p.owner_label || (p.relevant ? "toolbox" : "")}
                    </td>
                    <td className="system-proc-action">
                      {isStoppable(p) && (
                        <IconButton
                          aria-label={`Stop ${p.owner_label || p.name}`}
                          size="sm"
                          variant="destructive"
                          icon={<Square size={12} />}
                          onClick={() => setConfirm(p)}
                        />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length === 0 && <p className="system-note text-caption">No processes reported.</p>}
        </div>
      )}

      <AlertDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.owner_kind === "kernel" ? "Stop kernel" : "Stop job"}
        description={
          confirm
            ? `Stop ${confirm.owner_label || confirm.name}? This stops the whole ${
                confirm.owner_kind === "kernel" ? "kernel" : "job"
              }, not just pid ${confirm.pid}, and any work in progress is abandoned.`
            : ""
        }
        confirmLabel={confirm?.owner_kind === "kernel" ? "Stop kernel" : "Stop job"}
        onConfirm={() => {
          if (confirm) onStop(confirm);
          setConfirm(null);
        }}
      />
    </Panel>
  );
}