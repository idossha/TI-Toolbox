import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../ui/Button";
import { openNativeScene } from "./native";

export function NativeTetravox({ path }: { path?: string | null }) {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["native-tetravox"], queryFn: () => window.tit!.nativeTetravoxStatus!(), enabled: !!window.tit?.nativeTetravoxStatus });
  const install = useMutation({ mutationFn: () => window.tit!.installNativeTetravox!(), onSuccess: () => client.invalidateQueries({ queryKey: ["native-tetravox"] }) });
  const open = useMutation({ mutationFn: () => openNativeScene(path ?? "") });
  if (!window.tit?.nativeTetravoxStatus) return <div><p className="field-help">Native TetraVox requires TI-Toolbox Desktop.</p>{path && <a href={`/api/files/raw${path.split("/").map(encodeURIComponent).join("/")}`} download>Download scene for TetraVox</a>}</div>;
  return <div style={{ padding: "var(--space-4)", display: "grid", gap: "var(--space-3)" }} data-testid="native-tetravox">
    <p>TetraVox opens in its own native window.</p>
    <p className="field-help">{status.data?.installed ? `Installed${status.data.version ? ` · ${status.data.version}` : ""}` : status.isPending ? "Checking installation…" : "TetraVox is not installed."}</p>
    {status.data?.supported && !status.data.installed && <Button disabled={install.isPending || status.data.installing} onClick={() => install.mutate()}>{install.isPending ? "Installing…" : "Install TetraVox"}</Button>}
    {status.data?.installed && <Button onClick={() => open.mutate()} disabled={open.isPending}>Open {path ? "scene in " : ""}TetraVox</Button>}
    {status.data && !status.data.supported && <p className="field-help">Native TetraVox is unavailable on this platform.</p>}
    {(status.error || install.error || open.error || status.data?.error) && <p role="alert">{String((open.error ?? install.error ?? status.error)?.message ?? status.data?.error)}</p>}
    {path && <code style={{ overflowWrap: "anywhere" }}>{path}</code>}
    <p className="field-help">Use TetraVox to adjust the view and save camera or appearance changes.</p>
  </div>;
}
