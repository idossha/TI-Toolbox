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
  const { bridge, data, pending, progress, busy, working, failure, install, locate, forget, open } = useNativeTetravox();

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

        <Field label="Version" note="Updates are managed in TetraVox.">
          <div className="tetravox-row-value">
            <span>{data?.installed ? data.version : "Not installed"}</span>
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
            <Button size="sm" variant="secondary" disabled={busy || locate.isPending} onClick={() => locate.mutate()}>
              Locate…
            </Button>
          </div>
        </Field>

        {!data?.installed && data?.supported && <p className="field-help">TI-Toolbox sets up TetraVox automatically in your user directory when no installation is found.</p>}
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
                {busy ? "Installing…" : "Retry setup"}
              </Button>
            )
          )}
        </div>
      </CardBody>
    </Card>
  );
}
