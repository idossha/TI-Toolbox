/**
 * Pipeline canvas (plan §1-D, D5) — draw a graph of the jobs you already know, run it as **one**
 * job group, export it as a notebook.
 *
 * Three columns: a palette of node kinds, the React Flow canvas, and a right pane carrying the
 * receipt (what Run will submit, from `POST /api/pipelines/validate`) over the live Terminal.
 *
 * What this page deliberately does *not* have: a scheduler. Run is one `POST /api/pipelines/run`;
 * the server turns the document into one labelled DAG and submits it with `submit_plan`, so the
 * whole canvas is one `group_id` in Jobs, cancellable as one thing. Nothing here sequences jobs.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  type Connection,
  type Edge as FlowEdge,
  type Node as FlowNode,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Download, Play, Plus, Save, Trash2, Upload } from "lucide-react";
import { PageLayout, usePaneController } from "../../ui/Layout";
import { ActionBar } from "../../ui/Chrome";
import { Button, IconButton } from "../../ui/Button";
import { Callout, EmptyState } from "../../ui/Feedback";
import { JobStateChip, type JobState } from "../../ui/Status";
import { notify } from "../../ui/Toast";
import { usePageSession } from "../../app/pageSession";
import { useJobsModel } from "../../app/jobs-rail/model";
import { JobConsole } from "../../ui/Jobs";
import { jobEventsToLogLines } from "../../app/jobs/logLines";
import { getJobEvents } from "../../app/jobs-rail/api";
import { NodeInspector, useAtlasLookup } from "./NodeInspector";
import { configFor, defaultEditor, parseSubjects, type NodeEditor } from "./editors";
import {
  KIND_TITLE,
  NODE_KINDS,
  PORTS,
  PORT_LABEL,
  canConnect,
  displayName,
  emptyPipeline,
  nextNodeId,
  nodeById,
  nodeSummary,
  type NodeKind,
  type PipelineDoc,
  type PortType,
} from "./graph";
import {
  exportNotebook,
  listPipelines,
  loadPipeline,
  runPipeline,
  savePipeline,
  validatePipeline,
  type PipelineValidation,
} from "./api";
import "./pipeline.css";

/** Vertical offset of one port handle on a card, so several ports of a kind do not overlap. */
const handleTop = (index: number, total: number) => `${((index + 1) / (total + 1)) * 100}%`;

interface CardData extends Record<string, unknown> {
  kind: NodeKind;
  title: string;
  summary: string;
  state: JobState | null;
  invalid: boolean;
}

function NodeCard({ data, id }: NodeProps) {
  const card = data as CardData;
  const ports = PORTS[card.kind];
  return (
    <div className={`pipeline-card${card.invalid ? " is-invalid" : ""}`} data-testid={`pipeline-node-${id}`}>
      {ports.inputs.map((port, i) => (
        <Handle
          key={`in-${port}`}
          type="target"
          id={port}
          position={Position.Left}
          style={{ top: handleTop(i, ports.inputs.length) }}
          className={`pipeline-handle port-${port}`}
          title={PORT_LABEL[port]}
          data-testid={`pipeline-in-${id}-${port}`}
        />
      ))}
      <header>
        <span className="pipeline-card-kind">{KIND_TITLE[card.kind]}</span>
        {card.state && <JobStateChip state={card.state} />}
      </header>
      <strong className="pipeline-card-title">{card.title}</strong>
      <span className="pipeline-card-summary">{card.summary || "not configured"}</span>
      {ports.outputs.map((port, i) => (
        <Handle
          key={`out-${port}`}
          type="source"
          id={port}
          position={Position.Right}
          style={{ top: handleTop(i, ports.outputs.length) }}
          className={`pipeline-handle port-${port}`}
          title={PORT_LABEL[port]}
          data-testid={`pipeline-out-${id}-${port}`}
        />
      ))}
    </div>
  );
}

const NODE_TYPES = { pipelineNode: NodeCard };

interface PipelineSession {
  doc: PipelineDoc;
  editors: Record<string, NodeEditor>;
  /** The group the canvas last submitted; the status chips and the Terminal follow it. */
  groupId: string | null;
  /**
   * job id -> node id for that group. `JobStatus` carries no tags on the wire, so the mapping is
   * built at submit time by zipping the receipt's labels (which *do* name their node) with the
   * jobs the run returned -- `submit_plan` creates them in plan order, one for one.
   */
  jobNodes: Record<string, string>;
  parallel: number;
}

