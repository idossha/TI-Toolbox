/** TI-Toolbox supplies the FreeSurfer license; users never configure one. */
import { useQuery } from "@tanstack/react-query";
import { Callout, InlineError } from "../../ui/Feedback";
import { getSurferSettings } from "./api";

const SURFER_SETTINGS_KEY = ["surfer-settings"];
const REPAIR_MESSAGE = "Repair or update the TI-Toolbox installation. No personal license or registration is required.";

/** Settings shows installation status, without a license entry or registration flow. */
export function FreeSurferLicenseField() {
  const settings = useQuery({ queryKey: SURFER_SETTINGS_KEY, queryFn: getSurferSettings });
  return (
    <div role="group" aria-label="FreeSurfer license" style={{ display: "grid", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
      <div className="field-label">FreeSurfer license</div>
      <p className="field-help" data-testid="fs-license-status">
        TI-Toolbox supplies the FreeSurfer license automatically for FreeSurfer, QSIPrep and QSIRecon.
        No personal license or registration is required.
      </p>
      {settings.data && !settings.data.freesurfer_license.configured && (
        <Callout kind="warning" title="TI-Toolbox license unavailable">{REPAIR_MESSAGE}</Callout>
      )}
      {settings.error && <InlineError message={settings.error.message} />}
    </div>
  );
}

/** A damaged installation needs repair, never a personal license. */
export function FreeSurferLicenseNotice({ selected }: { selected: boolean }) {
  const settings = useQuery({ queryKey: SURFER_SETTINGS_KEY, queryFn: getSurferSettings, enabled: selected });
  if (!selected || !settings.data || settings.data.freesurfer_license.configured) return null;
  return (
    <Callout kind="warning" title="TI-Toolbox license unavailable">{REPAIR_MESSAGE}</Callout>
  );
}
