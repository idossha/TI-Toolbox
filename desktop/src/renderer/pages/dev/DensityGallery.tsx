/**
 * The v2 density block of the design gallery (DESIGN.md §3): every primitive the density pass
 * added or reshaped, side by side, plus a ruler that prints the measured height of a Field row, a
 * FormSection header and a table row so a screenshot can be checked against the acceptance
 * numbers rather than eyeballed.
 *
 * Rendered above the v1 gallery by `pages/dev/index.tsx`. Dev builds only.
 */
import { useEffect, useRef, useState } from "react";
import { Button } from "../../ui/Button";
import { ActionBar, ContextBar, Crumb, CrumbSeparator, RefetchBar } from "../../ui/Chrome";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { Field, TextInput, useChangedFields } from "../../ui/Field";
import { EmptyState, InlineError, Skeleton } from "../../ui/Feedback";
import { Card, CardBody, CardHeader, FormSection } from "../../ui/Layout";
import { NumberInput } from "../../ui/NumberInput";
import { PathInput } from "../../ui/PathInput";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Select } from "../../ui/Select";
import { Chip, StatusDot } from "../../ui/Status";

function Block({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: "var(--space-6)" }}>
      <h3 className="text-eyebrow" style={{ marginBottom: "var(--space-1)" }}>
        {title}
      </h3>
      {note && (
        <p className="field-help" style={{ marginBottom: "var(--space-2)", maxWidth: "72ch" }}>
          {note}
        </p>
      )}
      {children}
    </section>
  );
}

/** A bordered pane the width of the v2 work column, so the gallery shows the real measure. */
function Pane({ children, width = 880 }: { children: React.ReactNode; width?: number }) {
  return (
    <div style={{ width, maxWidth: "100%", border: "1px solid var(--line)", borderRadius: "var(--radius-card)", padding: "0 var(--pane-pad)" }}>
      {children}
    </div>
  );
}

interface RulerRow {
  what: string;
  measured: number;
  target: number;
}
const RULER_COLUMNS: DataTableColumn<RulerRow>[] = [
  { header: "Measured element", accessorKey: "what" },
  { header: "px", numeric: true, accessorKey: "measured" },
  { header: "target", numeric: true, accessorKey: "target" },
];

interface SampleRow {
  subject: string;
  sims: number;
  goal: string;
}
const SAMPLE_ROWS: SampleRow[] = [
  { subject: "ernie", sims: 3, goal: "mean" },
  { subject: "101", sims: 1, goal: "focality" },
  { subject: "102", sims: 0, goal: "max" },
];
const SAMPLE_COLUMNS: DataTableColumn<SampleRow>[] = [
  { header: "Subject", accessorKey: "subject" },
  { header: "Sims", numeric: true, accessorKey: "sims" },
  { header: "Goal", accessorKey: "goal" },
];

const GOAL_OPTIONS = [
  { value: "mean", label: "Mean" },
  { value: "max", label: "Max" },
  { value: "focality", label: "Focality" },
];

interface DemoForm {
  goal: string;
  intensity: number;
  shape: string;
}
const DEMO_DEFAULTS: DemoForm = { goal: "mean", intensity: 1.5, shape: "ellipse" };