const EMPTY_SESSION: PipelineSession = { doc: emptyPipeline(), editors: {}, groupId: null, jobNodes: {}, parallel: 1 };

function PipelineCanvas() {
  const [session, setSession] = usePageSession<PipelineSession>("canvas", EMPTY_SESSION);
  const { doc, editors, groupId } = session;
  const [selected, setSelected] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const pane = usePaneController({ pageId: "pipeline", name: "receipt" });
  const fileInput = useRef<HTMLInputElement>(null);

  const patch = useCallback(
    (next: Partial<PipelineSession>) => setSession((prev) => ({ ...prev, ...next })),
    [setSession],
  );

  // ---- validation is the receipt: the server is the authority on what Run will submit ---------
  const validation = useQuery<PipelineValidation>({
    queryKey: ["pipeline-validate", JSON.stringify(doc)],
    queryFn: () => validatePipeline(doc),
    enabled: doc.nodes.length > 0,
  });

  const saved = useQuery({ queryKey: ["pipelines"], queryFn: () => listPipelines() });

  // ---- live status per node, from the group this canvas last submitted ------------------------
  const jobs = useJobsModel();
  const groupJobs = useMemo(
    () => (groupId ? jobs.all.filter((j) => j.group_id === groupId) : []),
    [jobs.all, groupId],
  );
  const stateByNode = useMemo(() => {
    // Worst state wins, so a node whose one failed job is buried under nine successes still reads
    // "failed" on the card.
    const rank: JobState[] = ["failed", "running", "queued", "succeeded"];
    const out: Record<string, JobState> = {};
    for (const job of groupJobs) {
      const nodeId = session.jobNodes[job.id];
      if (!nodeId) continue;
      const state = job.state as JobState;
      const current = out[nodeId];
      if (!current || rank.indexOf(state) < rank.indexOf(current)) out[nodeId] = state;
    }
    return out;
  }, [groupJobs, session.jobNodes]);
  const followed = groupJobs.find((j) => j.state === "running") ?? groupJobs[0];
  const events = useQuery({
    queryKey: ["pipeline-log", followed?.id],
    queryFn: () => getJobEvents(followed!.id),
    enabled: !!followed,
    refetchInterval: followed && (followed.state === "running" || followed.state === "queued") ? 1000 : false,
  });

  // ---- editing -------------------------------------------------------------------------------
  const inspectedNode = inspecting ? nodeById(doc, inspecting) : undefined;
  const inspectedEditor = inspecting ? editors[inspecting] : undefined;
  const inspectedSubjects = inspectedEditor && "subjects" in inspectedEditor ? parseSubjects(inspectedEditor.subjects) : [];
  const atlasLookup = useAtlasLookup(
    inspectedSubjects[0],
    inspectedEditor && "roi" in inspectedEditor ? inspectedEditor.roi : undefined,
  );

  const addNode = (kind: NodeKind) => {
    const id = nextNodeId(doc, kind);
    const editor = defaultEditor(kind);
    patch({
      doc: {
        ...doc,
        nodes: [
          ...doc.nodes,
          { id, kind, config: configFor(editor, atlasLookup), position: { x: 40 + doc.nodes.length * 300, y: 40 + (doc.nodes.length % 2) * 140 } },
        ],
      },
      editors: { ...editors, [id]: editor },
    });
    setSelected(id);
  };

  const removeNode = (id: string) => {
    const rest = Object.fromEntries(Object.entries(editors).filter(([key]) => key !== id));
    patch({
      doc: { ...doc, nodes: doc.nodes.filter((n) => n.id !== id), edges: doc.edges.filter((e) => e.from !== id && e.to !== id) },
      editors: rest,
    });
    setSelected(null);
    setInspecting(null);
  };

  const updateEditor = (id: string, next: NodeEditor) => {
    patch({
      editors: { ...editors, [id]: next },
      doc: { ...doc, nodes: doc.nodes.map((n) => (n.id === id ? { ...n, config: configFor(next, atlasLookup) } : n)) },
    });
  };

  const onConnect = (connection: Connection) => {
    const port = (connection.sourceHandle ?? connection.targetHandle) as PortType | null;
    if (!connection.source || !connection.target || !port) return;
    if (connection.sourceHandle !== connection.targetHandle) {
      setRefusal(`${PORT_LABEL[connection.sourceHandle as PortType] ?? "that output"} cannot feed ${PORT_LABEL[connection.targetHandle as PortType] ?? "that input"}`);
      return;
    }
    const verdict = canConnect(doc, connection.source, connection.target, port);
    if (!verdict.ok) {
      setRefusal(verdict.reason);
      return;
    }
    setRefusal(null);
    patch({ doc: { ...doc, edges: [...doc.edges, { from: connection.source, to: connection.target, port }] } });
  };

  /**
   * React Flow is *controlled*, and controlling it means owning its node array — including the
   * `dimensions` changes it dispatches after it measures a card. Rebuilding the array from the
   * document on every render (or applying only the position changes) throws those measurements
   * away, and React Flow keeps an unmeasured node at `visibility: hidden` forever. So the flow
   * nodes live in their own state, every change is applied, and only a drag writes a position back
   * into the document.
   */
  const derived: FlowNode[] = useMemo(
    () =>
      doc.nodes.map((node) => ({
        id: node.id,
        type: "pipelineNode",
        position: node.position,
        selected: node.id === selected,
        data: {
          kind: node.kind,
          title: displayName(node),
          summary: nodeSummary(doc, node),
          state: stateByNode[node.id] ?? null,
          invalid: (validation.data?.issues ?? []).some((i) => i.level === "error" && i.node_id === node.id),
        } satisfies CardData,
      })),
    [doc, selected, stateByNode, validation.data],
  );

  const [flowNodes, setFlowNodes] = useState<FlowNode[]>(derived);
  const [lastDerived, setLastDerived] = useState<FlowNode[]>(derived);
  if (lastDerived !== derived) {
    // React's documented "adjusting state while rendering" (react.dev/learn/you-might-not-need-an-
    // effect): merge during render, not in an effect, so React Flow never sees a frame with stale
    // card data. Whatever React Flow attached to a node it already knows (its measurements, the
    // live position mid-drag) is kept; the data and selection come from the document.
    const byId = new Map(flowNodes.map((n) => [n.id, n]));
    setLastDerived(derived);
    setFlowNodes(
      derived.map((node) => {
        const existing = byId.get(node.id);
        return existing ? { ...existing, ...node, position: existing.position } : node;
      }),
    );
  }

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setFlowNodes((previous) => applyNodeChanges(changes, previous)),
    [],
  );

  const flowEdges: FlowEdge[] = useMemo(
    () =>
      doc.edges.map((edge) => ({
        id: `${edge.from}-${edge.to}-${edge.port}`,
        source: edge.from,
        target: edge.to,
        sourceHandle: edge.port,
        targetHandle: edge.port,
        label: PORT_LABEL[edge.port],
        className: `pipeline-edge port-${edge.port}`,
      })),
    [doc.edges],
  );

  // ---- run / save / export --------------------------------------------------------------------
  const run = useMutation({
    mutationFn: () => runPipeline(doc, session.parallel),
    onSuccess: (result) => {
      const labels = validation.data?.jobs ?? [];
      const jobNodes: Record<string, string> = {};
      if (labels.length === result.jobs.length) {
        result.jobs.forEach((job, i) => {
          const label = labels[i]?.label ?? "";
          const nodeId = label.split(":")[0];
          if (nodeId) jobNodes[job.id] = nodeId;
        });
      }
      patch({ groupId: result.group_id, jobNodes });
      notify.success(`Pipeline queued as one group (${result.jobs.length} jobs)`);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: unknown) => notify.error(`Could not run the pipeline: ${String((error as Error)?.message ?? error)}`),
  });

  const save = useMutation({
    mutationFn: async () => {
      const name = window.prompt("Save pipeline as", doc.name === "untitled" ? "" : doc.name)?.trim();
      if (!name) return null;
      await savePipeline(name, { ...doc, name });
      return name;
    },
    onSuccess: (name) => {
      if (!name) return;
      patch({ doc: { ...doc, name } });
      notify.success(`Saved “${name}”`);
      void queryClient.invalidateQueries({ queryKey: ["pipelines"] });
    },
    onError: (error: unknown) => notify.error(`Could not save: ${String((error as Error)?.message ?? error)}`),
  });

  const exportNb = useMutation({
    mutationFn: () => exportNotebook(doc),
    onSuccess: (text) => {
      const blob = new Blob([text], { type: "application/x-ipynb+json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${doc.name || "pipeline"}.ipynb`;
      anchor.click();
      URL.revokeObjectURL(url);
      notify.success("Notebook exported");
    },
    onError: (error: unknown) => notify.error(`Could not export: ${String((error as Error)?.message ?? error)}`),
  });

  async function openSaved(name: string) {
    const loaded = await loadPipeline(name);
    patch({ doc: loaded, editors: Object.fromEntries(loaded.nodes.map((n) => [n.id, defaultEditor(n.kind)])), groupId: null, jobNodes: {} });
    notify.info(`Loaded “${name}”. Node forms open at their defaults; the saved configs are what runs.`);
  }

  function importFile(file: File) {
    void file.text().then((text) => {
      try {
        const loaded = JSON.parse(text) as PipelineDoc;
        patch({ doc: loaded, editors: Object.fromEntries((loaded.nodes ?? []).map((n) => [n.id, defaultEditor(n.kind)])), groupId: null, jobNodes: {} });
      } catch (error) {
        notify.error(`Not a pipeline document: ${String((error as Error)?.message ?? error)}`);
      }
    });
  }

  const errors = (validation.data?.issues ?? []).filter((i) => i.level === "error");
  const warnings = (validation.data?.issues ?? []).filter((i) => i.level === "warning");
  const preview = validation.data?.jobs ?? [];
  const runnable = doc.nodes.length > 0 && validation.data?.ok === true && !run.isPending;

  useEffect(() => {
    if (!refusal) return;
    const timer = setTimeout(() => setRefusal(null), 5000);
    return () => clearTimeout(timer);
  }, [refusal]);

  const paneContent = (
    <div className="pipeline-pane">
      <section className="pipeline-receipt" data-testid="pipeline-receipt">
        <h2>This will run</h2>
        {doc.nodes.length === 0 ? (
          <p className="pipeline-muted">Nothing yet.</p>
        ) : errors.length > 0 ? (
          <Callout kind="danger">
            <ul>
              {errors.map((issue, i) => (
                <li key={i}>{issue.message}</li>
              ))}
            </ul>
          </Callout>
        ) : (
          <>
            <p>
              <strong>{preview.length}</strong> {preview.length === 1 ? "job" : "jobs"} in <strong>one</strong> group
              {" — "}
              {doc.nodes.length} {doc.nodes.length === 1 ? "step" : "steps"}.
            </p>
            <ol className="pipeline-receipt-rows">
              {preview.slice(0, 15).map((job) => (
                <li key={job.label}>
                  <code>{job.label}</code> <span className="pipeline-muted">{job.kind}</span>{" "}
                  {job.subject_ids.join(", ")}
                  {job.after.length > 0 && <span className="pipeline-muted"> after {job.after.join(", ")}</span>}
                </li>
              ))}
            </ol>
            {preview.length > 15 && <p className="pipeline-muted">… and {preview.length - 15} more</p>}
          </>
        )}
        {warnings.length > 0 && (
          <Callout kind="warning">
            <ul>
              {warnings.map((issue, i) => (
                <li key={i}>{issue.message}</li>
              ))}
            </ul>
          </Callout>
        )}
      </section>
      <section className="pipeline-terminal">
        <h2>Terminal{followed ? ` — ${followed.kind} ${followed.id.slice(0, 8)}` : ""}</h2>
        <JobConsole sourceKey={followed?.id ?? "none"} lines={jobEventsToLogLines(events.data ?? [])} />
      </section>
    </div>
  );

  const actionBar = (
      <ActionBar
        primary={
          <Button
            variant="primary"
            disabled={!runnable}
            title={doc.nodes.length === 0 ? "Add a step to the pipeline." : (errors[0]?.message ?? undefined)}
            onClick={() => run.mutate()}
            data-testid="pipeline-run"
          >
            <Play size={14} aria-hidden /> Run pipeline
          </Button>
        }
        secondary={
          <>
            <Button variant="ghost" onClick={() => save.mutate()} disabled={doc.nodes.length === 0}>
              <Save size={14} aria-hidden /> Save
            </Button>
            <Button variant="ghost" onClick={() => exportNb.mutate()} disabled={doc.nodes.length === 0} data-testid="pipeline-export">
              <Download size={14} aria-hidden /> Export notebook
            </Button>
            {selected && (
              <IconButton
                aria-label={`Delete ${selected}`}
                title={`Delete ${selected}`}
                icon={<Trash2 size={14} aria-hidden />}
                onClick={() => removeNode(selected)}
              />
            )}
          </>
        }
        digest={
          errors.length > 0
            ? errors[0]?.message
            : groupId
              ? `Group ${groupId.slice(0, 8)} — ${groupJobs.filter((j) => j.state === "succeeded").length}/${groupJobs.length} done`
              : undefined
        }
      />
  );

  return (
    <PageLayout
      variant="run"
      rightPaneKind="run"
      paneController={pane}
      rightPane={paneContent}
      actionBar={actionBar}
    >
      <div className="pipeline-main">
          <aside className="pipeline-palette" aria-label="Node palette">
            <h2>Add a step</h2>
            {NODE_KINDS.map((kind) => (
              <button key={kind} type="button" className="pipeline-palette-item" onClick={() => addNode(kind)} data-testid={`pipeline-add-${kind}`}>
                <Plus size={14} aria-hidden />
                {KIND_TITLE[kind]}
              </button>
            ))}
            <h2>Saved</h2>
            {(saved.data ?? []).length === 0 && <p className="pipeline-muted">Nothing saved yet.</p>}
            {(saved.data ?? []).map((entry) => (
              <button key={entry.name} type="button" className="pipeline-palette-item" onClick={() => void openSaved(entry.name)}>
                {entry.name}
              </button>
            ))}
            <button type="button" className="pipeline-palette-item" onClick={() => fileInput.current?.click()}>
              <Upload size={14} aria-hidden /> Import JSON…
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) importFile(file);
                e.target.value = "";
              }}
            />
          </aside>

          <div className="pipeline-canvas" data-testid="pipeline-canvas">
            {doc.nodes.length === 0 ? (
              <EmptyState message="Add steps from the palette, then drag from a step's right-hand port to the matching port on another to bind its output — subjects, montage names, a simulation. Run submits the whole graph as one job group." />
            ) : (
              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                nodeTypes={NODE_TYPES}
                onNodesChange={onNodesChange}
                onConnect={onConnect}
                onNodeClick={(_, node) => setSelected(node.id)}
                onNodeDragStop={(_, node) =>
                  patch({
                    doc: {
                      ...doc,
                      nodes: doc.nodes.map((n) =>
                        n.id === node.id ? { ...n, position: { x: node.position.x, y: node.position.y } } : n,
                      ),
                    },
                  })
                }
                onNodeDoubleClick={(_, node) => setInspecting(node.id)}
                onEdgesDelete={(deleted) =>
                  patch({
                    doc: {
                      ...doc,
                      edges: doc.edges.filter((e) => !deleted.some((d) => d.source === e.from && d.target === e.to && d.sourceHandle === e.port)),
                    },
                  })
                }
                fitView
                proOptions={{ hideAttribution: true }}
              >
                <Background />
                <Controls showInteractive={false} />
              </ReactFlow>
            )}
            {refusal && (
              <div className="pipeline-refusal" role="status" data-testid="pipeline-refusal">
                {refusal}
              </div>
            )}
          </div>
      </div>
      {inspectedNode && inspectedEditor && (
        <NodeInspector
          doc={doc}
          node={inspectedNode}
          editor={inspectedEditor}
          onEditorChange={(next) => updateEditor(inspectedNode.id, next)}
          onLabelChange={(label) =>
            patch({ doc: { ...doc, nodes: doc.nodes.map((n) => (n.id === inspectedNode.id ? { ...n, label } : n)) } })
          }
          onClose={() => setInspecting(null)}
        />
      )}
    </PageLayout>
  );
}

export function PipelinePage() {
  return (
    <ReactFlowProvider>
      <PipelineCanvas />
    </ReactFlowProvider>
  );
}
