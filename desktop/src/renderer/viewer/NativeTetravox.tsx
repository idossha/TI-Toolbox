import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../ui/Button";
import { openNativeScene } from "./native";
import type { TitNativeTetravoxProgress, TitNativeTetravoxStatus } from "../../shared/tit-bridge";

/** Short description of where an active TetraVox came from — used by the Settings card's Source
 * row and by the compact viewer embed's one-line status. */
export const SOURCE_LABEL: Record<NonNullable<TitNativeTetravoxStatus["source"]>, string> = {
  configured: "The application you chose",
  managed: "Installed for TI-Toolbox",
  system: "Your existing installation",
  path: "The TetraVox on your PATH",
};

function describe(status: TitNativeTetravoxStatus | undefined, pending: boolean): string {
  if (!status) return pending ? "Checking installation…" : "TetraVox is not installed.";
  if (!status.installed) return status.configuredPath && status.configuredPathValid === false ? "The chosen application is no longer a compatible TetraVox." : "TetraVox is not installed.";
  return `${SOURCE_LABEL[status.source ?? "managed"]}${status.version && status.version !== "system" ? ` · ${status.version}` : ""}`;
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
  const status = useQuery({ queryKey: ["native-tetravox"], queryFn: () => bridge!.nativeTetravoxStatus!(), enabled: !!bridge?.nativeTetravoxStatus });
  const refresh = { onSuccess: () => client.invalidateQueries({ queryKey: ["native-tetravox"] }) };
  const install = useMutation({ mutationFn: () => bridge!.installNativeTetravox!(), ...refresh });
  const update = useMutation({ mutationFn: () => bridge!.updateNativeTetravox!(), ...refresh });
  const check = useMutation({ mutationFn: () => bridge!.checkNativeTetravoxUpdate!(), ...refresh });
  const locate = useMutation({ mutationFn: () => bridge!.locateNativeTetravox!(), ...refresh });
  const forget = useMutation({ mutationFn: () => bridge!.clearNativeTetravoxPath!(), ...refresh });
  const open = useMutation({ mutationFn: () => openNativeScene(path ?? "") });

  useEffect(() => bridge?.onNativeTetravoxProgress?.(setProgress), [bridge]);

  const data = status.data;
  const busy = install.isPending || update.isPending || Boolean(data?.installing);
  const working = busy ? describeProgress(progress) ?? "Working…" : undefined;
  const failure = (open.error ?? install.error ?? update.error ?? check.error ?? locate.error ?? status.error)?.message ?? data?.error;

  return { bridge, data, pending: status.isPending, progress, busy, working, failure, install, update, check, locate, forget, open };
}

/** Compact embed used inline on the Viewer page — a status line plus a Launch/Install button, no
 * card chrome. The full Source/Version/Location layout lives in `TetravoxCard.tsx`. */
export function NativeTetravox({ path, compact = false }: { path?: string | null; compact?: boolean }) {
  const { bridge, data, pending, working, failure, install, update, locate, forget, open, busy } = useNativeTetravox(path);

  if (!bridge?.nativeTetravoxStatus) return <div><p className="field-help">Native TetraVox requires TI-Toolbox Desktop.</p>{path && <a href={`/api/files/raw${path.split("/").map(encodeURIComponent).join("/")}`} download>Download scene for TetraVox</a>}</div>;

  return <div style={{ padding: compact ? 0 : "var(--space-4)", display: "grid", gap: "var(--space-3)" }} data-testid="native-tetravox">
    {!compact && <p>TetraVox opens in its own native window.</p>}
    <p className="field-help">{describe(data, pending)}</p>
    {working && <p className="field-help" role="status">{working}</p>}
    {data?.installed && <Button onClick={() => open.mutate()} disabled={open.isPending}>{path ? "Open scene in TetraVox" : "Launch TetraVox"}</Button>}
    {data?.supported && !data.installed && <Button disabled={busy} onClick={() => install.mutate()}>{busy ? "Installing…" : "Install TetraVox"}</Button>}
    {data?.updateAvailable && <Button variant="secondary" disabled={busy} onClick={() => update.mutate()}>{`Update to ${data.updateAvailable}`}</Button>}
    {!compact && <Button variant="secondary" disabled={locate.isPending} onClick={() => locate.mutate()}>Locate TetraVox…</Button>}
    {!compact && data?.configuredPath && <>
      <code style={{ overflowWrap: "anywhere" }}>{data.configuredPath}</code>
      <Button variant="secondary" disabled={forget.isPending} onClick={() => forget.mutate()}>Use the automatic choice</Button>
    </>}
    {data && !data.supported && !data.installed && <p className="field-help">TI-Toolbox cannot install TetraVox on this platform. Install it yourself, then use Locate TetraVox…</p>}
    {failure && <p role="alert">{String(failure)}</p>}
    {path && <code style={{ overflowWrap: "anywhere" }}>{path}</code>}
  </div>;
}
