/**
 * Every primitive, every listed state, light and dark — design QA screenshots this page instead
 * of hunting through real screens for a rare state (DESIGN.md quality floor). Not shipped in
 * production builds (see pages/dev/index.tsx: `enabled: import.meta.env.DEV`).
 */
import { useState, type ReactNode } from "react";
import type { RowSelectionState } from "@tanstack/react-table";
import { Play, Rocket, Save, Trash2, Users } from "lucide-react";
import { useThemeStore } from "../app/theme/store";
import { Button, IconButton } from "../ui/Button";
import { Badge, Chip, JobStateChip, LivenessBadge, Progress, StatusDot, type JobState, type SemanticKind } from "../ui/Status";
import { Field, TextInput, Textarea } from "../ui/Field";
import { NumberInput } from "../ui/NumberInput";
import { Select } from "../ui/Select";
import { Combobox, MultiSelect } from "../ui/Combobox";
import { Checkbox, RadioGroup, Slider, Switch } from "../ui/Toggle";
import { PathInput } from "../ui/PathInput";
import { SubjectsField } from "../pages/_shared/subjects";
import { CoordinateInput, type Coordinate } from "../ui/CoordinateInput";
import { KeyValueTable, type KeyValueRow } from "../ui/KeyValueTable";
import { ElectrodePairsEditor, type ElectrodePair } from "../ui/ElectrodePairsEditor";
import { Card, CardBody, CardHeader, Cluster, FormSection, KeyValue, PageHeader, ResizablePanels, Stack, Tabs } from "../ui/Layout";
import { PlanSummary } from "../ui/PlanSummary";
import { AlertDialog, Dialog, Drawer, Popover, Tooltip } from "../ui/Overlay";
import { HelpIcon } from "../ui/HelpPopover";
import { notify } from "../ui/Toast";
import { Callout, DefinitionList, EmptyState, Kbd, Skeleton } from "../ui/Feedback";
import { VirtualList } from "../ui/VirtualList";
import { DataTable, type DataTableColumn } from "../ui/DataTable";
import { LineChart, Sparkline } from "../ui/Chart";
import { ArtifactList, JobConsole, JobTrace, JobsTable, type JobLogLine, type JobSummary } from "../ui/Jobs";
import { jobEventsToLogLines } from "../app/jobs/logLines";
import type { JobEvent } from "../app/jobs/types";
import { SceneGallery } from "./SceneGallery";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginBottom: "var(--space-8)" }}>
      <h2 className="text-section" style={{ marginBottom: "var(--space-3)" }}>
        {title}
      </h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-4)", alignItems: "flex-start" }}>{children}</div>
    </section>
  );
}

function Swatch({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="text-caption" style={{ color: "var(--ink-2)" }}>
        {label}
      </span>
      {children}
    </div>
  );
}

const SEMANTIC_KINDS: SemanticKind[] = ["neutral", "accent", "success", "warning", "danger", "field", "lost"];
const JOB_STATES: JobState[] = ["queued", "running", "succeeded", "failed", "cancelled", "skipped", "lost"];

interface DemoSubject {
  id: string;
  raw: boolean;
  freesurfer: boolean;
  m2m: boolean;
}
const DEMO_SUBJECTS: DemoSubject[] = [
  { id: "101", raw: true, freesurfer: true, m2m: true },
  { id: "102", raw: true, freesurfer: false, m2m: false },
];
const DEMO_SUBJECT_COLUMNS = [
  { id: "raw", label: "raw", present: (s: DemoSubject) => s.raw },
  { id: "freesurfer", label: "freesurfer", present: (s: DemoSubject) => s.freesurfer },
  { id: "m2m", label: "m2m", present: (s: DemoSubject) => s.m2m },
];

interface DemoRow {
  name: string;
  score: number;
  status: "ok" | "warn";
}
const DEMO_ROWS: DemoRow[] = [
  { name: "sub-101", score: 0.87, status: "ok" },
  { name: "sub-102", score: 0.54, status: "warn" },
  { name: "sub-103", score: 0.91, status: "ok" },
];

