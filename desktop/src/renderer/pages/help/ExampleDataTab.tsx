/**
 * Help ▸ Example data — the catalogue with an action per **part**.
 *
 * The same rows the once-per-project chooser shows (`app/exampleData/ExampleDataList`), in the
 * page's own chrome: each dataset headed by its provenance and licence, each of its parts with its
 * own Download, its own live progress while it runs (polled from `GET /api/example-data`, not a job
 * stream), and its own **Installed ✓** with a quiet Re-download. This is the one place a part can
 * be added after the chooser has been answered — Overview's toolbar button opens this tab rather
 * than carrying a third copy of the list.
 */
import { useNavigate } from "react-router-dom";
import { Button } from "../../ui/Button";
import { Callout } from "../../ui/Feedback";
import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { ExampleDataList } from "../../app/exampleData/ExampleDataList";
import { useExampleData } from "../../app/exampleData/useExampleData";

export function ExampleDataTab() {
  const navigate = useNavigate();
  const { start, error } = useExampleData();
  return (
    <Card>
      <CardHeader title="Example data" />
      <CardBody>
        <div data-testid="help-example-data">
          <p className="text-body" style={{ color: "var(--ink-2)", marginBottom: "var(--space-3)" }}>
            Public datasets downloaded into this project, so you can learn TI-Toolbox and test every
            page before using your own data. Each file is verified against its own sha256 before
            anything is written. Every part downloads and is detected on its own: a head model is
            ready for the Optimizer, Simulator and Analyzer immediately, while a raw MRI goes
            through Pre-process first (1–2 h of charm).
          </p>
          <ExampleDataList
            mode="manage"
            onDownload={(id, force) => void start(id, force).catch(() => undefined)}
          />
          {error && <Callout kind="danger">{error}</Callout>}
          <p className="text-body" style={{ color: "var(--ink-2)", marginTop: "var(--space-3)" }}>
            The packaged example notebook runs the whole workflow on <code>ernie</code> —
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
