import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../ui/Button";
import { openNativeScene } from "./native";
import type { TitNativeTetravoxProgress, TitNativeTetravoxStatus } from "../../shared/tit-bridge";

/** The only TetraVox TI-Toolbox launches is the one it installed itself (decision 2026-09-22). */
export const SOURCE_LABEL = "Installed by TI-Toolbox";

function describe(status: TitNativeTetravoxStatus | undefined, pending: boolean): string {
  if (!status) return pending ? "Checking installation…" : "TetraVox is not installed.";
  if (status.installing) return "Setting up TetraVox…";
  if (!status.installed) return "TetraVox is not installed.";
  return `${SOURCE_LABEL}${status.version ? ` · ${status.version}` : ""}`;
}

export function describeProgress(progress: TitNativeTetravoxProgress): string | undefined {
  if (progress.phase === "idle") return undefined;
  if (progress.phase === "install") return "Installing…";
  const megabytes = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(0)} MB`;
  return progress.total ? `Downloading ${megabytes(progress.received ?? 0)} of ${megabytes(progress.total)}…` : `Downloading ${megabytes(progress.received ?? 0)}…`;
}

/**
 * Shared query/mutation wiring behind both the compact viewer embed (`NativeTetravox`) and the
 * full Settings card (`TetravoxCard`), so the two never drift on how status is fetched, how a
 * download's progress is reported, or which error wins when several mutations can fail at once.
 */
export function useNativeTetravox(path?: string | null) {
  const client = useQueryClient();
  const bridge = window.tit;
  const [progress, setProgress] = useState<TitNativeTetravoxProgress>({ phase: "idle" });
  const status = useQuery({ queryKey: ["native-tetravox"], queryFn: () => bridge!.nativeTetravoxStatus!(), enabled: !!bridge?.nativeTetravoxStatus, refetchInterval: (query) => query.state.data?.installing ? 1000 : false });
  const refresh = { onSuccess: () => client.invalidateQueries({ queryKey: ["native-tetravox"] }) };
  const install = useMutation({ mutationFn: () => bridge!.installNativeTetravox!(), ...refresh });
  const update = useMutation({ mutationFn: () => bridge!.updateNativeTetravox!(), ...refresh });
  const open = useMutation({ mutationFn: () => openNativeScene(path ?? "") });

  useEffect(() => bridge?.onNativeTetravoxProgress?.((next) => {
    setProgress(next);
    if (next.phase === "idle") void client.invalidateQueries({ queryKey: ["native-tetravox"] });
  }), [bridge, client]);

  const data = status.data;
  const busy = install.isPending || update.isPending || Boolean(data?.installing);
  const working = busy ? describeProgress(progress) ?? "Setting up TetraVox…" : undefined;
  const failure = (open.error ?? install.error ?? update.error ?? status.error)?.message ?? data?.error;

  return { bridge, data, pending: status.isPending, progress, busy, working, failure, install, update, open };
}

/** Compact embed used inline on the Viewer page — a status line plus a Launch/Retry button, no
 * card chrome. The full Version/Location layout lives in `TetravoxCard.tsx`. */
export function NativeTetravox({ path, compact = false }: { path?: string | null; compact?: boolean }) {
  const { bridge, data, pending, working, failure, install, open, busy } = useNativeTetravox(path);

  if (!bridge?.nativeTetravoxStatus) return <div><p className="field-help">Native TetraVox requires TI-Toolbox Desktop.</p>{path && <a href={`/api/files/raw${path.split("/").map(encodeURIComponent).join("/")}`} download>Download scene for TetraVox</a>}</div>;

  return <div style={{ padding: compact ? 0 : "var(--space-4)", display: "grid", gap: "var(--space-3)" }} data-testid="native-tetravox">
    {!compact && <p>TetraVox opens in its own native window.</p>}
    <p className="field-help">{describe(data, pending)}</p>
    {working && <p className="field-help" role="status">{working}</p>}
    {data?.installed && <Button onClick={() => open.mutate()} disabled={open.isPending}>{path ? "Open scene in TetraVox" : "Launch TetraVox"}</Button>}
    {data?.supported && !data.installed && <Button disabled={busy} onClick={() => install.mutate()}>{busy ? "Installing…" : "Retry setup"}</Button>}
    {data && !data.supported && !data.installed && <p className="field-help">TI-Toolbox has no TetraVox package for this platform.</p>}
    {failure && <p role="alert">{String(failure)}</p>}
    {path && <code style={{ overflowWrap: "anywhere" }}>{path}</code>}
  </div>;
}
