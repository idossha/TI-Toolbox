/**
 * Ex / mEx sections: the leadfield precondition strip, the electrode buckets (or pool), the
 * current sweep, and the mTI carrier options. Merged from `optimizer-ex/{ExForm,MExForm,
 * ElectrodeBuckets,LeadfieldPanel,HelpButton}.tsx`; see `pages/optimizer/PARITY.md`.
 *
 * The leadfield is a **gate, not a form field** (wireframes §4): a 28 px strip under the Method
 * segment that states the fact and offers the one action that fixes it, rather than a card with a
 * radio list the user must interpret.
 */
import { useQuery } from "@tanstack/react-query";
import { CircleHelp, Zap } from "lucide-react";
import { Button } from "../../ui/Button";
import { Chip } from "../../ui/Status";
import { Field } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { SelectionPicker, type SelectionItem } from "../../ui/SelectionList";
import { Checkbox } from "../../ui/Toggle";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Popover } from "../../ui/Overlay";
import { Skeleton } from "../../ui/Feedback";
import { FormSection } from "../../ui/Layout";
import type { EegNet, Leadfield } from "./api";
import { planLeadfieldEta } from "./api";
import { durationLabel, estimateLabel } from "../_shared/run";
import {
  BUCKET_LABELS,
  BUCKET_TOOLTIPS,
  EX_BUCKET_KEYS,
  MEX_BUCKET_KEYS,
  MTI_CHANNELS_HELP,
  MTI_CHANNEL_ARCHITECTURES,
  MTI_SYMMETRY_HELP,
  formatBytes,
  type ExFormState,
  type MExFormState,
} from "./exConfig";
import { leadfieldFor, netOptions } from "./nets";
import { exCost, mexCost } from "./cost";

/** A `?` popover for the two mTI options whose consequences a label cannot carry. */
function HelpButton({ label, text }: { label: string; text: string }) {
  return (
    <Popover trigger={<button type="button" className="optimizer-help" aria-label={`About ${label}`}><CircleHelp size={12} /></button>}>
      <p className="text-dense" style={{ maxWidth: 360, whiteSpace: "pre-line" }}>
        {text}
      </p>
    </Popover>
  );
}

/**
 * How long generating THIS net's leadfield would take here, from the server's plan.
 *
 * Per (subject, net) because that is what the number depends on — one FEM solve per electrode,
 * on this machine's cores, emulated or not (`tit/jobs/eta.py`). Undefined while it loads, so the
 * button says nothing rather than a wrong thing; `null` when the server cannot model it.
 */
function useLeadfieldEta(subjectId: string | undefined, net: string | null) {
  return useQuery({
    queryKey: ["leadfield-eta", subjectId, net],
    queryFn: () => planLeadfieldEta(subjectId as string, net as string),
    enabled: Boolean(subjectId && net),
    staleTime: 5 * 60_000,
  });
}

export function LeadfieldStrip({
  leadfields,
  loading,
  nets,
  selectedNet,
  subjectId,
  onSelectNet,
  onGenerate,
  generating,
}: {
  leadfields: Leadfield[] | undefined;
  loading: boolean;
  nets: EegNet[] | undefined;
  selectedNet: string | null;
  /** Whose leadfield — the estimate is per subject (their head mesh) as well as per net. */
  subjectId?: string;
  onSelectNet: (net: string) => void;
  onGenerate: (net: string) => void;
  generating: boolean;
}) {
  // Hooks before the early return: the strip renders a skeleton while the catalog loads, and a
  // conditional hook would break on the transition out of it.
  const eta = useLeadfieldEta(subjectId, selectedNet);
  if (loading) return <Skeleton height={28} />;
  // Both catalogs spell a net differently (`nets.ts`): every value here is the bare name, which is
  // also what `LeadfieldGenerator` wants for `eeg_net` (it appends the `.csv` itself).
  const current = leadfieldFor(leadfields, selectedNet);
  const options = netOptions(leadfields, nets);
  const ready = current?.exists ?? false;
  const etaMinutes = eta.data?.minutes ?? null;

  return (
    <div className="optimizer-precondition" data-testid="leadfield-strip">
      <span className="text-eyebrow">Leadfield</span>
      <Select value={selectedNet ?? undefined} onValueChange={onSelectNet} options={options} placeholder="Select an EEG net…" aria-label="EEG net" />
      {ready ? (
        <Chip kind="success">{formatBytes(current?.size_bytes ?? 0)}</Chip>
      ) : (
        <>
          {/* No "required" chip (maintainer, 2026-09-06): the sentence beside it already says the
              leadfield is not there, and a red missing-chip made a normal next step read as an
              error. One plain sentence, one button. */}
          <span className="field-help">No leadfield for this net yet.</span>
          <Button
            variant="secondary"
            size="sm"
            icon={<Zap size={14} />}
            loading={generating}
            disabled={!selectedNet}
            onClick={() => selectedNet && onGenerate(selectedNet)}
            /* The estimate is for THIS net on THIS machine: one FEM solve per electrode, so a
               19-electrode cap is minutes and a 256-electrode one is over an hour under
               emulation. Hidden while it loads rather than guessed. */
            title={
              typeof etaMinutes === "number"
                ? `${estimateLabel(etaMinutes, eta.data?.system)} — one FEM solve per electrode in this net`
                : undefined
            }
            data-eta-minutes={typeof etaMinutes === "number" ? etaMinutes : undefined}
          >
            {typeof etaMinutes === "number" ? `Generate (≈ ${durationLabel(etaMinutes)})` : "Generate"}
          </Button>
        </>
      )}
    </div>
  );
}

