/**
 * The Host tab — everything `pages/system` was (plan §2: "System's charts/process table = Host
 * tab"). It kept every API call: the `/ws/system` snapshot stream (`ws/useSystemStream`, imported
 * and never edited by this lane) and `POST /api/system/terminate`.
 *
 * What changed is the geometry, not the content. `pages/system` spent a page header plus three
 * `Card`s on three numbers; here the numbers live in one 28px strip of stat cells with sparklines,
 * so the process table — the part you actually read — gets the height.
 */
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Server, XCircle } from "lucide-react";
import { useSystemStream } from "../../../ws/useSystemStream";
import { IconButton } from "../../../ui/Button";
import { DataTable, type DataTableColumn } from "../../../ui/DataTable";
import { Sparkline } from "../../../ui/Chart";
import { EmptyState, Skeleton } from "../../../ui/Feedback";
import { AlertDialog } from "../../../ui/Overlay";
import { StatusDot } from "../../../ui/Status";
import { notify } from "../../../ui/Toast";
import { bytes, pct } from "../../../ui/utils";
import { ApiError } from "../../../api/client";
import { terminateProcess } from "./api";

interface ProcessRow {
  pid: number;
  name: string;
  cmdline?: string;
  cpu_percent: number;
  rss: number;
}

function StatCell({
  label,
  value,
  detail,
  values,
  color,
  testId,
}: {
  label: string;
  value: string;
  detail: string;
  values: number[];
  color?: string;
  testId: string;
}) {
  return (
    <div className="host-stat">
      <span className="text-eyebrow host-stat-label">{label}</span>
      <span className="host-stat-value tabular-nums" data-testid={testId}>
        {value}
      </span>
      <Sparkline values={values} color={color} height={18} width={72} />
      <span className="host-stat-detail text-caption tabular-nums">{detail}</span>
    </div>
  );
}

export function HostPanel() {
  const { status, samples } = useSystemStream();
  const queryClient = useQueryClient();
  const [confirmPid, setConfirmPid] = useState<number | null>(null);
  const latest = samples[samples.length - 1];

  const cpu = useMemo(() => samples.map((s) => s.cpu_percent), [samples]);
  const mem = useMemo(() => samples.map((s) => s.mem.percent), [samples]);
  const disk = useMemo(() => samples.map((s) => s.disk.percent), [samples]);

  const terminate = useMutation({
    mutationFn: terminateProcess,
    onSuccess: (_data, pid) => {
      notify.success(`Terminated process ${pid}.`);
      queryClient.invalidateQueries();
    },
    onError: (e) => notify.error("Could not terminate the process.", e instanceof ApiError ? e.message : String(e)),
  });

  const targetProcess = latest?.processes.find((p) => p.pid === confirmPid);

  const columns: DataTableColumn<ProcessRow>[] = [
    { header: "PID", numeric: true, accessorKey: "pid" },
    { header: "Name", accessorKey: "name" },
    {
      header: "Command",
      accessorKey: "cmdline",
      cell: ({ getValue }) => <span className="mono">{(getValue() as string | undefined) ?? ""}</span>,
    },
    { header: "CPU %", numeric: true, cell: ({ row }) => row.original.cpu_percent.toFixed(1) },
    { header: "RSS", numeric: true, cell: ({ row }) => bytes(row.original.rss) },
    {
      header: "",
      id: "actions",
      cell: ({ row }) => (
        <IconButton
          aria-label={`Terminate process ${row.original.pid}`}
          variant="destructive"
          size="sm"
          icon={<XCircle size={14} />}
          onClick={() => setConfirmPid(row.original.pid)}
        />
      ),
    },
  ];

  return (
    <div className="host-panel" data-testid="host-panel">
      <div className="host-stats">
        <StatCell
          label="CPU"
          value={pct(latest?.cpu_percent)}
          detail={latest ? `${latest.cpu_count} CPUs` : "—"}
          values={cpu}
          testId="cpu-value"
        />
        <StatCell
          label="Memory"
          value={pct(latest?.mem.percent)}
          detail={latest ? `${bytes(latest.mem.used)} of ${bytes(latest.mem.total)}` : "—"}
          values={mem}
          color="var(--success)"
          testId="mem-value"
        />
        <StatCell
          label="Disk"
          value={pct(latest?.disk.percent, 0)}
          detail={latest ? `${bytes(latest.disk.free)} free of ${bytes(latest.disk.total)}` : "—"}
          values={disk}
          color="var(--warning)"
          testId="disk-value"
        />
        <div className="host-stat host-stat-siblings">
          <span className="text-eyebrow host-stat-label">
            <Server size={12} /> Docker siblings
          </span>
          <span className="host-stat-detail text-caption">
            Docker-outside-of-Docker containers (QSIPrep/QSIRecon) are not reported yet.
          </span>
        </div>
        <span className="host-ws-status" data-testid="ws-status">
          <StatusDot
            kind={status === "open" ? "success" : status === "reconnecting" ? "warning" : "neutral"}
            pulse={status === "reconnecting"}
            title={
              status === "open"
                ? "Live updates connected"
                : status === "reconnecting"
                  ? "Reconnecting to live updates…"
                  : "Live updates disconnected"
            }
          />
          <span className="text-caption">
            {status === "open" ? "Live" : status === "reconnecting" ? "Reconnecting…" : "Disconnected"}
          </span>
        </span>
      </div>

      <div className="host-processes" data-testid="process-table">
        {!latest ? (
          <Skeleton rows={5} />
        ) : latest.processes.length === 0 ? (
          <EmptyState variant="inline" message="No toolbox processes running." />
        ) : (
          <DataTable
            data={latest.processes}
            columns={columns}
            getRowId={(p) => String(p.pid)}
            emptyMessage="No toolbox processes running."
          />
        )}
      </div>

      <AlertDialog
        open={confirmPid !== null}
        onOpenChange={(open) => !open && setConfirmPid(null)}
        title="Terminate process"
        description={
          targetProcess
            ? `Terminate PID ${targetProcess.pid} (${targetProcess.name})? This cannot be undone and may abandon in-progress work.`
            : "Terminate this process? This cannot be undone."
        }
        confirmLabel="Terminate process"
        onConfirm={() => {
          if (confirmPid !== null) terminate.mutate(confirmPid);
          setConfirmPid(null);
        }}
      />
    </div>
  );
}
