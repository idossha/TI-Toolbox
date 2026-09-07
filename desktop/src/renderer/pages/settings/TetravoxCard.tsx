/**
 * **Settings → Viewer engine** — the in-app half of dynamic embed delivery (E1–E4,
 * `docs/dev/HISTORY.md § 2026-09-04 (embed convergence)`).
 *
 * The maintainer's ask: *"a system where we do not need to release a new version every time
 * Tetravox updates"*. This card is where that happens — what is running, where it came from,
 * what is available, install, and roll back — without a TI-Toolbox release and without a restart.
 *
 * Four rules it follows, each with the failure it prevents:
 *
 * 1. **The digest is shown, always.** A user installing code into their own container can read
 *    the sha256 the server will verify before unpacking. An install that hides what it verifies
 *    is asking to be trusted rather than checked.
 * 2. **This page never reaches the network.** It reads the server's cached answer; the only
 *    thing that asks GitHub anything is "Check now", or the server's own background check under
 *    the policy in rule 5. A Settings page that phoned out on every mount would tell a remote
 *    host that this install exists every time someone opened it.
 * 3. **No network is a sentence, not an error.** The server answers 200 with `available: false`,
 *    and this renders that message — an air-gapped install is a supported state (E2), not a
 *    failure to retry.
 * 4. **Rollback never deletes.** "Use this" on the baked row pins the image's own copy and keeps
 *    every installed bundle, so going forward again is one click. Removal is a separate,
 *    explicitly-labelled action.
 * 5. **Off stops the installing, not the knowing.** With the switch off the server still checks
 *    and this card still shows what it found, with an explicit Install per compatible release.
 *
 * A3 (`docs/dev/HISTORY.md § 2026-09-05/06 (Tetravox auto-update, selection, pipeline canvas)`) added the automatic half. Rule 2 above
 * is unchanged in substance and sharper in practice: **rendering this card still makes no network
 * request**, because the server's own 24 h check writes a cache and the card reads it — it shows
 * *when* the server last looked and *what it decided*. "Check now" is the only thing that spends
 * one of GitHub's 60 requests/hour, and turning automatic updates off stops the *installing*, not
 * the *knowing*: the card then offers an explicit Install for whatever was found.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../ui/Button";
import { Callout, DefinitionList, InlineError, Skeleton } from "../../ui/Feedback";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { Chip } from "../../ui/Status";
import { Switch } from "../../ui/Toggle";
import { notify } from "../../ui/Toast";
import {
  activateTetravox,
  getTetravox,
  getTetravoxUpdates,
  installTetravox,
  removeTetravox,
  setTetravoxPolicy,
  type TetravoxRelease,
  type TetravoxState,
  type TetravoxUpdateOutcome,
} from "./api";

const SOURCE_LABEL: Record<string, string> = {
  baked: "Baked into the image",
  installed: "Installed",
  override: "Developer override",
};

/** A digest is 64 hex characters; the row shows enough to compare, the tooltip carries all of it. */
function Digest({ sha256 }: { sha256: string }) {
  return (
    <code className="mono" title={sha256} style={{ fontSize: "var(--text-xs)", color: "var(--ink-3)" }}>
      sha256 {sha256.slice(0, 12)}…
    </code>
  );
}

function versionLine(release: TetravoxRelease): string {
  return `v${release.version} · protocol ${release.protocol ?? "?"}`;
}

