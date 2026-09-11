import type { ComponentProps } from "react";
import { Info } from "lucide-react";
import { RoiPicker, type TissueKind } from "../_shared/roi";
import { Checkbox } from "../../ui/Toggle";
import { Popover } from "../../ui/Overlay";
import { Field } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { ANALYZER_ROI_MODES, TISSUE_OPTIONS, type AnalyzerRow } from "./JobRows";

/** The same target and compartment controls for a page job or a pipeline step. */
export function AnalyzerSettings({row,onChange,onOpenViewer}: {row:AnalyzerRow;onChange:(patch:Partial<AnalyzerRow>)=>void;onOpenViewer?:ComponentProps<typeof RoiPicker>["onOpenViewer"]}) {
  return (
          <div className="analysis-target-editor" data-testid="analysis-target-editor" data-row={row.id}>
            <RoiPicker
              value={row.roi}
              onChange={(roi) => onChange({ roi })}
              modes={[...ANALYZER_ROI_MODES]}
              showMaskTissues={false}
              subject={row.subjectId || undefined}
              space={row.space === "voxel" ? "mni" : "subject"}
              onOpenViewer={onOpenViewer}
            />
            {(row.roi.mode === "cortical" || row.roi.mode === "subcortical") && (
              /* One line, not two: the checkbox and the (i) that explains it, the same shape as
                 the Combine switch on the table's footer. The paragraph this replaces said in two
                 sentences what the target line now says in one word ("combined"). */
              <div className="analysis-target-combine" data-testid="analysis-target-combine">
                <Checkbox
                  checked={row.combine}
                  onCheckedChange={(on) => onChange({ combine: on })}
                  label="Combine regions into one ROI"
                />
                <Popover
                  trigger={
                    <button type="button" className="field-help-trigger" aria-label="Help">
                      <Info size={12} aria-hidden />
                    </button>
                  }
                >
                  <div className="field-help-popover">
                    <div className="field-help-popover-title">Combine regions into one ROI</div>
                    On, the selected regions are measured together as one ROI. Off, each region is its own
                    analysis — one job per region.
                  </div>
                </Popover>
              </div>
            )}

            {/* Space options — the last page-level section the Analyzer had, now the row's.
                `AnalyzerConfig.tissue_type` is "voxel space only" (`tit/analyzer/config.py`) and
                the runner overwrites it with GM in mesh (`analyzer.py`), so a mesh row states the
                value it will actually run with and says why it cannot be changed. */}
            <section className="analysis-settings-group" data-testid="analysis-space-options">
              <h4 className="text-eyebrow">Space options</h4>
              <Field
                label="Tissue"
                help="The compartment a voxel analysis measures in."
                /* A disabled control's reason is stated ON the form, not behind an (i) the user
                   would have to think to open (DESIGN.md §4.2 rule 8's shape). */
                note={
                  row.space === "mesh"
                    ? "Mesh analyses are gray matter — tissue applies to voxel space."
                    : undefined
                }
              >
                <Select
                  value={row.space === "voxel" ? row.tissue : "GM"}
                  onValueChange={(v) => onChange({ tissue: v as TissueKind })}
                  options={TISSUE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                  disabled={row.space === "mesh"}
                  aria-label="Tissue"
                />
              </Field>
            </section>
          </div>
  );
}
