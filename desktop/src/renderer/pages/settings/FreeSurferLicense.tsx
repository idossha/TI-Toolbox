/**
 * The one place a user adds their own FreeSurfer license, plus the notice the Pre-processing
 * page shows when a licensed stage is selected and none is stored.
 *
 * The FreeSurfer license is issued per registered individual and may not be redistributed, so
 * the toolbox never bundles or fetches one: the user pastes the `license.txt` they received and
 * the server keeps it in the user config dir (`~/.config/ti-toolbox/freesurfer-license.txt`),
 * which every launcher mounts into the container. FastSurfer segmentation needs no license;
 * `recon-all`, the subregion tools and QSIPrep/QSIRecon do.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "../../ui/Button";
import { Callout, InlineError } from "../../ui/Feedback";
import { Field, Textarea } from "../../ui/Field";
import { deleteFreeSurferLicense, getSurferSettings, putFreeSurferLicense } from "./api";

export const FS_REGISTRATION_URL = "https://surfer.nmr.mgh.harvard.edu/registration.html";
const SURFER_SETTINGS_KEY = ["surfer-settings"];

export function RegistrationLink() {
  return <a href={FS_REGISTRATION_URL} target="_blank" rel="noreferrer">surfer.nmr.mgh.harvard.edu/registration.html ↗</a>;
}

/** Settings → Pre-processing → FreeSurfer: paste once, used by every job that needs it. */
export function FreeSurferLicenseField() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: SURFER_SETTINGS_KEY, queryFn: getSurferSettings });
  const [text, setText] = useState("");
  const store = useMutation({
    mutationFn: putFreeSurferLicense,
    onSuccess: (next) => { client.setQueryData(SURFER_SETTINGS_KEY, next); setText(""); },
  });
  const forget = useMutation({
    mutationFn: deleteFreeSurferLicense,
    onSuccess: (next) => client.setQueryData(SURFER_SETTINGS_KEY, next),
  });
  const license = settings.data?.freesurfer_license;
  const busy = store.isPending || forget.isPending;
  return (
    <div role="group" aria-label="FreeSurfer license" style={{ display: "grid", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
      <div className="field-label">FreeSurfer license</div>
      {license?.configured ? (
        <p className="field-help" data-testid="fs-license-status">
          License stored{license.email ? ` for ${license.email}` : ""}
          {license.source === "environment" ? " (from the environment, $FS_LICENSE or the image path)" : ""}.
          Used by recon-all, subregion segmentation and QSIPrep/QSIRecon. FastSurfer segmentation needs none.
        </p>
      ) : (
        <p className="field-help" data-testid="fs-license-status">
          No license stored. Needed only for FreeSurfer recon-all, thalamic and hippocampal/amygdala subregions
          and QSIPrep/QSIRecon; FastSurfer segmentation runs without one. Register (free) at <RegistrationLink />,
          then paste the whole license.txt you receive below. It stays on this machine and is never uploaded.
        </p>
      )}
      <Field label={license?.configured ? "Replace license.txt" : "Paste license.txt"} htmlFor="fs-license-text" layout="stacked">
        <Textarea id="fs-license-text" rows={4} spellCheck={false} autoComplete="off" value={text}
          placeholder={"name@example.org\n12345\n *Ab1cD2eF3gH\n FSabc123DEF456"}
          onChange={(event) => setText(event.target.value)} style={{ fontFamily: "var(--font-mono)" }} />
      </Field>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <Button size="sm" variant="primary" disabled={busy || text.trim().length === 0} loading={store.isPending}
          onClick={() => store.mutate(text)}>Store license</Button>
        {license?.configured && license.source === "app" && (
          <Button size="sm" disabled={busy} loading={forget.isPending} onClick={() => forget.mutate()}>Forget license</Button>
        )}
      </div>
      {(store.error || forget.error) && <InlineError message={(store.error || forget.error)!.message} />}
    </div>
  );
}

/** Pre-processing page: shown under the FreeSurfer step while it is selected without a license. */
export function FreeSurferLicenseNotice({ selected }: { selected: boolean }) {
  const settings = useQuery({ queryKey: SURFER_SETTINGS_KEY, queryFn: getSurferSettings, enabled: selected });
  if (!selected || !settings.data || settings.data.freesurfer_license.configured) return null;
  return (
    <Callout kind="warning" title="FreeSurfer needs your license">
      recon-all and the subregion tools run FreeSurfer, which needs your own license; none is stored
      (FastSurfer segmentation does not need one). Register free at <RegistrationLink /> and paste the
      license.txt under <Link to="/settings#preprocessing">Settings → Pre-processing</Link>.
    </Callout>
  );
}