/** "3 minutes ago" beats a timestamp here: the question is *how stale*, not *when exactly*. */
function sinceLabel(checkedAt: number | null | undefined): string {
  if (!checkedAt) return "never";
  const seconds = Math.max(0, Date.now() / 1000 - checkedAt);
  if (seconds < 90) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86_400)} d ago`;
}

/** `unsupported` and `failed` are the two the user may have to act on. */
function outcomeKind(outcome: TetravoxUpdateOutcome): "warning" | "info" {
  return outcome.action === "unsupported" || outcome.action === "failed" ? "warning" : "info";
}

export function TetravoxCard() {
  const queryClient = useQueryClient();
  const stateQuery = useQuery({ queryKey: ["tetravox"], queryFn: getTetravox });
  // Reading the *cached* answer costs the server nothing, so it is safe on mount and is what
  // makes "last checked / what happened" visible without a button press. `refresh` is the button.
  const updatesQuery = useQuery({ queryKey: ["tetravox-updates"], queryFn: () => getTetravoxUpdates(false), staleTime: 60_000 });

  /** Every mutation answers with the whole new state, so nothing has to be re-read. */
  function applyState(next: TetravoxState) {
    queryClient.setQueryData(["tetravox"], next);
    // `capabilities.tetravox_embed` describes the *active* bundle, so it just changed too — and
    // the About card and every feature gate read it.
    queryClient.invalidateQueries({ queryKey: ["capabilities"] });
    queryClient.invalidateQueries({ queryKey: ["tetravox-updates"] });
  }

  const installMutation = useMutation({
    mutationFn: installTetravox,
    onSuccess: (next) => {
      applyState(next);
      notify.success(`Viewer ${next.active ? `v${next.active.version}` : ""} installed and active`);
    },
    onError: (error: Error) => notify.error(error.message),
  });
  const activateMutation = useMutation({
    mutationFn: activateTetravox,
    onSuccess: (next) => {
      applyState(next);
      notify.success(next.active ? `Now using viewer v${next.active.version} (${SOURCE_LABEL[next.active.source]?.toLowerCase() ?? next.active.source})` : "Viewer changed");
    },
    onError: (error: Error) => notify.error(error.message),
  });
  const policyMutation = useMutation({
    mutationFn: setTetravoxPolicy,
    onSuccess: (next) => {
      applyState(next);
      notify.success(next.auto_update ? "Automatic viewer updates are on" : "Automatic viewer updates are off — updates will be offered, not installed");
    },
    onError: (error: Error) => notify.error(error.message),
  });
  const removeMutation = useMutation({
    mutationFn: removeTetravox,
    onSuccess: (next) => {
      applyState(next);
      notify.success("Viewer bundle removed");
    },
    onError: (error: Error) => notify.error(error.message),
  });

  const busy = installMutation.isPending || activateMutation.isPending || removeMutation.isPending;
  const state = stateQuery.data;
  const active = state?.active;

  return (
    <Card>
      <CardHeader title="Viewer engine" />
      <CardBody>
        {stateQuery.isPending && <Skeleton height={96} />}
        {stateQuery.error && <InlineError message="Could not read the viewer bundle state." onAction={() => stateQuery.refetch()} />}

        {state && (
          <div data-testid="tetravox-card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
            <DefinitionList
              entries={[
                ["Version", active ? <span data-testid="tetravox-active-version">{versionLine(active)}</span> : "none installed"],
                ["Source", active ? (SOURCE_LABEL[active.source] ?? active.source) : "—"],
                ["App supports", `protocol ${state.supported.min}–${state.supported.max}`],
                ["Features", active && active.features.length > 0 ? active.features.join(", ") : "—"],
              ]}
            />
            <p className="field-help" data-testid="tetravox-reason">
              {state.reason}. Bundles install to <code className="mono">{state.install_root}</code>; the copy baked into the image is never
              touched, so an offline install always has something to fall back to.
            </p>

            {active && !active.compatible && (
              <Callout kind="danger" title="This viewer is outside the supported range">
                The active bundle speaks protocol {active.protocol ?? "?"}, but this app supports {state.supported.min}–{state.supported.max}. Roll back
                below, or update TI-Toolbox.
              </Callout>
            )}

            <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", justifyContent: "space-between" }}>
              <label style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }} htmlFor="tetravox-auto-update">
                <Switch
                  id="tetravox-auto-update"
                  checked={state.auto_update}
                  disabled={policyMutation.isPending}
                  onCheckedChange={(next) => policyMutation.mutate(next)}
                  aria-label="Install viewer updates automatically"
                />
                <span className="text-body" data-testid="tetravox-auto-update-label">
                  Install viewer updates automatically
                </span>
              </label>
              <Button
                variant="secondary"
                size="sm"
                loading={updatesQuery.isFetching}
                onClick={() => {
                  // Always a forced check: the button exists to ask the index again.
                  queryClient.fetchQuery({ queryKey: ["tetravox-updates"], queryFn: () => getTetravoxUpdates(true), staleTime: 0 });
                }}
                data-testid="tetravox-check"
              >
                Check now
              </Button>
            </div>

            <p className="field-help" data-testid="tetravox-last-checked">
              {state.auto_update
                ? "The server checks for a newer viewer at startup and every 24 hours, and installs one only when it speaks a protocol this app supports."
                : "Automatic installs are off. The server still checks, and offers what it finds below."}{" "}
              Last checked: {sinceLabel(updatesQuery.data?.checked_at)}.
            </p>

            {updatesQuery.data?.last_outcome && (
              <Callout kind={outcomeKind(updatesQuery.data.last_outcome)} title="Last automatic check">
                <span data-testid="tetravox-last-outcome">{updatesQuery.data.last_outcome.message}</span>
              </Callout>
            )}

            {updatesQuery.data && !updatesQuery.data.available && (
              // Rule 3: an air-gapped install is a supported state, not a failure.
              <p className="field-help" data-testid="tetravox-offline">
                {updatesQuery.data.message ?? "The release index could not be reached."} The viewer keeps working; you can install a bundle by hand with
                its URL and digest once you are online.
              </p>
            )}

            {updatesQuery.data?.available && (
              <div data-testid="tetravox-updates" style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                {updatesQuery.data.releases.length === 0 && <p className="field-help">The release index lists no bundles.</p>}
                {updatesQuery.data.releases.map((release) => (
                  <div key={release.version} style={{ display: "flex", gap: "var(--space-3)", alignItems: "baseline", justifyContent: "space-between" }}>
                    <span>
                      <span className="text-body" style={{ fontWeight: 500 }}>
                        v{release.version}
                      </span>{" "}
                      <span className="field-help">protocol {release.protocol ?? "?"}</span>
                      {release.notes && <div className="field-help">{release.notes}</div>}
                      <div>
                        <Digest sha256={release.sha256} />
                      </div>
                    </span>
                    {release.installed ? (
                      <Chip kind="success">installed</Chip>
                    ) : release.compatible ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busy}
                        loading={installMutation.isPending && installMutation.variables?.version === release.version}
                        onClick={() => installMutation.mutate({ version: release.version })}
                        data-testid={`tetravox-install-${release.version}`}
                      >
                        Install
                      </Button>
                    ) : (
                      <Chip kind="warning" title={`Needs an app that supports protocol ${release.protocol ?? "?"}`}>
                        needs a newer app
                      </Chip>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              <span className="text-body" style={{ fontWeight: 500 }}>
                On this machine
              </span>
              {state.baked && (
                <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", justifyContent: "space-between" }}>
                  <span>
                    <span className="text-body">v{state.baked.version}</span> <span className="field-help">baked into the image</span>
                  </span>
                  {state.baked.active ? (
                    <Chip kind="accent">in use</Chip>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => activateMutation.mutate("baked")}
                      data-testid="tetravox-activate-baked"
                    >
                      Use this
                    </Button>
                  )}
                </div>
              )}
              {state.installed.map((release) => (
                <div key={release.version} style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", justifyContent: "space-between" }}>
                  <span>
                    <span className="text-body">v{release.version}</span> <span className="field-help">protocol {release.protocol ?? "?"}</span>
                  </span>
                  <span style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
                    {release.active ? (
                      <Chip kind="accent">in use</Chip>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy || !release.compatible}
                        onClick={() => activateMutation.mutate(release.version)}
                        data-testid={`tetravox-activate-${release.version}`}
                      >
                        Use this
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy || release.active}
                      onClick={() => removeMutation.mutate(release.version)}
                      data-testid={`tetravox-remove-${release.version}`}
                    >
                      Remove
                    </Button>
                  </span>
                </div>
              ))}
              {state.installed.length === 0 && <p className="field-help">Nothing installed yet — the image's own copy is in use.</p>}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