const DEMO_JOBS: JobSummary[] = [
  { id: "1", kind: "sim", subject: "101", state: "running", progressPct: 62, liveness: "active", elapsed: "4m 12s" },
  { id: "2", kind: "flex", subject: "102", state: "queued", elapsed: "0s" },
  { id: "3", kind: "analyzer", subject: "103", state: "succeeded", elapsed: "1m 3s" },
  { id: "4", kind: "pre", subject: "104", state: "failed", elapsed: "38s" },
  { id: "5", kind: "ex", subject: "105", state: "running", liveness: "stalled", elapsed: "9m 0s" },
];

// Generated once at module load, not during render — Date.now()/Math.random() inside a
// component body would violate the "components must be pure" rule (react-hooks/purity).
const DEMO_CHART_BASE_TS = Date.now() / 1000;
const DEMO_CHART_TIMESTAMPS = Array.from({ length: 30 }, (_, i) => DEMO_CHART_BASE_TS - (30 - i) * 2);
const DEMO_CHART_VALUES = Array.from({ length: 30 }, () => 20 + Math.random() * 60);

/*
 * Built through the real transform (`jobEventsToLogLines`) from the shapes a real server sends,
 * because that is where the console's one hard invariant lives: ONE ITEM PER VISUAL LINE. A single
 * SimNIBS event carries a whole multi-line block ("Placing Electrode:" and its eight fields), and
 * the virtual list gives every item exactly 18 px — so an unsplit block used to paint over the
 * lines below it (`tests/e2e/terminal.spec.ts` measures that no two rows overlap).
 */
const DEMO_LOG_EVENTS: JobEvent[] = [
  { seq: 1, ts: 1, type: "log", level: "info", msg: "[stage] head modelling started" },
  { seq: 2, ts: 2, type: "log", level: "debug", msg: "charm --forceqform sub-101" },
  { seq: 3, ts: 3, type: "log", level: "warning", msg: "low contrast in T1 near vertex" },
  { seq: 4, ts: 4, type: "log", level: "error", msg: "charm exited 1: see log for details" },
  {
    seq: 5,
    ts: 5,
    type: "log",
    level: "info",
    msg: "Placing Electrode:\ndefinition: plane\nshape: ellipse\ncentre: E034\npos_ydir: []\ndimensions: [8, 8]\nthickness:[4, 2.0]\nchannelnr: 1\nnumber of holes: 0\n",
  },
  { seq: 6, ts: 6, type: "log", level: "info", msg: "meshing 1 %\rmeshing 47 %\rmeshing 100 %" },
  ...Array.from({ length: 120 }, (_, index): JobEvent => ({
    seq: index + 7,
    ts: index + 7,
    type: "log",
    level: "info",
    msg:
      index === 119 || index % 20 === 19
        ? `long command ${"--electrode-position 123.456,789.012,-345.678 ".repeat(12)}`
        : index % 7 === 6
          ? `[ simnibs ] INFO: Running Simulation ${index} of 75\n[ simnibs ] INFO: Time to set up KSP:   2.5794 s\n[ simnibs ] INFO: Time to solve:   5.8715 s`
          : `worker output ${index + 7}`,
  })),
];

const DEMO_LOG_LINES: JobLogLine[] = jobEventsToLogLines(DEMO_LOG_EVENTS);