export function DensityGallery() {
  const fieldRef = useRef<HTMLDivElement>(null);
  const sectionHeaderRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLDivElement>(null);
  const [ruler, setRuler] = useState<RulerRow[]>([]);
  const [shell, setShell] = useState<RulerRow[]>([]);

  const [method, setMethod] = useState("flex");
  const [scope, setScope] = useState("subject");
  const [goal, setGoal] = useState("mean");
  const [intensity, setIntensity] = useState<number | undefined>(2);
  const isChanged = useChangedFields<DemoForm>({ goal, intensity: intensity ?? 0, shape: "ellipse" }, DEMO_DEFAULTS);

  useEffect(() => {
    // The ruler is the point of this block: the acceptance numbers are measured, not asserted by
    // eye. Measuring happens in an animation frame rather than straight out of the effect so the
    // web fonts and the first paint have landed — and so the state write is not a synchronous
    // cascading render out of an effect body.
    const frame = requestAnimationFrame(() => {
      const rows: RulerRow[] = [];
      const field = fieldRef.current?.querySelector(".field");
      const header = sectionHeaderRef.current?.querySelector(".form-section-header");
      const row = tableRef.current?.querySelector<HTMLElement>(".data-table tbody tr");
      if (field) rows.push({ what: "Field row (label-left)", measured: round(field.getBoundingClientRect().height), target: 28 });
      if (header) rows.push({ what: "FormSection header", measured: round(header.getBoundingClientRect().height), target: 28 });
      if (row) rows.push({ what: "Table row", measured: round(row.getBoundingClientRect().height), target: 28 });
      setRuler(rows);

      // The shell's own v3 numbers, read from the live chrome around this page (DESIGN.md §2.1,
      // §12.1) — the same rects `tests/e2e/_metrics.ts` samples, printed where a human can see
      // them without opening an artifact directory.
      const w = (sel: string): number => {
        const el = document.querySelector(sel);
        return el ? round(el.getBoundingClientRect().width) : 0;
      };
      const wide = window.innerWidth >= 1440;
      setShell([
        { what: "Nav rail", measured: w('[data-testid="nav-rail"]'), target: wide ? 216 : 56 },
        { what: "Content box", measured: w('[data-testid="shell-content"]'), target: window.innerWidth - (wide ? 216 : 56) },
        { what: "Page header", measured: round(document.querySelector(".page-header")?.getBoundingClientRect().height ?? 0), target: 0 },
      ]);
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div style={{ maxWidth: 1100 }}>
      <h2 className="text-section" style={{ marginBottom: "var(--space-1)" }}>
        Density (v2)
      </h2>
      <p className="field-help" style={{ marginBottom: "var(--space-6)", maxWidth: "80ch" }}>
        One shipped density, no user switch. Base type 13/18, controls and rows 28 px, flush form sections, label-left field rows,
        no page headers, sticky 44 px action bar.
      </p>

      <Block title="Type scale" note="Six steps. 11 px is the chip and eyebrow step only, and never pairs with --ink-3.">
        <Pane width={520}>
          <div style={{ padding: "var(--space-3) 0", display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="text-micro">11/14 · chips, eyebrows, status bar</span>
            <span className="text-caption">12/16 · labels, help, summaries</span>
            <span className="text-body">13/18 · base — every control, every table cell</span>
            <span className="text-prose">14/20 · running prose (Help, About)</span>
            <span className="text-emphasis">16/22 · emphasis and section headings</span>
            <span className="text-page-title">20/26 · page title (Settings, Help only)</span>
          </div>
        </Pane>
      </Block>

      <Block
        title="Field — label-left row"
        note="Default is a 28 px grid row: label in a 160 px gutter, control right, help behind an (i) popover, units inside the control. Stacked and full-bleed are the two escapes."
      >
        <div ref={fieldRef}>
          <Pane width={520}>
            <div style={{ padding: "var(--space-3) 0", display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              <Field label="Goal" help="What the optimizer maximises inside the ROI.">
                <Select value={goal} onValueChange={setGoal} options={GOAL_OPTIONS} />
              </Field>
              <Field label="Intensity" changed={isChanged("intensity")}>
                <NumberInput value={intensity} onValueChange={setIntensity} unit="mA" step={0.1} />
              </Field>
              <Field label="Electrode shape" changed={false}>
                <TextInput value="ellipse" readOnly />
              </Field>
              <Field label="Subject" required error="Subject sub-999 does not exist.">
                <TextInput value="sub-999" onChange={() => {}} invalid />
              </Field>
              <Field label="Notes" layout="stacked">
                <TextInput value="layout=stacked keeps the label above the control" onChange={() => {}} />
              </Field>
              <Field label="Project directory">
                <PathInput value="/mnt/example/derivatives/SimNIBS" onValueChange={() => {}} />
              </Field>
            </div>
          </Pane>
        </div>
      </Block>

      <Block
        title="FormSection — flush, collapsible, self-describing"
        note="No card, no shadow: an 11 px eyebrow, a 1 px rule and a 12 px body. A collapsed section states its own values; a changed child gets an accent dot, an errored one a danger dot. An advanced group holding non-default values force-opens and says how many."
      >
        <div ref={sectionHeaderRef}>
          <Pane>
            <FormSection
              title="Electrodes"
              collapsible
              changed
              summary="ellipse · 8×8 mm · gel 4 mm"
              onReset={() => {}}
              advanced={
                <>
                  <Field label="Gel thickness">
                    <NumberInput value={4} onValueChange={() => {}} unit="mm" />
                  </Field>
                  <Field label="Connector spacing">
                    <NumberInput value={2} onValueChange={() => {}} unit="mm" />
                  </Field>
                </>
              }
              advancedChangedCount={2}
            >
              <Field label="Shape">
                <SegmentedControl
                  aria-label="Electrode shape"
                  value="ellipse"
                  onValueChange={() => {}}
                  options={[
                    { value: "ellipse", label: "Ellipse" },
                    { value: "rect", label: "Rectangle" },
                  ]}
                />
              </Field>
              <Field label="Dimensions">
                <NumberInput value={8} onValueChange={() => {}} unit="mm" />
              </Field>
            </FormSection>
            <FormSection title="Conductivity" collapsible defaultOpen={false} summary="isotropic · SimNIBS defaults">
              <Field label="Anisotropy">
                <TextInput value="isotropic" readOnly />
              </Field>
            </FormSection>
            <FormSection title="Output" collapsible defaultOpen={false} error summary="TI_max · mesh + voxel">
              <Field label="Field">
                <TextInput value="TI_max" readOnly />
              </Field>
            </FormSection>
          </Pane>
        </div>
      </Block>

      <Block title="SegmentedControl" note="One-of-N in one row, where a RadioGroup would spend a block: Method, Scope, Space.">
        <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap" }}>
          <SegmentedControl
            aria-label="Method"
            value={method}
            onValueChange={setMethod}
            options={[
              { value: "flex", label: "Flex" },
              { value: "ex", label: "Ex" },
              { value: "mex", label: "mEx" },
            ]}
          />
          <SegmentedControl
            aria-label="Scope"
            value={scope}
            onValueChange={setScope}
            options={[
              { value: "subject", label: "Subject" },
              { value: "group", label: "Group" },
              { value: "figures", label: "Figures" },
            ]}
          />
          <SegmentedControl
            aria-label="Layout"
            size="sm"
            value="2x2"
            onValueChange={() => {}}
            options={[
              { value: "1x1", label: "1×1" },
              { value: "2x2", label: "2×2" },
              { value: "3d", label: "3D", disabled: true },
            ]}
          />
        </div>
      </Block>

      <Block title="Shell chrome" note="Context bar 40 · action bar 44 · status bar 24. The design system owns the numbers; the shell fills the slots.">
        <Pane>
          <div style={{ margin: "0 calc(var(--pane-pad) * -1)" }}>
            <ContextBar
              end={
                <>
                  <span className="cluster gap-1 items-center">
                    <StatusDot kind="success" /> connected
                  </span>
                  <span>3 running</span>
                </>
              }
            >
              <Crumb label="Dataset 000" switcher />
              <CrumbSeparator />
              <Crumb
                label="ernie"
                switcher
                meta={
                  <>
                    <Chip kind="success">raw</Chip>
                    <Chip kind="success">fs</Chip>
                    <Chip kind="success">m2m</Chip>
                  </>
                }
              />
              <Crumb label="+2 more" switcher />
            </ContextBar>
            <RefetchBar active />
            {/* The action bar lives INSIDE the work pane's scroll container — that is what makes
                it stick to the bottom edge of the pane rather than to the window, and it is the
                same structure `PageLayout` builds. */}
            <div style={{ height: 168, overflow: "auto", display: "flex", flexDirection: "column" }}>
              <div style={{ flex: 1, minHeight: 0, padding: "0 var(--space-3)" }}>
                <p className="field-help" style={{ padding: "var(--space-2) 0" }}>
                  Work pane. Scroll it: the action bar stays on the bottom edge of this pane, next to the control you were last
                  editing — not 500 px above it in a right-hand panel.
                </p>
                <div style={{ height: 120 }} />
              </div>
              <ActionBar
                digest="2 jobs · 8 CPU · 16 GB · 1 overwrite"
                warningCount={2}
                onWarningsClick={() => {}}
                secondary={<Button variant="secondary">Save preset</Button>}
                primary={<Button variant="primary">Run 2 simulations</Button>}
              />
            </div>
          </div>
        </Pane>
        <div style={{ marginTop: "var(--space-3)", width: 520, maxWidth: "100%" }}>
          <ActionBar
            digest="Pick a subject and an ROI"
            blocked
            primary={
              <Button variant="primary" disabled>
                Run flex search
              </Button>
            }
          />
        </div>
      </Block>

      <Block
        title="Empty, loading, failed"
        note="An inline empty is left-aligned and at most two lines. Skeletons are sized in rows, never slabs, and only on first load; a refetch is the 2 px bar. A failed load is an inline error in the surface that failed, never a toast."
      >
        <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap", alignItems: "flex-start" }}>
          <div style={{ flex: "none", width: 300 }}>
            <Card>
              <CardHeader title="Inline empty (in a panel)" />
              <CardBody>
                <EmptyState variant="inline" message="No simulations for ernie yet." actionLabel="Run one" onAction={() => {}} />
              </CardBody>
            </Card>
          </div>
          <div style={{ flex: "none", width: 260 }}>
            <Card>
              <CardHeader title="Skeleton, 3 rows" />
              <CardBody>
                <Skeleton rows={3} />
              </CardBody>
            </Card>
          </div>
          <div style={{ flex: "none", width: 380 }}>
            <Card>
              <CardHeader title="Inline error" />
              <CardBody>
                <InlineError
                  message="Could not load the subject list."
                  detail="GET /api/subjects — 503 upstream unavailable"
                  onAction={() => {}}
                />
              </CardBody>
            </Card>
          </div>
        </div>
      </Block>

      <Block
        title="Density ruler"
        note="Measured with getBoundingClientRect after layout — the numbers a screenshot should be checked against. The sample table on the left is what the row height is read from."
      >
        <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap", alignItems: "flex-start" }}>
          <div ref={tableRef} style={{ width: 340 }}>
            <DataTable data={SAMPLE_ROWS} columns={SAMPLE_COLUMNS} getRowId={(r) => r.subject} />
          </div>
          <div style={{ width: 460, maxWidth: "100%" }}>
            <DataTable data={ruler} columns={RULER_COLUMNS} getRowId={(r) => r.what} emptyMessage="Measuring…" />
          </div>
        </div>
      </Block>

      <Block
        title="Shell ruler (v3)"
        note="The shell's own numbers, read from the chrome around this page — the same rects tests/e2e/_metrics.ts samples. The rail is icons below 1440 and labelled at or above it (program Q1); the page-header budget outside Settings and Help is 0. The three status cells this page registered are in the bar below, and the one with a null value is not."
      >
        <div style={{ width: 460, maxWidth: "100%" }} data-testid="shell-ruler">
          <DataTable data={shell} columns={RULER_COLUMNS} getRowId={(r) => r.what} emptyMessage="Measuring…" />
        </div>
      </Block>
    </div>
  );
}

function round(n: number): number {
  return Math.round(n * 10) / 10;
}