function BucketGrid({
  keys,
  values,
  onChange,
  electrodes,
  disabled,
}: {
  keys: readonly string[];
  values: Record<string, string[]>;
  onChange: (key: string, electrodes: string[]) => void;
  electrodes: string[];
  disabled?: boolean;
}) {
  const options: SelectionItem[] = electrodes.map((e) => ({ id: e, label: e }));
  // No wrapper grid: `FormSection` already lays its children out as a `.form-grid`, and nesting a
  // second one squeezed every bucket into half a column (round-1 measurement).
  //
  // One grammar (plan C1): a bucket is a selection out of the net's 185 electrodes, so it is the
  // same list — filter, ⇧-range, ⌘-toggle, All · None, `N of M selected` — as the subject table and
  // the ROI regions, behind a trigger that states what is in the bucket. The chip row it replaces
  // could hold about two names before truncating, so the closed control could not answer "what is
  // in E1+?", and picking a run of eight neighbouring electrodes meant eight separate clicks
  // through a popover that closed itself after each one.
  return (
    <>
      {keys.map((key) => (
        <Field key={key} label={BUCKET_LABELS[key] ?? key} help={BUCKET_TOOLTIPS[key]}>
          <SelectionPicker
            items={options}
            value={values[key] ?? []}
            onChange={(v) => onChange(key, v)}
            label={`${BUCKET_LABELS[key] ?? key} electrodes`}
            title={`${BUCKET_LABELS[key] ?? key} — choose electrodes`}
            headers={{ label: "Electrode" }}
            filterPlaceholder="Filter electrodes…"
            idPrefix={`bucket-${key}`}
            placeholder="Add electrode…"
            disabled={disabled}
          />
        </Field>
      ))}
    </>
  );
}

/** Tier 1 for Ex: the search space itself, with its cost stated beside the control that sets it. */
export function ExElectrodesSection({
  form,
  onChange,
  electrodes,
  disabled,
}: {
  form: ExFormState;
  onChange: (patch: Partial<ExFormState>) => void;
  electrodes: string[];
  disabled?: boolean;
}) {
  const cost = exCost(form);
  return (
    <FormSection title="Electrodes">
      <Field label="Search space">
        <SegmentedControl
          value={form.electrodeMode}
          onValueChange={(v) => onChange({ electrodeMode: v as "bucketed" | "all" })}
          options={[
            { value: "bucketed", label: "Bucketed" },
            { value: "all", label: "All combinations" },
          ]}
          aria-label="Search space"
        />
      </Field>
      {form.electrodeMode === "bucketed" ? (
        <BucketGrid keys={EX_BUCKET_KEYS} values={form.buckets} onChange={(k, v) => onChange({ buckets: { ...form.buckets, [k]: v } })} electrodes={electrodes} disabled={disabled} />
      ) : (
        <Field label="Electrode pool" help="Any electrode in this set can be assigned to any position." className="optimizer-span">
          <SelectionPicker
            items={electrodes.map((e) => ({ id: e, label: e }))}
            value={form.pool}
            onChange={(v) => onChange({ pool: v })}
            label="Electrode pool"
            title="Electrode pool"
            headers={{ label: "Electrode" }}
            filterPlaceholder="Filter electrodes…"
            idPrefix="electrode-pool"
            placeholder="Add electrode…"
            disabled={disabled}
          />
        </Field>
      )}
      <p className="optimizer-cost optimizer-span" data-testid="optimizer-cost-ex">
        {cost.line}
      </p>
    </FormSection>
  );
}

