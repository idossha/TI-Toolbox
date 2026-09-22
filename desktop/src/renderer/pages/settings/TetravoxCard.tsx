import { useQuery } from "@tanstack/react-query";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Chip, Progress, type SemanticKind } from "../../ui/Status";
import { SOURCE_LABEL, useNativeTetravox } from "../../viewer/NativeTetravox";
import type { TitNativeTetravoxStatus } from "../../../shared/tit-bridge";
import "./TetravoxCard.css";

function statusPill(data: TitNativeTetravoxStatus | undefined, pending: boolean): { kind: SemanticKind; label: string } {
  if (!data) return { kind: "neutral", label: pending ? "Checking…" : "Not installed" };
  if (data.installing) return { kind: "neutral", label: "Setting up…" };
  if (!data.installed) return { kind: "neutral", label: "Not installed" };
  return { kind: "success", label: `Installed ${data.version}` };
}

/**
 * Settings ▸ Viewer's TetraVox card. Same status/mutations as the compact viewer embed
 * (`useNativeTetravox` in `NativeTetravox.tsx`) laid out as `Field` rows to match the other
 * settings cards. There is exactly one TetraVox here: the copy TI-Toolbox installs for itself
 * (decision 2026-09-22) — no picker, no machine-wide search.
 */
export function TetravoxCard() {
  const { bridge, data, pending, progress, busy, working, failure, install, update, open } = useNativeTetravox();
  // Keyed on the installed version so a finished update asks again.
  const latest = useQuery({
    queryKey: ["native-tetravox-latest", data?.version],
    queryFn: () => bridge!.checkNativeTetravoxUpdate!(),
    enabled: !!data?.installed && !!bridge?.checkNativeTetravoxUpdate,
    staleTime: 10 * 60_000,
    retry: false,
  });

  if (!bridge?.nativeTetravoxStatus) {
    return (
      <Card>
        <CardHeader title="TetraVox" />
        <CardBody>
          <Field label="TetraVox">
            <span className="field-help">Requires the TI-Toolbox desktop app</span>
          </Field>
        </CardBody>
      </Card>
    );
  }

  const pill = statusPill(data, pending);
  const locationPath = data?.executable || data?.directory;
  const unsupported = data && !data.supported && !data.installed;

  return (
    <Card>
      <CardHeader title="TetraVox" actions={<Chip kind={pill.kind}>{pill.label}</Chip>} />
      <CardBody className="tetravox-card-body">
        <Field label="Version" note={SOURCE_LABEL}>
          <div className="tetravox-row-value">
            <span>{data?.installed ? data.version : "Not installed"}</span>
            {data?.installed && (latest.data && !latest.data.newer ? (
              <Button size="sm" variant="secondary" disabled={latest.isFetching} onClick={() => void latest.refetch()}>
                {latest.isFetching ? "Checking…" : "Check for updates"}
              </Button>
            ) : (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => update.mutate()}>
                {update.isPending ? "Updating…" : latest.data?.newer ? `Update to ${latest.data.latest}` : "Update"}
              </Button>
            ))}
          </div>
          {data?.installed && latest.data && (
            <p className="field-help" data-testid="tetravox-latest">
              {latest.data.newer ? `TetraVox ${latest.data.latest} is available.` : `Up to date — ${latest.data.latest} is the newest release.`}
              {" "}TetraVox also offers new releases in its own window; TI-Toolbox installs them.
            </p>
          )}
          {data?.installed && latest.error && <p className="field-help">Could not check for updates: {latest.error.message}</p>}
          {busy && (
            <Progress
              indeterminate={!progress.total}
              value={progress.total ? (100 * (progress.received ?? 0)) / progress.total : undefined}
              label={working}
            />
          )}
        </Field>

        <Field label="Location" help="Where TI-Toolbox keeps its TetraVox on disk.">
          <div className="tetravox-row-value">
            <code className="mono">{locationPath ?? "—"}</code>
          </div>
        </Field>

        {!data?.installed && data?.supported && <p className="field-help">TI-Toolbox sets up TetraVox automatically in your user directory from the official release.</p>}
        {unsupported && (
          <p className="field-help">TI-Toolbox has no TetraVox package for this platform.</p>
        )}
        {failure && (
          <p role="alert" className="field-error">
            {String(failure)}
          </p>
        )}

        <div className="tetravox-actions">
          {data?.installed ? (
            <Button variant="primary" disabled={open.isPending} onClick={() => open.mutate()}>
              Launch TetraVox
            </Button>
          ) : (
            data?.supported && (
              <Button variant="primary" disabled={busy} onClick={() => install.mutate()}>
                {busy ? "Installing…" : "Retry setup"}
              </Button>
            )
          )}
        </div>
      </CardBody>
    </Card>
  );
}
