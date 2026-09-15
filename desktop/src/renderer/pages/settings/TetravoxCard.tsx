import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Chip, Progress, type SemanticKind } from "../../ui/Status";
import { SOURCE_LABEL, useNativeTetravox } from "../../viewer/NativeTetravox";
import type { TitNativeTetravoxStatus } from "../../../shared/tit-bridge";
import "./TetravoxCard.css";

function statusPill(data: TitNativeTetravoxStatus | undefined, pending: boolean): { kind: SemanticKind; label: string } {
  if (!data) return { kind: "neutral", label: pending ? "Checking…" : "Not installed" };
  if (!data.installed) return { kind: "neutral", label: "Not installed" };
  if (data.updateAvailable) return { kind: "warning", label: `Update available ${data.updateAvailable}` };
  const location = data.source === "system" && data.directory ? ` (${data.directory})` : "";
  return { kind: "success", label: `Installed ${data.version}${data.source ? ` · ${data.source}` : ""}${location}` };
}

/**
 * Settings ▸ Viewer's TetraVox card. Same status/mutations as the compact viewer embed
 * (`useNativeTetravox` in `NativeTetravox.tsx`) laid out as `Field` rows to match the other
 * settings cards (Project, Pre-processing, Extensions, Server) rather than a stack of full-width
 * buttons.
 */
export function TetravoxCard() {
  const { bridge, data, pending, progress, busy, working, failure, install, update, check, locate, forget, open } = useNativeTetravox();

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
  const sourceLabel = data?.source ? SOURCE_LABEL[data.source] : undefined;
  const locationPath = data?.executable || data?.directory;
  const unsupported = data && !data.supported && !data.installed;

  return (
    <Card>
      <CardHeader title="TetraVox" actions={<Chip kind={pill.kind}>{pill.label}</Chip>} />
      <CardBody className="tetravox-card-body">
        {data?.installed && (
          <Field label="Source" help="Which TetraVox installation TI-Toolbox launches.">
            <div className="tetravox-row-value">
              <span>{sourceLabel}</span>
              {locationPath && <code className="mono">{locationPath}</code>}
            </div>
            {data.configuredPath && (
              <a
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  forget.mutate();
                }}
              >
                Use automatic choice
              </a>
            )}
          </Field>
        )}

        <Field label="Version">
          <div className="tetravox-row-value">
            <span>{data?.installed ? data.version : "Not installed"}</span>
            {data?.updateAvailable ? (
              <Button size="sm" variant="primary" disabled={busy} onClick={() => update.mutate()}>
                {`Update to ${data.updateAvailable}`}
              </Button>
            ) : (
              data?.source === "managed" && (
                <Button size="sm" variant="secondary" disabled={check.isPending || busy} onClick={() => check.mutate()}>
                  {check.isPending ? "Checking…" : check.isSuccess ? "Up to date" : "Check for updates"}
                </Button>
              )
            )}
          </div>
          {busy && (
            <Progress
              indeterminate={!progress.total}
              value={progress.total ? (100 * (progress.received ?? 0)) / progress.total : undefined}
              label={working}
            />
          )}
        </Field>

        <Field label="Location" help="Where the launched TetraVox lives on disk.">
          <div className="tetravox-row-value">
            <code className="mono">{locationPath ?? "—"}</code>
            <Button size="sm" variant="secondary" disabled={locate.isPending} onClick={() => locate.mutate()}>
              Locate…
            </Button>
          </div>
        </Field>

        {unsupported && (
          <p className="field-help">TI-Toolbox cannot install TetraVox on this platform. Install it yourself, then use Locate…</p>
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
                {busy ? "Installing…" : "Install TetraVox"}
              </Button>
            )
          )}
        </div>
      </CardBody>
    </Card>
  );
}
