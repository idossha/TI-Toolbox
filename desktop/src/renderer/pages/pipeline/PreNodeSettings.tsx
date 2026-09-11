import { useState } from "react";
import { PreprocessSteps } from "../preprocess/PreprocessSteps";
import { defaultConfig } from "../preprocess/config";
import { QsiPrepDialog } from "../preprocess/QsiPrepDialog";
import { QsiReconDialog } from "../preprocess/QsiReconDialog";
import { defaultQsiPrepConfig, defaultQsiReconConfig } from "../preprocess/qsi";
import type { PreprocessConfig } from "../preprocess/api";
import { PRE_STAGES, type PreEditor } from "./editors";

export function PreNodeSettings({editor,onChange}: {editor:PreEditor;onChange:(editor:PreEditor)=>void}) {
  const [prepOpen,setPrepOpen]=useState(false);
  const [reconOpen,setReconOpen]=useState(false);
  const values={...defaultConfig(),...editor.settings,...editor.stages};
  const patch=(changes:Partial<PreprocessConfig>)=>{
    const settings={...values,...changes};
    onChange({...editor,settings,stages:Object.fromEntries(PRE_STAGES.map(({key})=>[key,settings[key as keyof PreprocessConfig]===true]))});
  };
  return <>
    <PreprocessSteps values={values} onChange={patch} onQsiPrep={()=>setPrepOpen(true)} onQsiRecon={()=>setReconOpen(true)} />
    <QsiPrepDialog open={prepOpen} onOpenChange={setPrepOpen} initial={{...defaultQsiPrepConfig(),...values.qsiprep_config}} onSave={(qsiprep_config)=>patch({qsiprep_config})}/>
    <QsiReconDialog open={reconOpen} onOpenChange={setReconOpen} initial={{...defaultQsiReconConfig(),...values.qsi_recon_config}} onSave={(qsi_recon_config)=>patch({qsi_recon_config})}/>
  </>;
}
