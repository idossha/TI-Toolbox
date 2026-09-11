import { Link } from "react-router-dom";
import { FormSection } from "../../ui/Layout";
import { Checkbox } from "../../ui/Toggle";
import { Button } from "../../ui/Button";
import { StepHelpIcon } from "./stepInfo";
import { NativeFastSurfer } from "./NativeFastSurfer";
import type { PreprocessConfig } from "./api";
import "./preprocess.css";

export function PreprocessSteps({values, onChange, onQsiPrep, onQsiRecon}: {values: PreprocessConfig; onChange: (patch: Partial<PreprocessConfig>)=>void; onQsiPrep:()=>void; onQsiRecon:()=>void}) {
  const setValue = <K extends keyof PreprocessConfig>(key: K, value: PreprocessConfig[K]) => onChange({[key]:value});
  return <>
        <div data-tier="1">
          <FormSection
            title="Structural"
            helpSlot={<StepHelpIcon id="structural" />}
          >
            <div className="structural-columns">
              <div className="structural-column">
                <div className="run-checkbox-row preprocess-step-row"><Checkbox checked={values.convert_dicom} onCheckedChange={(v) => setValue("convert_dicom", v)} label="Convert DICOM to NIfTI" /><StepHelpIcon id="convert_dicom" /></div><div className="run-checkbox-row preprocess-step-row"><Checkbox checked={values.create_m2m} onCheckedChange={(v) => setValue("create_m2m", v)} label="SimNIBS charm (m2m + subject atlas)" /><StepHelpIcon id="create_m2m" /></div><div className="run-checkbox-row preprocess-step-row"><Checkbox checked={values.run_tissue_analysis} onCheckedChange={(v) => setValue("run_tissue_analysis", v)} label="Tissue analyzer" /><StepHelpIcon id="run_tissue_analysis" /></div>
              </div>
              <div className="structural-column">
                <div><div className="run-checkbox-row preprocess-step-row"><Checkbox checked={values.run_fastsurfer} onCheckedChange={(v) => setValue("run_fastsurfer", v)} label="FastSurfer segmentation" /><StepHelpIcon id="run_fastsurfer" /></div><div className="structural-child"><span aria-hidden="true">↳</span><NativeFastSurfer /></div></div>
                <div><div className="run-checkbox-row preprocess-step-row"><Checkbox checked={values.run_freesurfer} onCheckedChange={(v) => setValue("run_freesurfer", v)} label="FreeSurfer (optional)" /><StepHelpIcon id="run_freesurfer" /></div><div className="structural-child"><span aria-hidden="true">↳</span><Link to="/settings#preprocessing">Configure FreeSurfer</Link></div></div>
              </div>
            </div>
          </FormSection>
        </div>

        <div data-tier="1">
          <FormSection
            title="DWI (docker)"
            helpSlot={<StepHelpIcon id="dwi" />}
          >
            <div className="run-checkbox-row preprocess-step-row">
              <Checkbox checked={values.run_qsiprep} onCheckedChange={(v) => setValue("run_qsiprep", v)} label="QSIPrep" />
              <Button size="sm" variant="secondary" onClick={() => onQsiPrep()} data-testid="open-qsiprep-config">
                Configure…
              </Button>
              <StepHelpIcon id="run_qsiprep" />
            </div>
            <div className="run-checkbox-row preprocess-step-row">
              <Checkbox checked={values.run_qsirecon} onCheckedChange={(v) => setValue("run_qsirecon", v)} label="QSIRecon" />
              <Button size="sm" variant="secondary" onClick={() => onQsiRecon()} data-testid="open-qsirecon-config">
                Configure…
              </Button>
              <StepHelpIcon id="run_qsirecon" />
            </div>
            <div className="run-checkbox-row preprocess-step-row">
              <Checkbox
                checked={values.extract_dti}
                onCheckedChange={(v) => setValue("extract_dti", v)}
                label="Extract DTI tensor"
              />
              <StepHelpIcon id="extract_dti" />
            </div>
          </FormSection>
        </div>

  </>;
}
