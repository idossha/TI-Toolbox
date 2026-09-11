/* global window */
// Explicit real-machine acceptance run; requires a new subject and preserves all outputs.
import { _electron as electron } from '@playwright/test';
import { mkdir, copyFile, access, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import assert from 'node:assert/strict';
const project = process.env.TIT_NATIVE_TEST_PROJECT;
const container = process.env.TIT_NATIVE_TEST_CONTAINER;
const sid = process.env.TIT_NATIVE_TEST_SUBJECT;
const input = process.env.TIT_NATIVE_TEST_INPUT || join(project || '', 'sub-101/anat/sub-101_T1w.nii.gz');
if (!project || !container || !sid || !/^[a-zA-Z0-9]+$/.test(sid)) throw new Error('Set TIT_NATIVE_TEST_PROJECT, TIT_NATIVE_TEST_CONTAINER and a new TIT_NATIVE_TEST_SUBJECT.');
const subject = join(project, 'sub-' + sid);
try { await access(subject); throw new Error('Test subject already exists. Choose a new test subject.'); } catch (e) { if(e.code !== 'ENOENT') throw e; }
await mkdir(join(subject, 'anat'), {recursive: true});
await copyFile(input,join(subject,'anat',`sub-${sid}_T1w.nii.gz`));
const app = await electron.launch({args:['.'],env:{...process.env,TIT_E2E_OFFSCREEN:'1',TIT_LAUNCH_CONTAINER_ID:container,TIT_USER_DATA_DIR:process.env.TIT_NATIVE_TEST_USER_DATA || join(process.env.HOME,'Library/Application Support/ti-toolbox-desktop'),TIT_DEV_LAUNCHER:'0'}});
try {
 const page = await app.firstWindow();
 await page.waitForFunction(()=>!!window.tit?.fastsurfer, {timeout:30000});
 for(let i=0;i<30;i++){if((await page.evaluate(()=>window.tit.fastsurfer.status())).supported)break;await new Promise(r=>setTimeout(r,1000));}
 assert.equal((await page.evaluate(()=>window.tit.fastsurfer.status())).supported,true,'A verified local Docker project is required.');
 assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().some(w=>w.isVisible())),false);
 await app.evaluate(({dialog})=>{dialog.showMessageBox=async (_window,options)=>{globalThis.nativeConsent=options;return {response:1,checkboxChecked:false};};});
 const declined=await page.evaluate(()=>window.tit.fastsurfer.enable());
 assert.equal(declined.enabled,false);
 const prompt=await app.evaluate(()=>globalThis.nativeConsent);
 assert.ok(prompt.detail.includes('across your local projects')); 
 assert.ok(prompt.detail.includes('runtimes'));
 await app.evaluate(({dialog})=>{dialog.showMessageBox=async()=>({response:0,checkboxChecked:false});});
 const enabled=await page.evaluate(()=>window.tit.fastsurfer.enable());
 assert.equal(enabled.enabled,true,JSON.stringify(enabled));
 console.log('Consent declined/accepted; native worker enabled; hidden window confirmed.');
 const started=Date.now();
 const job=await page.evaluate(async (sid)=>{const r=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'pre',subject_ids:[sid],config:{subject_ids:[sid],run_fastsurfer:true,fastsurfer_threads:10}})});if(!r.ok)throw new Error(await r.text());return r.json();},sid);
 console.log('Job submitted:',job.id);
 await writeFile(join(subject,'native-test-consent.json'),JSON.stringify({declined:!declined.enabled,accepted:enabled.enabled,project,directory:enabled.directory},null,2));
 await writeFile(join(subject,'native-test-job.json'),JSON.stringify({id:job.id,started:new Date(started).toISOString()},null,2));
 let result;
 for(let i=0;i<240;i++){
  await new Promise(r=>setTimeout(r,10000));
  result=await page.evaluate(async id=>(await (await fetch('/api/jobs/'+id)).json()).status,job.id);
  if(i%6===0)console.log('Job',result.state,'elapsed',Math.round((Date.now()-started)/1000),'s');
  if(['succeeded','failed','cancelled'].includes(result.state))break;
 }
 console.log(JSON.stringify({state:result?.state,elapsedSeconds:(Date.now()-started)/1000}));
 assert.equal(result?.state,'succeeded',JSON.stringify(result));
 await access(join(project,'derivatives/fastsurfer','sub-'+sid,'mri/aparc.DKTatlas+aseg.deep.nii.gz'));
 await writeFile(join(subject,'native-test-result.json'),JSON.stringify({state:result.state,elapsedSeconds:(Date.now()-started)/1000},null,2));
} finally {
 const page = await app.firstWindow().catch(()=>null);
 await page?.evaluate(()=>window.tit?.fastsurfer?.disable()).catch(()=>{});
 await app.evaluate(()=>{process.exit(0);}).catch(()=>{});
}
