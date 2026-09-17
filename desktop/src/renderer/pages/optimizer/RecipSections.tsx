/**
 * Reciprocity-search sections — the third method's half of the row editor.
 *
 * Same visual language as `ExSections.tsx`, and deliberately shorter than either neighbour: a
 * reciprocity run has no electrode buckets and no current sweep, because it does not enumerate
 * montages. What it needs is the target (a point, or an ROI), the direction the field should be
 * strongest in, what "best" means, and how many channels to build — so those are the sections, in
 * that order, with the leadfield still the gate strip the Ex methods use (`LeadfieldStrip`).
 *
 * The leadfield picker itself is NOT re-implemented here: the row editor renders `LeadfieldStrip`
 * for every non-flex method, so Recip reuses it unchanged.
 */
import { CircleHelp } from "lucide-react";
import { Field } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { CoordinateInput } from "../../ui/CoordinateInput";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Slider } from "../../ui/Toggle";
import { Popover } from "../../ui/Overlay";
import { FormSection } from "../../ui/Layout";
import { RoiPicker, type RoiMode, type RoiValue } from "../_shared/roi";
import { recipCost } from "./cost";
import { recipTopK, type RecipChannels, type RecipFormState, type RecipObjective } from "./recipConfig";

const DIRECTION_HELP =
  "Any direction maximises the amplitude of the TI envelope, whatever way it points.\n\n" +
  "A vector optimises the envelope of the field projected on that direction (SimNIBS's directional " +
  "TI), in the target's own coordinate space. The runner normalises it, so only the direction matters, " +
  "not the length.";

const OBJECTIVE_HELP =
  "Intensity ranks candidates by the mean envelope in the target.\n\n" +
  "Focality ranks them by mean(ROI)^(1 + weight) / p95(non-ROI grey matter) — the same threshold-free " +
  "focality score the flex goal `focality_tf` uses. Weight 0 is pure focality; higher weights buy " +
  "intensity back.";

const TOP_K_HELP =
  "How many of the best reciprocity pairs are combined into channel candidates. Left empty it follows " +
  "the runner's defaults (40 pairs for 2 channels, 20 for 4), chosen so the disjoint combinations are " +
  "worth evaluating. Raising it widens the candidate set combinatorially, up to the runner's cap of 1000.";

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
 * The target: a coordinate with a radius, or the shared ROI picker.
 *
 * A point is offered first because that is the gesture reciprocity is *for* — one coordinate, one
 * read of the leadfield — but an ROI target is the accurate one when the user has a region: the
 * pick is made from the ROI-MEAN field, which is the whole difference between ranking 3rd and 75th
 * against an exhaustive search (the study behind this method).
 */
export function RecipTargetSection({
  form,
  onChange,
  roi,
  onRoiChange,
  roiModes,
  subject,
  onOpenViewer,
}: {
  form: RecipFormState;
  onChange: (patch: Partial<RecipFormState>) => void;
  roi: RoiValue;
  onRoiChange: (roi: RoiValue) => void;
  roiModes: RoiMode[];
  subject?: string;
  onOpenViewer?: () => void;
}) {
  return (
    <FormSection title="Target">
      <Field label="Target" className="optimizer-span">
        <SegmentedControl
          value={form.targetMode}
          onValueChange={(v) => onChange({ targetMode: v === "roi" ? "roi" : "point" })}
          options={[
            { value: "point", label: "Point" },
            { value: "roi", label: "ROI" },
          ]}
          aria-label="Target kind"
        />
      </Field>
      {form.targetMode === "point" ? (
        <Field
          label="Coordinate"
          className="optimizer-span"
          help="The elements within the radius of this point are the target. A radius of 0 uses the single nearest element."
        >
          <CoordinateInput
            value={form.point}
            onValueChange={(point) => onChange({ point: { ...form.point, ...point } })}
            space={form.pointSpace}
            onSpaceChange={(pointSpace) => onChange({ pointSpace })}
            withRadius
          />
        </Field>
      ) : (
        <div className="optimizer-span">
          <RoiPicker
            value={roi}
            onChange={onRoiChange}
            modes={roiModes}
            subject={subject}
            allowCombine={false}
            onOpenViewer={roi.mode === "spherical" ? onOpenViewer : undefined}
          />
        </div>
      )}
    </FormSection>
  );
}

