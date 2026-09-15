/**
 * Help ▸ Example data — the catalogue with a Download button per sample.
 *
 * The same rows the once-per-project chooser shows (`app/exampleData/ExampleDataList`), in the
 * page's own chrome: source and licence per row, live job progress while one downloads, and
 * **Installed** for what this project already holds. This is the one place a sample can be added
 * after the chooser has been answered — Overview's toolbar button opens this tab rather than
 * carrying a third copy of the list.
 */
import { useNavigate } from "react-router-dom";
import { Button } from "../../ui/Button";
import { Callout } from "../../ui/Feedback";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { ExampleDataList } from "../../app/exampleData/ExampleDataList";
import { useExampleDataJobs } from "../../app/exampleData/useExampleDataJobs";

export function ExampleDataTab() {
  const navigate = useNavigate();
  const { start, busyText, error } = useExampleDataJobs();
  return (
    <Card>
      <CardHeader title="Example data" />
      <CardBody>
        <div data-testid="help-example-data">
          <p className="text-body" style={{ color: "var(--ink-2)", marginBottom: "var(--space-3)" }}>
            Public datasets downloaded into this project, so you can learn TI-Toolbox and test every
            page before using your own data. Each file is verified against its own sha256 before
            anything is written. A head model is ready for the Optimizer, Simulator and Analyzer
            immediately; a raw MRI goes through Pre-process first (1–2 h of charm).
          </p>
          <ExampleDataList
            mode="manage"
            rowState={(sample) => ({ busy: busyText(sample.id) })}
            onDownload={(id) => void start(id).catch(() => undefined)}
          />
          {error && <Callout kind="danger">{error}</Callout>}
          <p className="text-body" style={{ color: "var(--ink-2)", marginTop: "var(--space-3)" }}>
            The packaged example notebook runs the whole workflow on <code>ernie-headmodel</code> —
            a montage simulation, a flex-search optimization and a field analysis — and its first
            cell is this same download (<code>fetch_ernie</code>). Open it from{" "}
            <Button variant="ghost" size="sm" onClick={() => navigate("/notebooks")}>
              Notebooks
            </Button>
            , or run <code>python -m tit.examples --project DIR --list</code> in a shell.
          </p>
        </div>
      </CardBody>
    </Card>
  );
}
