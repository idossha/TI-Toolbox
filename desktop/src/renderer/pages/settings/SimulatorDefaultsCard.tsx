import { useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import { withAppDefaults } from "../../forms/appDefaults";
import { Button } from "../../ui/Button";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { SimulationSettings } from "../simulator/SimulationSettings";
import { defaultJobSettings, type JobSettings } from "../simulator/types";
import { resolveSimulatorDefaults, useSimulatorDefaults } from "../simulator/userDefaults";
import "../simulator/simulator-page.css";

/**
 * Settings ▸ Simulator: the user's defaults for new simulation jobs, in the very form a job's own
 * Job settings dialog shows (`SimulationSettings`), so the two match control for control. Changes
 * apply at once, like Execution's; a form with no output field ticked is shown, not saved.
 */
function SimulatorDefaults() {
  const saved = useSimulatorDefaults((s) => s.saved);
  const setSimulatorDefaults = useSimulatorDefaults((s) => s.setSimulatorDefaults);
  const [draft, setDraft] = useState<JobSettings>(() => resolveSimulatorDefaults(saved));
  const factory = useMemo(() => defaultJobSettings(), []);

  function change(next: JobSettings) {
    setDraft(next);
    if (next.outputFields.length > 0) setSimulatorDefaults(next);
  }

  return (
    <Card>
      <CardHeader
        title="Defaults for new simulation jobs"
        actions={
          <Button
            variant="ghost"
            size="sm"
            icon={<RotateCcw size={14} />}
            disabled={JSON.stringify(draft) === JSON.stringify(factory)}
            onClick={() => {
              setDraft(factory);
              setSimulatorDefaults(null);
            }}
          >
            Restore factory defaults
          </Button>
        }
      />
      <CardBody>
        <p className="field-help" style={{ marginBottom: "var(--space-3)" }}>
          A new Simulator job starts with these. A job’s own Job settings change that job only, and its Reset to defaults returns here. Changes apply at
          once; jobs already run or queued keep their own values.
        </p>
        <SimulationSettings value={draft} onChange={change} />
      </CardBody>
    </Card>
  );
}

export const SimulatorDefaultsCard = withAppDefaults(SimulatorDefaults);