/** Direction, objective, channels and the top-k override — everything that is not the target. */
export function RecipSearchSection({ form, onChange }: { form: RecipFormState; onChange: (patch: Partial<RecipFormState>) => void }) {
  const cost = recipCost(form);
  return (
    <FormSection title="Search">
      <Field label="Direction" helpSlot={<HelpButton label="field direction" text={DIRECTION_HELP} />} className="optimizer-span">
        <SegmentedControl
          value={form.directionMode}
          onValueChange={(v) => onChange({ directionMode: v === "vector" ? "vector" : "any" })}
          options={[
            { value: "any", label: "Any direction" },
            { value: "vector", label: "Along a vector" },
          ]}
          aria-label="Direction mode"
        />
      </Field>
      {form.directionMode === "vector" && (
        <Field label="Vector" className="optimizer-span" help="Direction components in the target's coordinate space; normalised by the runner.">
          <CoordinateInput value={form.direction} onValueChange={(direction) => onChange({ direction })} />
        </Field>
      )}
      <Field label="Objective" helpSlot={<HelpButton label="objective" text={OBJECTIVE_HELP} />} className="optimizer-span">
        <SegmentedControl
          value={form.objective}
          onValueChange={(v) => onChange({ objective: v as RecipObjective })}
          options={[
            { value: "intensity", label: "Intensity" },
            { value: "focality", label: "Focality" },
          ]}
          aria-label="Objective"
        />
      </Field>
      {/* The weight only means anything to the focality score, so it is only there when that is
          what is being optimised — the same rule the flex Objective section follows. */}
      {form.objective === "focality" && (
        <Field label="Intensity preference" className="optimizer-span" help="0 is pure focality; higher weights favour a stronger field in the target.">
          <Slider
            value={form.focalityWeight}
            onValueChange={(focalityWeight) => onChange({ focalityWeight })}
            min={0}
            max={1}
            step={0.05}
            aria-label="Focality weight"
            data-testid="recip-focality-weight"
          />
        </Field>
      )}
      <Field label="Channels" help="Two channels is classic TI; four build a multipolar (mTI) envelope. Odd counts have no verified envelope.">
        <SegmentedControl
          value={String(form.nChannels)}
          onValueChange={(v) => onChange({ nChannels: Number(v) as RecipChannels })}
          /* 2 or 4: the verified envelope is defined for an even number of channels only
             (`tit.calc.get_TI_vectors`), so 3 is not a choice the runner would accept. */
          options={[
            { value: "2", label: "2 (TI)" },
            { value: "4", label: "4 (mTI)" },
          ]}
          aria-label="Channels"
        />
      </Field>
      <Field label="Current" help="Delivered by each channel.">
        <NumberInput value={form.currentMa} onValueChange={(v) => onChange({ currentMa: v ?? 1 })} unit="mA" min={0.1} max={10} step={0.1} />
      </Field>
      <p className="optimizer-cost optimizer-span" data-testid="optimizer-cost-recip">
        {cost.line}
      </p>
    </FormSection>
  );
}

/** The two knobs a normal run never touches, closed by default. */
export function RecipAdvancedSection({ form, onChange }: { form: RecipFormState; onChange: (patch: Partial<RecipFormState>) => void }) {
  return (
    <FormSection
      title="Advanced"
      collapsible
      summary={`top ${recipTopK(form)} pairs${form.topK === null ? " (default)" : ""} · ${form.gmSubsample.toLocaleString("en-US")} GM samples`}
    >
      <Field label="Top-k pairs" helpSlot={<HelpButton label="top-k pairs" text={TOP_K_HELP} />}>
        <NumberInput
          value={form.topK ?? undefined}
          onValueChange={(v) => onChange({ topK: v ?? null })}
          min={form.nChannels}
          max={200}
          step={1}
          placeholder={`auto (${recipTopK({ ...form, topK: null })})`}
          aria-label="Top-k pairs"
        />
      </Field>
      <Field label="GM subsample" help="Grey-matter elements sampled outside the ROI to score focality. Seeded, so runs are comparable.">
        <NumberInput value={form.gmSubsample} onValueChange={(v) => onChange({ gmSubsample: v ?? 100000 })} min={1000} max={1000000} step={1000} />
      </Field>
    </FormSection>
  );
}
