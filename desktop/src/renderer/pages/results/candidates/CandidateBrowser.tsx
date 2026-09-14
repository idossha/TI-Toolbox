import { autoLabel, positionColor } from "../../simulator/freehandPlacement";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Button } from "../../../ui/Button";
import { DataTable, type DataTableColumn } from "../../../ui/DataTable";
import { Callout } from "../../../ui/Feedback";
import { Select } from "../../../ui/Select";
import { ElectrodePositionTable } from "../preview/views";
import { ScenePane, useSceneManifest } from "../../_shared/scene";
import { getCandidate, getCandidateHistory, getCandidates } from "./api";
import { finite, frontierIds, intensityColor, metricDefinition, METRIC_LABELS, tradeoffCandidates, type Candidate, type CandidateRun, type Metric } from "./model";
import "./candidates.css";

const format = (value: unknown) => finite(value) ? value.toPrecision(4) : "Unavailable";
const metricKeys = Object.keys(METRIC_LABELS) as Metric[];
export function CandidateBrowser(props: CandidateRun) {
  return <CandidateBrowserContent key={`${props.subject}:${props.kind}:${props.run}`} {...props} />;
}
function CandidateBrowserContent({ subject, kind, run }: CandidateRun) {
  const navigate = useNavigate();
  const manifest = useSceneManifest(subject);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState("roi_mean");
  const [descending, setDescending] = useState(true);
  const [picked, setPicked] = useState<string | null>(null);
  const tableElement = useRef<HTMLDivElement>(null);
  const currentSelection = useRef<string | undefined>(undefined);
  const [background, setBackground] = useState<Metric>("contrast");
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const [transferring, setTransferring] = useState(false);
  const source = { subject, kind, run };
  const query = useQuery({ queryKey: ["optimization-candidates", subject, kind, run, offset, sort, descending], queryFn: () => getCandidates(source, offset, sort, descending), placeholderData: keepPreviousData });
  const history = useQuery({ queryKey: ["optimization-candidate-history", subject, kind, run, sort, descending], queryFn: ({ signal }) => getCandidateHistory(source, sort, descending, signal) });
  const candidates = useMemo(() => query.data?.candidates ?? [], [query.data]);
  const selected = history.data?.candidates.find((candidate) => candidate.id === picked) ?? candidates.find((candidate) => candidate.id === picked) ?? candidates[0];
  function pickPoint(candidate: Candidate) {
    setPicked(candidate.id);
    const index = history.data?.candidates.findIndex((item) => item.id === candidate.id) ?? -1;
    if (index >= 0) setOffset(Math.floor(index / 50) * 50);
  }
  useLayoutEffect(() => {
    currentSelection.current = selected?.id;
    const table = tableElement.current;
    const row = table?.querySelector<HTMLElement>('button[aria-pressed="true"]')?.closest("tr");
    if (table && row) table.scrollTop = Math.max(0, row.offsetTop - table.clientHeight / 2);
  }, [selected?.id, candidates]);
  const termination = selected?.optimizer_termination?.[selected.optimizer_termination.accepted_stage];
  const points = useMemo(() => tradeoffCandidates(history.data?.candidates ?? candidates, selected?.comparison_key ?? null, background), [history.data, candidates, selected?.comparison_key, background]);
  const frontier = useMemo(() => frontierIds(points, background), [points, background]);
  const labels = useMemo(() => {
    const ratio = selected?.metric_labels.contrast ?? "";
    return { ...METRIC_LABELS, background_mean: /whole.GM/i.test(selected?.metric_labels.background_mean ?? "") ? "Whole-GM mean (includes ROI; V/m)" : METRIC_LABELS.background_mean, contrast: /p95|95th/i.test(ratio) ? "ROI mean / non-ROI p95 (historical)" : /whole.GM/i.test(ratio) ? "ROI / whole-GM mean" : /non_roi_mean|non-ROI mean|mean.*non.roi/i.test(ratio) ? "Focality (ROI / non-ROI mean)" : METRIC_LABELS.contrast };
  }, [selected?.metric_labels]);
  const markers = useMemo(() => selected?.positions?.map((world, index) => ({ id: `${selected.id}-${index}`, world, channel: Math.floor(index / 2), label: autoLabel(index), color: positionColor(index) })), [selected]);
  const columns = useMemo<DataTableColumn<Candidate>[]>(() => [
    { id: "candidate", header: "Candidate", cell: ({ row }) => <button type="button" className="candidate-pick" aria-pressed={row.original.id === selected?.id} onClick={() => setPicked(row.original.id)}>{row.original.id}</button> },
    { accessorKey: "objective", header: "Objective", numeric: true, enableSorting: false, cell: ({ row }) => <span title={`${row.original.objective_label}; ${row.original.objective_direction}`}>{format(row.original.objective)}</span> },
    ...metricKeys.map((metric) => ({ id: metric, header: () => <span title={metricDefinition(selected?.metric_labels[metric] ?? labels[metric])}>{labels[metric]}</span>, numeric: true, enableSorting: false, cell: ({ row }: { row: { original: Candidate } }) => <span title={metricDefinition(row.original.metric_labels[metric] ?? METRIC_LABELS[metric])}>{format(row.original.metrics[metric])}</span> })),
  ], [selected?.id, selected?.metric_labels, labels]);
  async function prepareSimulation() {
    if (!selected) return;
    setTransferring(true); setHandoffError(null);
    try {
      const detail = await getCandidate(source, selected.id);
      if (!mounted.current || currentSelection.current !== selected.id) return;
      if (detail.candidate.id !== selected.id) throw new Error("The returned candidate does not match the selection.");
      navigate("/simulator", { state: { optimizationCandidate: { ...source, id: selected.id, requestId: crypto.randomUUID(), config: detail.simulation_config } } });
    } catch (error) { setHandoffError(error instanceof Error ? error.message : String(error)); }
    finally { setTransferring(false); }
  }
  if (query.isPending) return <p role="status">Loading evaluated candidates…</p>;
  if (query.error) return <Callout kind="danger">Could not load candidates. <Button onClick={() => void query.refetch()}>Retry</Button></Callout>;
  if (!query.data?.total) return <div>{query.data?.legacy && <Callout kind="info">Historical Flex run: no replayable saved winner is available; no trial history was recorded.</Callout>}<p>No valid evaluated candidates were recorded for this run.</p></div>;
  const xValues = points.map((c) => c.metrics.roi_mean as number), yValues = points.map((c) => c.metrics[background] as number);
  const xmin = Math.min(...xValues), xmax = Math.max(...xValues), ymin = Math.min(...yValues), ymax = Math.max(...yValues);
  const x = (value: number) => 45 + ((value - xmin) / (xmax - xmin || 1)) * 390;
  const y = (value: number) => 155 - ((value - ymin) / (ymax - ymin || 1)) * 125;
  return <div className="candidate-browser" data-testid="candidate-browser">
    <p className="field-help">Optimization estimates. Select a candidate to inspect its subject-space montage, then prepare an editable simulation.</p>
    {query.data.legacy && <Callout kind="info">Historical Flex run: only the saved winner is available. No trial history was recorded.</Callout>}
    <div className="candidate-review-grid"><section className="candidate-list-panel" aria-label="Candidate table">
    <div className="candidate-toolbar">
      <Select aria-label="Sort candidates" value={sort} options={[{ value: "objective", label: "Objective" }, ...metricKeys.map((value) => ({ value, label: labels[value] }))]} onValueChange={(value) => { setSort(value); setOffset(0); setPicked(null); }} />
      <Button onClick={() => { setDescending(!descending); setOffset(0); setPicked(null); }}>{descending ? "Descending" : "Ascending"}</Button>
    </div>
    <div className="candidate-table" ref={tableElement}><DataTable data={candidates} columns={columns} getRowId={(c) => c.id} selected={selected ? { [selected.id]: true } : {}} onRowClick={(c) => setPicked(c.id)} /></div>
    <div className="candidate-toolbar">
      <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button>
      <span>{offset + 1}–{Math.min(offset + candidates.length, query.data.total)} of {query.data.total}</span>
      <Button disabled={offset + 50 >= query.data.total} onClick={() => setOffset(offset + 50)}>Next</Button>
    </div>
    </section><section className="candidate-plot-panel" aria-label="Candidate comparison">
    <label className="candidate-axis">Vertical axis
      <Select aria-label="Trade-off non-ROI metric" value={background} options={(["background_p95", "background_mean", "contrast"] as Metric[]).map((value) => ({ value, label: labels[value] }))} onValueChange={(value) => setBackground(value as Metric)} />
    </label>
    {selected?.metric_labels[background] && <details className="field-help"><summary>Metric definition</summary>{metricDefinition(selected.metric_labels[background])}</details>}
    {history.isPending && <p role="status">Loading recorded evaluations for the plot… Table remains available.</p>}
    {history.error && <Callout kind="warning">Could not load the full plot; showing this table page only. <Button onClick={() => void history.refetch()}>Retry plot</Button></Callout>}
    {history.data && <p className="field-help">{history.data.candidates.length} of {history.data.total} recorded candidates loaded{history.data.candidates.length < history.data.total ? " (incomplete history; at most 10,000 candidates in the current sort order are loaded)" : ""}. {points.length} have comparable measurements for these axes.</p>}
    {points.length ? <>
      <svg className="candidate-plot" viewBox="0 0 480 195" aria-label="Candidate trade-off plot">
        <path d="M45 20 V155 H450" fill="none" stroke="currentColor" />
        <text x="48" y="15">{labels[background]} {background === "contrast" ? "↑" : "(lower is better)"}</text>
        <text x="45" y="180">{labels.roi_mean} →</text>
        <text x="41" y="32" textAnchor="end">{format(ymax)}</text><text x="41" y="155" textAnchor="end">{format(ymin)}</text>
        <text x="45" y="168">{format(xmin)}</text><text x="390" y="168">{format(xmax)}</text>
        {[...points.filter((candidate) => candidate.id !== selected?.id), ...points.filter((candidate) => candidate.id === selected?.id)].map((candidate) => <circle key={candidate.id} cx={x(candidate.metrics.roi_mean as number)} cy={y(candidate.metrics[background] as number)} r={candidate.id === selected?.id ? 4 : 2.25} fill={intensityColor(candidate.metrics.roi_mean as number, xmin, xmax)} className="candidate-point" data-selected={candidate.id === selected?.id} aria-pressed={candidate.id === selected?.id} data-frontier={frontier.has(candidate.id)} tabIndex={0} role="button" aria-label={`Select candidate ${candidate.id}`} onClick={() => pickPoint(candidate)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pickPoint(candidate); } }}><title>{candidate.id}: {format(candidate.metrics.roi_mean)} ROI mean (V/m), {format(candidate.metrics[background])} {labels[background]}</title></circle>)}
      </svg>
      <div className="candidate-color-legend" aria-label="Point colour: ROI mean (V/m)">
        <span>Colour: ROI mean (V/m)</span>
        <span>Low {format(xmin)}</span>
        <span className="candidate-color-ramp" aria-hidden="true" style={{ background: `linear-gradient(to right, ${intensityColor(xmin, xmin, xmax)}, ${intensityColor(xmax, xmin, xmax)})` }} />
        <span>High {format(xmax)}</span>
      </div>
      <p className="field-help">Outlined points: frontier among the {points.length} displayed evaluated candidates with matching metric definitions. This is not a global optimum.</p>
    </> : <p className="field-help">Focality or non-ROI measurements were not recorded for this selection. No values are inferred; choose another available metric or inspect the montage directly.</p>}
    </section></div>
    {selected && <section className="candidate-selected-panel" aria-label="Selected montage">
      <strong>Selected: {selected.id}</strong>
      <span>{selected.objective_label}: {format(selected.objective)} · {selected.objective_direction}</span>
      {selected.currents_mA && <span>Channel currents: {selected.currents_mA.map((current, i) => `Ch${i + 1} ${format(current)} mA`).join(" · ")}</span>}
      {(selected.positions?.length ?? 0) || (selected.pairs?.length && selected.eeg_net) ? (!manifest.data || manifest.data.building || manifest.error) ? <p role="status">Subject montage preview unavailable{manifest.data?.building ? " while subject geometry is building" : " until subject geometry is available"}. Recorded electrode coordinates remain available below.</p> : <div className="candidate-scene"><ScenePane mode="montage" subject={subject} net={selected.eeg_net ?? null} pairs={selected.pairs} placedMarkers={markers?.length ? markers : undefined} note={`Candidate ${selected.id} · ${subject} · optimization estimate`} /></div> : <p>Montage geometry is unavailable for this candidate.</p>}
      {!!selected.positions?.length && <details><summary>Electrode coordinates (subject mm)</summary><ElectrodePositionTable electrodes={selected.positions!.map(([x, y, z], index) => ({ channel: Math.floor(index / 2), array: index % 2, x, y, z }))} /></details>}
      {termination && <p>{termination.success ? "Solver stopping criterion reached" : "Solver did not converge"}: {termination.message}. This describes solver termination, not proof of a global optimum.</p>}
      {selected.replay_note && <Callout kind="info">{selected.replay_note}</Callout>}
      <Button disabled={transferring} onClick={() => void prepareSimulation()}>{transferring ? "Preparing…" : "Use in Simulator"}</Button>
      <p className="field-help">Creates a draft; nothing runs until you press Run simulation.</p>
    </section>}
    {handoffError && <Callout kind="danger">{handoffError}</Callout>}
  </div>;
}