/** Ex's current sweep: total, step and per-channel limit — the three numbers that set `splits`. */
export function ExCurrentSection({ form, onChange }: { form: ExFormState; onChange: (patch: Partial<ExFormState>) => void }) {
  const cost = exCost(form);
  return (
    <FormSection title="Current" collapsible summary={`${form.totalCurrent} mA total · ${form.currentStep} mA step · ${cost.splits} splits`}>
      {/* Three numbers about one thing, on one line (coordinator, 2026-09-06 — the two-up form grid
          put Total and Step side by side and wrapped Channel limit onto a third row of its own).
          `.field-row-inline` is the shared idiom the Simulator's Electrodes row uses: label-left
          fields sized to their content, 24px apart. */}
      <div className="field-row-inline optimizer-current-row">
        <Field label="Total current" help="Distributed between the two channels.">
          <NumberInput value={form.totalCurrent} onValueChange={(v) => onChange({ totalCurrent: v ?? 2.0 })} unit="mA" min={0.1} max={10} step={0.1} />
        </Field>
        <Field label="Step" help="Step size for current-ratio iterations.">
          <NumberInput value={form.currentStep} onValueChange={(v) => onChange({ currentStep: v ?? 0.2 })} unit="mA" min={0.01} max={2} step={0.01} />
        </Field>
        <Field label="Channel limit" help="Maximum current per channel (must be ≤ total current).">
          <NumberInput value={form.channelLimit ?? undefined} onValueChange={(v) => onChange({ channelLimit: v ?? null })} unit="mA" min={0.1} max={10} step={0.1} />
        </Field>
      </div>
    </FormSection>
  );
}

/** Tier 1 for mEx: eight buckets, one per pole of the four bipolar pairs. */
export function MExElectrodesSection({
  form,
  onChange,
  electrodes,
  disabled,
}: {
  form: MExFormState;
  onChange: (patch: Partial<MExFormState>) => void;
  electrodes: string[];
  disabled?: boolean;
}) {
  const cost = mexCost(form);
  return (
    <FormSection title="Electrode pairs">
      <BucketGrid keys={MEX_BUCKET_KEYS} values={form.buckets} onChange={(k, v) => onChange({ buckets: { ...form.buckets, [k]: v } })} electrodes={electrodes} disabled={disabled} />
      <p className="optimizer-cost optimizer-span" data-testid="optimizer-cost-mex">
        {cost.line}
      </p>
    </FormSection>
  );
}

/** mTI carrier wiring, per-pair current and the symmetry search. */
export function MExCarrierSection({ form, onChange }: { form: MExFormState; onChange: (patch: Partial<MExFormState>) => void }) {
  const architecture = MTI_CHANNEL_ARCHITECTURES.find((a) => a.value === form.channelsArchitecture);
  return (
    <FormSection
      title="Carriers"
      collapsible
      summary={`${form.currentMa} mA per pair · ${architecture?.label ?? form.channelsArchitecture}${form.symmetricBucket ? " · symmetric" : ""}`}
    >
      <>
        <Field label="Pair current" help="Current delivered by each of the four bipolar pairs.">
          <NumberInput value={form.currentMa} onValueChange={(v) => onChange({ currentMa: v ?? 2.0 })} unit="mA" min={0.1} max={10} step={0.1} />
        </Field>
        <Field label="Carrier wiring" helpSlot={<HelpButton label="carrier wiring" text={MTI_CHANNELS_HELP} />}>
          <Select
            value={form.channelsArchitecture}
            onValueChange={(v) => onChange({ channelsArchitecture: v })}
            options={MTI_CHANNEL_ARCHITECTURES.map((a) => ({ value: a.value, label: a.label }))}
          />
        </Field>
        <Field label="Symmetry" helpSlot={<HelpButton label="symmetric bucket search" text={MTI_SYMMETRY_HELP} />}>
          <Checkbox checked={form.symmetricBucket} onCheckedChange={(on) => onChange({ symmetricBucket: on })} label="Force left/right symmetry" />
        </Field>
        <Field label="Symmetry pairing">
          <Select
            value={form.symmetryPairing}
            onValueChange={(v) => onChange({ symmetryPairing: v as "within_pairs" | "cross_pairs" })}
            options={[
              { value: "within_pairs", label: "Within each pair" },
              { value: "cross_pairs", label: "Cross pairs (E1↔E3, E2↔E4)" },
            ]}
            disabled={!form.symmetricBucket}
          />
        </Field>
      </>
    </FormSection>
  );
}