export function Gallery() {
  const { theme, setTheme } = useThemeStore();

  const [textValue, setTextValue] = useState("sub-101");
  const [numberValue, setNumberValue] = useState<number | undefined>(1.8);
  const [selectValue, setSelectValue] = useState<string | undefined>("mean");
  const [comboValue, setComboValue] = useState<string | undefined>(undefined);
  const [multiValues, setMultiValues] = useState<string[]>(["F3", "F4"]);
  const [switchOn, setSwitchOn] = useState(true);
  const [checkboxState, setCheckboxState] = useState<boolean | "indeterminate">(true);
  const [radioValue, setRadioValue] = useState("mean");
  const [sliderValue, setSliderValue] = useState(1.5);
  const [pathValue, setPathValue] = useState("/mnt/project/derivatives/SimNIBS/sub-101");
  const [subjectSelection, setSubjectSelection] = useState<string[]>(["101"]);
  const [coordinate, setCoordinate] = useState<Coordinate>({ x: -28.4, y: 12.1, z: 54.0 });
  const [space, setSpace] = useState<"subject" | "mni">("mni");
  const [kvRows, setKvRows] = useState<KeyValueRow[]>([{ key: "intensity", value: "2.0" }]);
  const [pairMode, setPairMode] = useState<"net" | "freehand">("net");
  const [pairs, setPairs] = useState<ElectrodePair[]>([["F3", "F4"]]);
  const [freehandPairs, setFreehandPairs] = useState<[Coordinate, Coordinate][]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [alertOpen, setAlertOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [layeringDialogOpen, setLayeringDialogOpen] = useState(false);
  const [layeringSelect, setLayeringSelect] = useState<string | undefined>("mean");
  const [selectedRows, setSelectedRows] = useState<RowSelectionState>({});

  const columns: DataTableColumn<DemoRow>[] = [
    { header: "Name", accessorKey: "name" },
    { header: "Score", numeric: true, accessorKey: "score" },
    { header: "Status", cell: ({ row }) => <Chip kind={row.original.status === "ok" ? "success" : "warning"}>{row.original.status}</Chip> },
  ];

  return (
    <div style={{ maxWidth: 1100 }}>
      <PageHeader
        title="Design gallery"
        purpose="Every primitive, every state — for design QA screenshots, not shipped in production."
        actions={
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button variant={theme === "light" ? "primary" : "secondary"} size="sm" onClick={() => setTheme("light")}>
              Light
            </Button>
            <Button variant={theme === "dark" ? "primary" : "secondary"} size="sm" onClick={() => setTheme("dark")}>
              Dark
            </Button>
            <Button variant={theme === "system" ? "primary" : "secondary"} size="sm" onClick={() => setTheme("system")}>
              System
            </Button>
          </div>
        }
      />

      <div style={{ height: "var(--space-8)" }} />

      <Section title="Buttons">
        <Swatch label="Primary">
          <Button variant="primary" icon={<Play size={14} />}>
            Run simulation
          </Button>
        </Swatch>
        <Swatch label="Secondary">
          <Button variant="secondary">Save montage</Button>
        </Swatch>
        <Swatch label="Ghost">
          <Button variant="ghost">Cancel</Button>
        </Swatch>
        <Swatch label="Destructive">
          <Button variant="destructive" icon={<Trash2 size={14} />}>
            Delete montage
          </Button>
        </Swatch>
        <Swatch label="Loading">
          <Button variant="primary" loading>
            Queue 3 jobs
          </Button>
        </Swatch>
        <Swatch label="Disabled">
          <Button variant="primary" disabled>
            Run simulation
          </Button>
        </Swatch>
        <Swatch label="Sizes">
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Button size="sm">Small</Button>
            <Button size="md">Medium</Button>
            <Button size="lg">Large</Button>
          </div>
        </Swatch>
        <Swatch label="Icon button">
          <IconButton aria-label="Open in viewer" icon={<Rocket size={16} />} />
        </Swatch>
      </Section>

      <Section title="Status">
        <Swatch label="StatusDot (all kinds)">
          <div style={{ display: "flex", gap: 8 }}>
            {SEMANTIC_KINDS.map((k) => (
              <StatusDot key={k} kind={k} title={k} />
            ))}
            <StatusDot kind="accent" pulse title="pulsing" />
          </div>
        </Swatch>
        <Swatch label="Chip (all kinds)">
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {SEMANTIC_KINDS.map((k) => (
              <Chip key={k} kind={k} dot>
                {k}
              </Chip>
            ))}
            <Chip kind="danger" missing>
              missing
            </Chip>
          </div>
        </Swatch>
        <Swatch label="Badge">
          <div style={{ display: "flex", gap: 8 }}>
            <Badge count={3} />
            <Badge count={12} neutral />
          </div>
        </Swatch>
        <Swatch label="Progress">
          <div style={{ width: 220 }}>
            <Progress value={62} label="Head modelling" />
          </div>
        </Swatch>
        <Swatch label="Progress (indeterminate)">
          <div style={{ width: 220 }}>
            <Progress indeterminate label="Preparing" />
          </div>
        </Swatch>
        <Swatch label="LivenessBadge">
          <div style={{ display: "flex", gap: 12 }}>
            <LivenessBadge state="active" />
            <LivenessBadge state="stalled" stalledFor="3m" />
          </div>
        </Swatch>
        <Swatch label="JobStateChip (all states)">
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {JOB_STATES.map((s) => (
              <JobStateChip key={s} state={s} pulse={s === "running"} />
            ))}
          </div>
        </Swatch>
        <Swatch label="JobStateChip — running, active vs. stalled (one dot, never two: ra_12 #17)">
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <JobStateChip state="running" pulse={true} />
            <JobStateChip state="running" pulse={false} />
          </div>
        </Swatch>
      </Section>

      <Section title="Form fields">
        <Swatch label="TextInput">
          <Field label="Subject" required help="BIDS subject id.">
            <TextInput value={textValue} onChange={(e) => setTextValue(e.target.value)} />
          </Field>
        </Swatch>
        <Swatch label="TextInput (error)">
          <Field label="Subject" required error="Subject sub-999 does not exist.">
            <TextInput value="sub-999" invalid onChange={() => {}} />
          </Field>
        </Swatch>
        <Swatch label="TextInput (disabled)">
          <Field label="Subject">
            <TextInput value="sub-101" disabled onChange={() => {}} />
          </Field>
        </Swatch>
        <Swatch label="Textarea">
          <Field label="Notes">
            <Textarea rows={3} placeholder="Optional notes…" />
          </Field>
        </Swatch>
        <Swatch label="NumberInput (unit)">
          <Field label="Intensity">
            <NumberInput value={numberValue} onValueChange={setNumberValue} unit="mA" step={0.1} min={0} max={4} />
          </Field>
        </Swatch>
        <Swatch label="Select">
          <Field label="Goal">
            <Select
              value={selectValue}
              onValueChange={setSelectValue}
              options={[
                { value: "mean", label: "Mean" },
                { value: "max", label: "Max" },
                { value: "focality", label: "Focality" },
              ]}
            />
          </Field>
        </Swatch>
        <Swatch label="Combobox">
          <Field label="Atlas region">
            <Combobox
              value={comboValue}
              onValueChange={setComboValue}
              options={[
                { value: "dlpfc", label: "Dorsolateral prefrontal cortex" },
                { value: "m1", label: "Primary motor cortex" },
                { value: "acc", label: "Anterior cingulate cortex" },
              ]}
            />
          </Field>
        </Swatch>
        <Swatch label="MultiSelect">
          <Field label="Electrodes" help="Chips, from an EEG net.">
            <MultiSelect
              values={multiValues}
              onValuesChange={setMultiValues}
              options={["F3", "F4", "C3", "C4", "P3", "P4"].map((v) => ({ value: v, label: v }))}
            />
          </Field>
        </Swatch>
        <Swatch label="Switch">
          <Field label="Combine ROIs">
            <Switch checked={switchOn} onCheckedChange={setSwitchOn} aria-label="Combine ROIs" />
          </Field>
        </Swatch>
        <Swatch label="Checkbox">
          <Checkbox checked={checkboxState} onCheckedChange={setCheckboxState} label="Overwrite existing outputs" />
        </Swatch>
        <Swatch label="RadioGroup (horizontal)">
          <RadioGroup
            value={radioValue}
            onValueChange={setRadioValue}
            options={[
              { value: "mean", label: "Mean" },
              { value: "max", label: "Max" },
              { value: "focality", label: "Focality" },
            ]}
          />
        </Swatch>
        <Swatch label="RadioGroup (cards)">
          <RadioGroup
            layout="cards"
            value={radioValue}
            onValueChange={setRadioValue}
            options={[
              { value: "mean", label: "Mean" },
              { value: "max", label: "Max" },
            ]}
          />
        </Swatch>
        <Swatch label="Slider">
          <div style={{ width: 260 }}>
            <Slider value={sliderValue} onValueChange={setSliderValue} min={0} max={4} step={0.1} unit="mA" aria-label="Intensity" />
          </div>
        </Swatch>
        <Swatch label="PathInput">
          <div style={{ width: 380 }}>
            <PathInput value={pathValue} onValueChange={setPathValue} onBrowse={async () => pathValue} />
          </div>
        </Swatch>
        <Swatch label="SubjectsField">
          <div style={{ width: 420 }}>
            <SubjectsField
              subjects={DEMO_SUBJECTS}
              value={subjectSelection}
              onChange={setSubjectSelection}
              columns={DEMO_SUBJECT_COLUMNS}
              eligibility={(s) => (s.m2m ? { ok: true } : { ok: false, reason: "no head model (m2m)" })}
              defaultOpen
            />
          </div>
        </Swatch>
        <Swatch label="CoordinateInput">
          <CoordinateInput value={coordinate} onValueChange={setCoordinate} space={space} onSpaceChange={setSpace} withRadius />
        </Swatch>
        <Swatch label="KeyValueTable">
          <div style={{ width: 320 }}>
            <KeyValueTable rows={kvRows} onRowsChange={setKvRows} />
          </div>
        </Swatch>
        <Swatch label="ElectrodePairsEditor">
          <div style={{ width: 420 }}>
            <ElectrodePairsEditor
              mode={pairMode}
              onModeChange={setPairMode}
              electrodes={["F3", "F4", "C3", "C4"]}
              pairs={pairs}
              onPairsChange={setPairs}
              freehandPairs={freehandPairs}
              onFreehandPairsChange={setFreehandPairs}
            />
          </div>
        </Swatch>
      </Section>

      <Section title="Containers">
        <Swatch label="Card">
          <Card>
            <CardHeader title="Conductivities" />
            <CardBody>Scalp, skull, CSF, gray matter, white matter.</CardBody>
          </Card>
        </Swatch>
        <Swatch label="FormSection (with Advanced)">
          <div style={{ width: 420 }}>
            <FormSection title="Output fields" advanced={<Field label="Mesh format"><TextInput value="msh" onChange={() => {}} /></Field>}>
              <Field label="Field">
                <TextInput value="TI_max" onChange={() => {}} />
              </Field>
            </FormSection>
          </div>
        </Swatch>
        <Swatch label="Tabs">
          <div style={{ width: 420 }}>
            <Tabs
              items={[
                { id: "a", label: "Montage", content: <p className="text-body">Montage tab content.</p> },
                { id: "b", label: "Conductivity", content: <p className="text-body">Conductivity tab content.</p> },
              ]}
            />
          </div>
        </Swatch>
        <Swatch label="Dialog">
          <Dialog
            open={dialogOpen}
            onOpenChange={setDialogOpen}
            title="Save montage"
            description="Give this montage a name."
            trigger={<Button variant="secondary" icon={<Save size={14} />}>Save montage</Button>}
            footer={
              <>
                <Button variant="secondary" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={() => setDialogOpen(false)}>
                  Save montage
                </Button>
              </>
            }
          >
            <Field label="Name" required>
              <TextInput placeholder="my-montage" onChange={() => {}} />
            </Field>
          </Dialog>
        </Swatch>
        <Swatch label="AlertDialog">
          <AlertDialog
            open={alertOpen}
            onOpenChange={setAlertOpen}
            title="Overwrite existing outputs?"
            description="Simulations for sub-101 already exist at this path and will be overwritten."
            confirmLabel="Overwrite"
            onConfirm={() => {
              setAlertOpen(false);
              notify.success("Overwritten");
            }}
            trigger={<Button variant="destructive">Overwrite</Button>}
          />
        </Swatch>
        <Swatch label="Drawer">
          <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
            Open drawer
          </Button>
          <Drawer open={drawerOpen} onOpenChange={setDrawerOpen} title="Run detail">
            <DefinitionList entries={[["kind", "sim"], ["subject", "101"], ["state", "running"]]} />
          </Drawer>
        </Swatch>
        <Swatch label="Popover">
          <Popover trigger={<Button variant="secondary">Filters</Button>}>
            <Field label="Min score">
              <NumberInput value={0.5} onValueChange={() => {}} />
            </Field>
          </Popover>
        </Swatch>
        <Swatch label="Tooltip (nav/overflow labels only — never help; help is HelpIcon)">
          <Tooltip label="Runs a two-pair TI simulation">
            <span>
              <IconButton aria-label="Participants" icon={<Users size={16} />} />
            </span>
          </Tooltip>
        </Swatch>
        <Swatch label="HelpIcon (click, never hover)">
          <HelpIcon
            title="Goal"
            text={"What the optimizer **maximises** inside the ROI.\n\n- `mean` — average field\n- `max` — peak field\n- `focality` — on-target share"}
          />
        </Swatch>
        <Swatch label="Select inside a Dialog (z-index layering: overlay 80 < dialog 90 < popover/select 100 < tooltip 110 < toast 120, tokens.css)">
          <Dialog
            open={layeringDialogOpen}
            onOpenChange={setLayeringDialogOpen}
            title="Configure output"
            description="A Select's popover must render above this dialog, not behind it."
            trigger={<Button variant="secondary">Open dialog with a Select</Button>}
            footer={
              <Button variant="primary" onClick={() => setLayeringDialogOpen(false)}>
                Done
              </Button>
            }
          >
            <Field label="Goal" help="Click to open — its options list must sit on top of this dialog.">
              <Select
                value={layeringSelect}
                onValueChange={setLayeringSelect}
                options={[
                  { value: "mean", label: "Mean" },
                  { value: "max", label: "Max" },
                  { value: "focality", label: "Focality" },
                ]}
              />
            </Field>
          </Dialog>
        </Swatch>
      </Section>

      <Section title="Feedback">
        <Swatch label="EmptyState">
          <div style={{ width: 320, border: "1px dashed var(--line)", borderRadius: 6 }}>
            <EmptyState icon={<Users size={24} />} message="No simulations for ernie yet — run one from Simulator." actionLabel="Run simulation" onAction={() => {}} />
          </div>
        </Swatch>
        <Swatch label="Skeleton">
          <div style={{ width: 240, display: "flex", flexDirection: "column", gap: 6 }}>
            <Skeleton height={14} />
            <Skeleton height={14} width="70%" />
            <Skeleton height={60} />
          </div>
        </Swatch>
        <Swatch label="Callout (info / warning / danger)">
          <div style={{ width: 320, display: "flex", flexDirection: "column", gap: 8 }}>
            <Callout kind="info" title="Plan">
              This will queue 3 jobs.
            </Callout>
            <Callout kind="warning" title="Will queue behind #12">
              charm sub-101 is already running.
            </Callout>
            <Callout kind="danger" title="Conflict">
              Output already exists at this path.
            </Callout>
          </div>
        </Swatch>
        <Swatch label="Kbd">
          <span>
            <Kbd>⌘</Kbd> <Kbd>J</Kbd>
          </span>
        </Swatch>
        <Swatch label="DefinitionList">
          <DefinitionList entries={[["kind", "sim"], ["subject", "101"], ["montage", "F3-F4 / C3-C4"]]} />
        </Swatch>
      </Section>

      <Section title="Data">
        <Swatch label="Sparkline">
          <Sparkline values={[2, 5, 3, 8, 6, 9, 7, 10]} />
        </Swatch>
        <Swatch label="LineChart (uPlot)">
          <div style={{ width: 320 }}>
            <LineChart timestamps={DEMO_CHART_TIMESTAMPS} values={DEMO_CHART_VALUES} label="CPU percent" />
          </div>
        </Swatch>
        <Swatch label="LineChart — collecting (< 2 samples, ra_12 #29)">
          <div style={{ width: 320 }}>
            <LineChart timestamps={DEMO_CHART_TIMESTAMPS.slice(0, 1)} values={DEMO_CHART_VALUES.slice(0, 1)} label="CPU percent" />
          </div>
        </Swatch>
        <Swatch label="DataTable">
          <div style={{ width: 420 }}>
            <DataTable data={DEMO_ROWS} columns={columns} getRowId={(r) => r.name} selectable selected={selectedRows} onSelectedChange={setSelectedRows} />
          </div>
        </Swatch>
        <Swatch label="VirtualList">
          <div style={{ width: 260, height: 120, border: "1px solid var(--line)", borderRadius: 6 }}>
            <VirtualList
              items={Array.from({ length: 200 }, (_, i) => `Row ${i + 1}`)}
              rowHeight={24}
              renderRow={(row) => <div style={{ padding: "0 8px", fontSize: 12 }}>{row}</div>}
              style={{ height: "100%" }}
            />
          </div>
        </Swatch>
        <Swatch label="ResizablePanels">
          <div style={{ width: 420, height: 120, border: "1px solid var(--line)", borderRadius: 6 }}>
            <ResizablePanels left={<div style={{ padding: 8, fontSize: 12 }}>Left pane</div>} right={<div style={{ padding: 8, fontSize: 12 }}>Right pane</div>} />
          </div>
        </Swatch>
      </Section>

      <Section title="Layout (ra_12 #28 — replaces the repeated flex/gap inline styles)">
        <Swatch label="Stack (vertical, gap on the 4px-grid steps only)">
          <div style={{ width: 240 }}>
            <Stack gap={2}>
              <div className="card" style={{ padding: 8 }}>
                One
              </div>
              <div className="card" style={{ padding: 8 }}>
                Two
              </div>
              <div className="card" style={{ padding: 8 }}>
                Three
              </div>
            </Stack>
          </div>
        </Swatch>
        <Swatch label="Cluster (horizontal, wraps by default)">
          <div style={{ width: 240 }}>
            <Cluster gap={2}>
              <Chip kind="accent">flex</Chip>
              <Chip kind="success">sim</Chip>
              <Chip kind="warning">ex</Chip>
              <Chip kind="neutral">analyzer</Chip>
            </Cluster>
          </div>
        </Swatch>
        <Swatch label="KeyValue (one ad-hoc label/value pair)">
          <Cluster gap={4}>
            <KeyValue label="CPUs" value={8} />
            <KeyValue label="Memory" value="16 GB" />
          </Cluster>
        </Swatch>
      </Section>

      <Section title="PlanSummary (ra_12 #7 — every run page's Plan panel)">
        <Swatch label="Idle (nothing chosen yet)">
          <div style={{ width: 280 }}>
            <PlanSummary idleMessage="Pick a subject and ROI to see the plan." />
          </div>
        </Swatch>
        <Swatch label="Loading">
          <div style={{ width: 280 }}>
            <PlanSummary loading />
          </div>
        </Swatch>
        <Swatch label="Resolved, no conflicts">
          <div style={{ width: 280 }}>
            <PlanSummary jobs={1} cpus={4} memoryGb={8} outputs={[{ label: "sub-ernie -> TI_max.msh" }]} waits={[]} />
          </div>
        </Swatch>
        <Swatch label="Resolved, with an overwrite + a wait + warnings">
          <div style={{ width: 320 }}>
            <PlanSummary
              jobs={2}
              cpus={8}
              memoryGb={16}
              outputs={[{ label: "sub-ernie -> TI_max.msh", willOverwrite: true }, { label: "sub-101 -> TI_max.msh" }]}
              waits={["sub-ernie: waiting on flex-search (queued)"]}
              warnings={["This will overwrite an existing simulation for sub-ernie."]}
            />
          </div>
        </Swatch>
        <Swatch label="Error">
          <div style={{ width: 280 }}>
            <PlanSummary error="The server could not resolve this plan." />
          </div>
        </Swatch>
      </Section>

      <Section title="Jobs">
        <Swatch label="JobTrace">
          <div style={{ height: 36, border: "1px solid var(--line)", borderRadius: 6, display: "flex", alignItems: "center" }}>
            <JobTrace job={DEMO_JOBS[0]!} />
          </div>
        </Swatch>
        <Swatch label="JobsTable">
          <div style={{ width: 480 }}>
            <JobsTable jobs={DEMO_JOBS} onOpen={() => {}} />
          </div>
        </Swatch>
        <Swatch label="JobConsole">
          <div style={{ width: 420, height: 160 }} data-testid="gallery-job-console">
            <JobConsole sourceKey="gallery-demo" lines={DEMO_LOG_LINES} />
          </div>
        </Swatch>
        <Swatch label="ArtifactList">
          <div style={{ width: 340 }}>
            <ArtifactList
              artifacts={[
                { path: "/derivatives/ti-toolbox/reports/report.html", kind: "report", label: "report.html" },
                { path: "/derivatives/SimNIBS/sub-101/Simulations/TI/TI_max.nii.gz", kind: "nifti", label: "TI_max.nii.gz" },
              ]}
              onOpen={() => {}}
              onView={() => {}}
              onReveal={() => {}}
            />
          </div>
        </Swatch>
      </Section>

      {/* The slim 3D scene. Mounted on a click, not on load: a WebGL2 context and a
          150k-triangle upload are not what the rest of this page's screenshots should pay for. */}
      <SceneGallery />
    </div>
  );
}
