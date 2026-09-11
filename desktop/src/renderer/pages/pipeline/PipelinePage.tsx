/**
 * Pipeline canvas (plan §1-D, D5) — draw a graph of the jobs you already know, run it as **one**
 * job group, export it as a notebook.
 *
 * Three columns: a searchable palette of node kinds, the React Flow canvas, and a right pane
 * carrying a compact receipt (from `POST /api/pipelines/validate`) over the live Terminal.
 *
 * What this page deliberately does *not* have: a scheduler. Run is one `POST /api/pipelines/run`;
 * the server turns the document into one labelled DAG and submits it with `submit_plan`, so the
 * whole canvas is one `group_id` in Jobs, cancellable as one thing. Nothing here sequences jobs.
 *
 * ## The document is the single source of truth
 *
 * React Flow is *controlled*. Every structural fact — which nodes exist, which wires exist, where
 * a card sits — lives in `session.doc` and nowhere else, and every mutation goes through `commit`,
 * which is also what makes undo possible. The two things React Flow is allowed to own are its own
 * measurements (see the merge-during-render below) and the *selection*, which is view state.
 *
 * The bug this shape fixes: the previous version wired `onEdgesDelete` but not `onNodesDelete`
 * and not `onEdgesChange`, so Delete on a node removed it from React Flow's array and the very
 * next render put it straight back from the document, and an edge could not be selected at all —
 * which made Delete on a wire a no-op. Both paths now end in `commit`.
 */
import { ExistingOutputsDialog } from "../_shared/run/ExistingOutputsDialog";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge as FlowEdge,
  type Node as FlowNode,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Download, Play, Redo2, Save, Sparkles, Trash2, Undo2 } from "lucide-react";
import { PageLayout, usePaneController } from "../../ui/Layout";
import { ActionBar } from "../../ui/Chrome";
import { Button, IconButton } from "../../ui/Button";
import { Dialog } from "../../ui/Overlay";
import { Field } from "../../ui/Field";
import { type JobState } from "../../ui/Status";
import { notify } from "../../ui/Toast";
import { usePageSession } from "../../app/pageSession";
import { useJobsModel } from "../../app/jobs-rail/model";
import { JobConsole } from "../../ui/Jobs";
import { jobEventsToLogLines } from "../../app/jobs/logLines";
import { getJobEvents } from "../../app/jobs-rail/api";
import { NodeInspector, useAtlasLookup } from "./NodeInspector";
import { NodeCard, type CardData } from "./NodeCard";
import { Palette, NODE_DRAG_TYPE } from "./Palette";
import { Receipt } from "./Receipt";
import { expandAnalysisTargets } from "./expandAnalysis";
import { analyzerNodeTargets, configFor, defaultEditor, editorFromNode, editorError, type NodeEditor } from "./editors";
import { useOverviewReadiness } from "./SubjectsEditor";
import {
  NODE_KINDS,
  PORT_LABEL,
  canConnect,
  displayName,
  emptyPipeline,
  nextNodeId,
  nodeById,
  nodeSummary,
  samplePipeline,
  subjectsOf,
  type NodeKind,
  type PipelineDoc,
  type PortType,
} from "./graph";
import {
  exportNotebookToProject,
  listPipelines,
  loadPipeline,
  runPipeline,
  planPipelineOutputs,
  savePipeline,
  validatePipeline,
  type PipelineValidation,
} from "./api";
import "./pipeline.css";

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

/** Did this event come from somewhere a keystroke means something else? */
function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return (
    el.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) ||
    el.closest?.("[role='dialog']") !== null
  );
}

function PipelineCanvas() {
  const [session, setSession] = usePageSession<PipelineSession>("canvas", EMPTY_SESSION);
  const { doc, editors, groupId } = session;
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [inspectField, setInspectField] = useState<PortType | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; nodeId?: string; edgeId?: string } | null>(null);
  const [saveAs, setSaveAs] = useState<string | null>(null);
  const [dropping, setDropping] = useState(false);
  /** A step added this render, to be selected as soon as React Flow knows about it. */
  const [justAdded, setJustAdded] = useState<string | null>(null);
  /** Undo history. Deliberately *not* in the page session: a history is per-visit, not per-page. */
  const [past, setPast] = useState<PipelineDoc[]>([]);
  const [future, setFuture] = useState<PipelineDoc[]>([]);
  const queryClient = useQueryClient();
  /**
   * The receipt is a *receipt*, and this page's work pane is a canvas.
   *
   * The run shape's default pane is `clamp(320px, 45vw, calc(100% - 566px))` — 610 px at 1440,
   * measured — which is right for the Simulator, whose pane carries the plan grid and a terminal
   * beside a column of controls. On this page it left a 560 px work pane, a 200 px palette and a
   * **348 px canvas**: too narrow to hold two node cards side by side, which is why the
   * maintainer's screenshot showed one enormous card on an otherwise empty grid. So the floor is
   * lowered to 320 and the pane is seeded once at 400 — the width `--right-pane-w-lg` gives every
   * other pane at this breakpoint. It is a *default*, not a lock: the drag handle, ⌘⇧I and the
   * expand control all still work, and once the user sets a width theirs is what persists.
   */
  const pane = usePaneController({ pageId: "pipeline", name: "receipt", minWidth: 320 });
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || pane.width !== null) return;
    seeded.current = true;
    pane.dispatch({ type: "resize", width: 400 });
  }, [pane]);
  const fileInput = useRef<HTMLInputElement>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const flow = useReactFlow();

  const patch = useCallback(
    (next: Partial<PipelineSession>) => setSession((prev) => ({ ...prev, ...next })),
    [setSession],
  );

  /** Every structural change to the graph, and the only thing undo has to know about. */
  const commit = useCallback(
    (next: PipelineDoc, alsoEditors?: Record<string, NodeEditor>) => {
      setPast((p) => [...p.slice(-49), doc]);
      setFuture([]);
      patch(alsoEditors ? { doc: next, editors: alsoEditors } : { doc: next });
    },
    [doc, patch],
  );

  /** Replace the whole canvas (load, import, sample). Undoable like anything else. */
  const replaceDoc = useCallback(
    (next: PipelineDoc) => {
      setPast((p) => [...p.slice(-49), doc]);
      setFuture([]);
      patch({
        doc: next,
        editors: Object.fromEntries((next.nodes ?? []).map((n) => [n.id, editorFromNode(n)])),
        groupId: null,
        jobNodes: {},
      });
    },
    [doc, patch],
  );

  // Read from state and write plainly — never from inside another setter's updater. An updater
  // function must be pure: React may call it more than once, and calling `patch`/`setFuture` from
  // inside `setPast` is an update to a different component mid-render, which React is free to
  // drop. It did: ⌘Z left the graph exactly as it was.
  const undo = useCallback(() => {
    if (!past.length) return;
    setPast(past.slice(0, -1));
    setFuture([doc, ...future]);
    const next = past[past.length - 1]!;
    patch({ doc: next, editors: Object.fromEntries(next.nodes.map((n) => [n.id, editorFromNode(n)])) });
  }, [past, future, doc, patch]);

  const redo = useCallback(() => {
    if (!future.length) return;
    setFuture(future.slice(1));
    setPast([...past, doc]);
    const next = future[0]!;
    patch({ doc: next, editors: Object.fromEntries(next.nodes.map((n) => [n.id, editorFromNode(n)])) });
  }, [past, future, doc, patch]);

  // ---- validation is the receipt: the server is the authority on what Run will submit ---------
  const validation = useQuery<PipelineValidation>({
    queryKey: ["pipeline-validate", JSON.stringify(doc)],
    queryFn: () => validatePipeline(doc),
    enabled: doc.nodes.length > 0,
  });
  const draftIssues = useMemo<PipelineValidation["issues"]>(() => doc.nodes.flatMap((node) => { const error = editors[node.id] && editorError(editors[node.id]!); return error ? [{ node_id: node.id, level: "error" as const, message: error }] : []; }), [doc.nodes, editors]);
  const issues = useMemo(() => [...(validation.data?.issues ?? []), ...draftIssues], [validation.data, draftIssues]);

  const saved = useQuery({ queryKey: ["pipelines"], queryFn: () => listPipelines() });

  /**
   * What every subject in this project already has. The drag gate needs it *locally*: a refusal
   * has to land while the wire is still following the pointer, which is before there is a graph
   * to ask the server about. `POST /api/pipelines/validate` applies the same table server-side, so
   * the sentence a user sees mid-drag is the sentence the receipt shows once the wire is there.
   */
  const { readiness } = useOverviewReadiness();

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

  // The Terminal pins to the node the user is looking at when that node has a job, and otherwise
  // to whatever is running -- so double-clicking a card and watching its log is one gesture.
  const [pinned, setPinned] = useState<string | null>(null);
  const followed = useMemo(() => {
    const forNode = (id: string | null | undefined) =>
      id ? groupJobs.find((j) => session.jobNodes[j.id] === id) : undefined;
    return forNode(pinned) ?? groupJobs.find((j) => j.state === "running") ?? groupJobs[0];
  }, [groupJobs, session.jobNodes, pinned]);

  const events = useQuery({
    queryKey: ["pipeline-log", followed?.id],
    queryFn: () => getJobEvents(followed!.id),
    enabled: !!followed,
    refetchInterval: followed && (followed.state === "running" || followed.state === "queued") ? 1000 : false,
  });

  // ---- editing -------------------------------------------------------------------------------
  const inspectedNode = inspecting ? nodeById(doc, inspecting) : undefined;
  const inspectedEditor = inspecting ? editors[inspecting] : undefined;
  // Which subjects reach the node being edited — from the graph, not from the node.
  const inspectedSubjects = inspecting ? subjectsOf(doc, inspecting) : [];
  const targetAtlasLookup = useAtlasLookup(
    inspectedSubjects[0],
    inspectedEditor && "roi" in inspectedEditor ? inspectedEditor.roi : undefined,
  );

  const nonRoiAtlasLookup = useAtlasLookup(inspectedSubjects[0], inspectedEditor?.kind === "flex" ? inspectedEditor.nonRoi : undefined);
  const atlasLookup = useCallback((atlas: string) => targetAtlasLookup(atlas) ?? nonRoiAtlasLookup(atlas), [targetAtlasLookup, nonRoiAtlasLookup]);

  /** Add a step. `at` is a flow-space position (a drop); without one it lands in view centre. */
  const addNode = useCallback(
    (kind: NodeKind, at?: { x: number; y: number }) => {
      const id = nextNodeId(doc, kind);
      const editor = defaultEditor(kind);
      const position =
        at ??
        (() => {
          // The middle of what the user is actually looking at, offset so a second click does not
          // stack one card exactly on top of another.
          const box = wrapper.current?.getBoundingClientRect();
          const centre = box
            ? flow.screenToFlowPosition({ x: box.x + box.width / 2, y: box.y + box.height / 2 })
            : { x: 0, y: 0 };
          const step = doc.nodes.length % 6;
          return { x: centre.x - 104 + step * 24, y: centre.y - 40 + step * 24 };
        })();
      commit(
        { ...doc, nodes: [...doc.nodes, { id, kind, config: configFor(editor, atlasLookup, undefined, []), position }] },
        { ...editors, [id]: editor },
      );
      // Selected by the effect below, once the node the document just gained is in `flowNodes`.
      // Not a `setTimeout`: a timer here raced the keyboard, and ⌘A pressed straight after adding
      // a step was undone a tick later by the timer re-selecting only the new node (measured: 1
      // node selected out of 2).
      setJustAdded(id);
    },
    [doc, editors, commit, atlasLookup, flow],
  );

  const removeNodes = useCallback(
    (ids: string[]) => {
      if (!ids.length) return;
      const gone = new Set(ids);
      commit(
        {
          ...doc,
          nodes: doc.nodes.filter((n) => !gone.has(n.id)),
          edges: doc.edges.filter((e) => !gone.has(e.from) && !gone.has(e.to)),
        },
        Object.fromEntries(Object.entries(editors).filter(([key]) => !gone.has(key))),
      );
      if (inspecting && gone.has(inspecting)) setInspecting(null);
    },
    [doc, editors, commit, inspecting],
  );

  const edgeId = (e: { from: string; to: string; port: string }) => `${e.from}-${e.to}-${e.port}`;

  const removeEdges = useCallback(
    (ids: string[]) => {
      if (!ids.length) return;
      const gone = new Set(ids);
      commit({ ...doc, edges: doc.edges.filter((e) => !gone.has(edgeId(e))) });
    },
    [doc, commit],
  );

  const updateEditor = (id: string, next: NodeEditor) => {
    patch({
      editors: { ...editors, [id]: next },
      doc: {
        ...doc,
        nodes: doc.nodes.map((n) =>
          n.id === id ? { ...n, config: configFor(next, atlasLookup, n.config, subjectsOf(doc, id), editors[id] ?? editorFromNode(n)) } : n,
        ),
      },
    });
  };

  // ---- wiring ---------------------------------------------------------------------------------
  //
  // Two layers, deliberately: `isValidConnection` runs *while the wire is being dragged*, so an
  // illegal target simply will not accept the drop; `onConnect` runs on the drop that survived it
  // and states the reason for anything left. A refusal is never silent.
  const refuse = useCallback((reason: string) => {
    setRefusal(reason);
    notify.info(reason);
  }, []);

  const verdictFor = useCallback(
    (c: Connection | FlowEdge): { ok: true } | { ok: false; reason: string } => {
      if (!c.source || !c.target) return { ok: false, reason: "a wire needs both ends" };
      if (c.sourceHandle !== c.targetHandle) {
        const from = PORT_LABEL[c.sourceHandle as PortType] ?? "that output";
        const to = PORT_LABEL[c.targetHandle as PortType] ?? "that input";
        return { ok: false, reason: `${from} cannot feed ${to}` };
      }
      return canConnect(doc, c.source, c.target, c.sourceHandle as PortType, readiness);
    },
    [doc, readiness],
  );

  /**
   * The reason the *last* handle the pointer was over refused the wire, and whether the drag
   * ended in an actual connection.
   *
   * `isValidConnection` is what makes an illegal target simply not accept the drop — good, and
   * the reason it is not enough on its own: a refused drop never reaches `onConnect`, so without
   * this the wire would spring back with no explanation, which is exactly the "silently dropped"
   * behaviour §9.1 forbids. So the verdict computed during the drag is kept, and `onConnectEnd`
   * states it if the drag produced nothing.
   */
  const pendingRefusal = useRef<string | null>(null);
  const connected = useRef(false);

  const onConnect = (connection: Connection) => {
    const verdict = verdictFor(connection);
    if (!verdict.ok) {
      refuse(verdict.reason);
      return;
    }
    connected.current = true;
    pendingRefusal.current = null;
    setRefusal(null);
    commit({
      ...doc,
      edges: [...doc.edges, { from: connection.source!, to: connection.target!, port: connection.sourceHandle as PortType }],
    });
  };

  /**
   * React Flow is *controlled*, and controlling it means owning its node array — including the
   * `dimensions` changes it dispatches after it measures a card. Rebuilding the array from the
   * document on every render (or applying only the position changes) throws those measurements
   * away, and React Flow keeps an unmeasured node at `visibility: hidden` forever. So the flow
   * nodes live in their own state, every change is applied, and only a drag writes a position
   * back into the document.
   */
  const needsByNode = useMemo(() => {
    const out: Record<string, PortType[]> = {};
    for (const issue of issues) {
      if (issue.code !== "missing_input" || !issue.node_id || !issue.port) continue;
      (out[issue.node_id] ??= []).push(issue.port as PortType);
    }
    return out;
  }, [issues]);

  const openNodeAt = useCallback((nodeId: string, port: PortType | null) => {
    setInspectField(port);
    setInspecting(nodeId);
  }, []);

  const derived: FlowNode[] = useMemo(
    () =>
      doc.nodes.map((node) => ({
        id: node.id,
        type: "pipelineNode",
        position: node.position,
        data: {
          kind: node.kind,
          title: displayName(node),
          summary: nodeSummary(doc, node),
          state: stateByNode[node.id] ?? null,
          invalid: issues.some((i) => i.level === "error" && i.node_id === node.id),
          needs: needsByNode[node.id] ?? [],
          onNeedClick: openNodeAt,
        } satisfies CardData,
      })),
    [doc, stateByNode, issues, needsByNode, openNodeAt],
  );

  const [flowNodes, setFlowNodes] = useState<FlowNode[]>(derived);
  const [lastDerived, setLastDerived] = useState<FlowNode[]>(derived);
  if (lastDerived !== derived) {
    // React's documented "adjusting state while rendering" (react.dev/learn/you-might-not-need-an-
    // effect): merge during render, not in an effect, so React Flow never sees a frame with stale
    // card data. Whatever React Flow attached to a node it already knows (its measurements, its
    // selection, the live position mid-drag) is kept; the data comes from the document. A node
    // the document no longer has disappears, which is what makes Delete work.
    const byId = new Map(flowNodes.map((n) => [n.id, n]));
    const wasDerived = new Map(lastDerived.map((n) => [n.id, n.position]));
    setLastDerived(derived);
    // A step just added is the selected one — decided *here*, in the same pass that first puts it
    // into React Flow's array, rather than in a timer afterwards. The timer raced the keyboard:
    // ⌘A pressed right after adding a step was undone a tick later by the timer re-selecting only
    // the new node (measured: 1 of 2 selected).
    const select = justAdded;
    if (select) setJustAdded(null);
    setFlowNodes(
      derived.map((node) => {
        const existing = byId.get(node.id);
        if (!existing) return select ? { ...node, selected: node.id === select } : node;
        if (select) return { ...existing, ...node, position: node.position, selected: node.id === select };
        // Position is the one field where "keep what React Flow has" is not always right. Mid-drag
        // React Flow's copy is the live one and the document's is stale, so the default is to keep
        // it. But when the *document's* position changes on its own — undo, redo, a loaded
        // pipeline, the sample — the document is the one that moved, and keeping React Flow's copy
        // would let a card sit where a drag left it while the document says otherwise. (Measured:
        // ⌘Z after dragging a card put the document back and left the card 152 px away from it.)
        const before = wasDerived.get(node.id);
        const moved = !before || before.x !== node.position.x || before.y !== node.position.y;
        return { ...existing, ...node, position: moved ? node.position : existing.position };
      }),
    );
  }

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setFlowNodes((previous) => applyNodeChanges(changes, previous)),
    [],
  );

  /** Edges are derived from the document; only their *selection* is React Flow's to own. */
  const [selectedEdges, setSelectedEdges] = useState<string[]>([]);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    for (const change of changes) {
      if (change.type === "select") {
        setSelectedEdges((ids) => (change.selected ? [...new Set([...ids, change.id])] : ids.filter((i) => i !== change.id)));
      }
    }
  }, []);

  const flowEdges: FlowEdge[] = useMemo(
    () =>
      doc.edges.map((edge) => {
        const id = edgeId(edge);
        const flowing = stateByNode[edge.from] === "running" || stateByNode[edge.to] === "running";
        return {
          id,
          source: edge.from,
          target: edge.to,
          sourceHandle: edge.port,
          targetHandle: edge.port,
          selected: selectedEdges.includes(id),
          className: `pipeline-edge port-${edge.port}${flowing ? " is-flowing" : ""}`,
        };
      }),
    [doc.edges, selectedEdges, stateByNode],
  );

  // ---- run / save / export --------------------------------------------------------------------
  const [outputDecision, setOutputDecision] = useState<{ existing: number; total: number; complete: boolean } | null>(null);
  const [checkingOutputs, setCheckingOutputs] = useState(false);
  async function checkOutputs() {
    setCheckingOutputs(true);
    try {
      const outputs = await planPipelineOutputs(doc);
      if (outputs.existing > 0) setOutputDecision(outputs);
      else run.mutate(false);
    } catch {
      notify.error("Could not check pipeline outputs. Try again before running.");
    } finally { setCheckingOutputs(false); }
  }
  const run = useMutation({
    mutationFn: (overwrite: boolean) => runPipeline(doc, session.parallel, { overwrite }),
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
    mutationFn: async (name: string) => {
      await savePipeline(name, { ...doc, name });
      return name;
    },
    onSuccess: (name) => {
      patch({ doc: { ...doc, name } });
      setSaveAs(null);
      notify.success(`Saved “${name}”`);
      void queryClient.invalidateQueries({ queryKey: ["pipelines"] });
    },
    onError: (error: unknown) => notify.error(`Could not save: ${String((error as Error)?.message ?? error)}`),
  });

  const exportNb = useMutation({
    mutationFn: () => exportNotebookToProject(doc),
    onSuccess: async (name) => {
      await queryClient.invalidateQueries({ queryKey: ["notebooks"] });
      notify.success(`Notebook saved to project Notebooks: ${name}`);
    },
    onError: (error: unknown) => notify.error(`Could not export: ${String((error as Error)?.message ?? error)}`),
  });

  async function openSaved(name: string) {
    try {
      replaceDoc(await loadPipeline(name));
      notify.info(`Loaded “${name}”.`);
    } catch (error) {
      notify.error(`Could not load “${name}”: ${String((error as Error)?.message ?? error)}`);
    }
  }

  function importFile(file: File) {
    void file.text().then((text) => {
      try {
        const loaded = JSON.parse(text) as PipelineDoc;
        if (!loaded || typeof loaded !== "object" || !Array.isArray(loaded.nodes)) {
          throw new Error("a pipeline document needs a `nodes` array");
        }
        replaceDoc({ version: 1, name: loaded.name || file.name.replace(/\.json$/i, ""), nodes: loaded.nodes, edges: loaded.edges ?? [] });
        notify.success(`Imported ${loaded.nodes.length} ${loaded.nodes.length === 1 ? "step" : "steps"}`);
      } catch (error) {
        notify.error(`Not a pipeline document: ${String((error as Error)?.message ?? error)}`);
      }
    });
  }

  /** Select a node, bring it into view and pin the Terminal to it. The receipt's "Fix" link. */
  const focusNode = useCallback(
    (nodeId: string) => {
      setFlowNodes((ns) => ns.map((n) => ({ ...n, selected: n.id === nodeId })));
      setPinned(nodeId);
      const node = nodeById(doc, nodeId);
      if (node) void flow.setCenter(node.position.x + 104, node.position.y + 40, { zoom: flow.getZoom(), duration: 200 });
    },
    [flow, doc],
  );

  const errors = issues.filter((i) => i.level === "error");
  const runnable = doc.nodes.length > 0 && validation.data?.ok === true && draftIssues.length === 0 && !run.isPending && !checkingOutputs;
  // Whichever subject this project has already run something for, else the documentation's own.
  const sampleSubject = jobs.all.find((j) => j.subject_ids?.length)?.subject_ids?.[0] ?? "ernie";

  // ---- keyboard --------------------------------------------------------------------------------
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || inspecting || saveAs !== null) return;
      const meta = event.metaKey || event.ctrlKey;
      if (meta && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
        return;
      }
      if (meta && event.key.toLowerCase() === "a") {
        event.preventDefault();
        setFlowNodes((ns) => ns.map((n) => ({ ...n, selected: true })));
        setSelectedEdges(doc.edges.map(edgeId));
        return;
      }
      if (event.key === "Escape") {
        setFlowNodes((ns) => ns.map((n) => ({ ...n, selected: false })));
        setSelectedEdges([]);
        setMenu(null);
        setRefusal(null);
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        // React Flow's own delete key handles the nodes; the edges are ours, because their
        // selection is ours.
        if (selectedEdges.length) {
          event.preventDefault();
          removeEdges(selectedEdges);
          setSelectedEdges([]);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, flow, doc.edges, selectedEdges, removeEdges, inspecting, saveAs]);

  useEffect(() => {
    if (!refusal) return;
    const timer = setTimeout(() => setRefusal(null), 5000);
    return () => clearTimeout(timer);
  }, [refusal]);

  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menu]);

  // ---- panes ------------------------------------------------------------------------------------
  const paneContent = (
    <div className="pipeline-pane">
      <section className="pipeline-receipt-section">
        <h2>
          <span>This will run</span>
          {validation.isFetching && <span>checking…</span>}
        </h2>
        <div className="pipeline-receipt">
          <Receipt
            doc={doc}
            issues={issues}
            jobs={validation.data?.jobs ?? []}
            loading={validation.isPending && doc.nodes.length > 0}
            onFocusNode={focusNode}
          />
        </div>
      </section>
      <section className="pipeline-terminal">
        <h2>
          <span>Terminal</span>
          {followed && (
            <span>
              {followed.kind} {followed.id.slice(0, 8)}
            </span>
          )}
        </h2>
        <JobConsole sourceKey={followed?.id ?? "none"} lines={jobEventsToLogLines(events.data ?? [])} />
      </section>
    </div>
  );

  const actionBar = (
    <ActionBar
      blocked={!runnable}
      primary={
        <Button
          variant="primary"
          disabled={!runnable}
          title={
            doc.nodes.length === 0
              ? "Add a step to the pipeline."
              : errors.length
                ? `${errors.length} problem${errors.length === 1 ? "" : "s"} to fix — see the receipt.`
                : undefined
          }
          onClick={() => void checkOutputs()}
          data-testid="pipeline-run"
        >
          <Play size={14} aria-hidden /> Run pipeline
        </Button>
      }
      secondary={
        <>
          <Button variant="ghost" onClick={() => setSaveAs(doc.name === "untitled" ? "" : doc.name)} disabled={doc.nodes.length === 0 || draftIssues.length > 0} data-testid="pipeline-save">
            <Save size={14} aria-hidden /> Save
          </Button>
          <Button variant="ghost" onClick={() => exportNb.mutate()} disabled={doc.nodes.length === 0 || draftIssues.length > 0 || exportNb.isPending} data-testid="pipeline-export">
            <Download size={14} aria-hidden /> Export notebook
          </Button>
          <IconButton
            aria-label="Undo"
            title="Undo (⌘Z)"
            data-testid="pipeline-undo"
            disabled={past.length === 0}
            icon={<Undo2 size={14} aria-hidden />}
            onClick={undo}
          />
          <IconButton
            aria-label="Redo"
            title="Redo (⇧⌘Z)"
            data-testid="pipeline-redo"
            disabled={future.length === 0}
            icon={<Redo2 size={14} aria-hidden />}
            onClick={redo}
          />
          <IconButton
            aria-label="Delete selected steps"
            title="Delete the selected steps and wires"
            data-testid="pipeline-delete"
            disabled={!flowNodes.some((n) => n.selected) && selectedEdges.length === 0}
            icon={<Trash2 size={14} aria-hidden />}
            onClick={() => {
              removeNodes(flowNodes.filter((n) => n.selected).map((n) => n.id));
              removeEdges(selectedEdges);
              setSelectedEdges([]);
            }}
          />
        </>
      }
      digest={
        groupId
          ? `Group ${groupId.slice(0, 8)} — ${groupJobs.filter((j) => j.state === "succeeded").length}/${groupJobs.length} done`
          : `${validation.data?.jobs?.length ?? 0} jobs · one group · ${doc.nodes.length} ${doc.nodes.length === 1 ? "step" : "steps"}`
      }
    />
  );

  return (
    <PageLayout variant="run" rightPaneKind="run" paneController={pane} rightPane={paneContent} actionBar={actionBar}>
      <div className="pipeline-main">
        <Palette
          saved={saved.data ?? []}
          onAdd={(kind) => addNode(kind)}
          onOpen={(name) => void openSaved(name)}
          onImport={() => fileInput.current?.click()}
        />
        <input
          ref={fileInput}
          type="file"
          accept="application/json,.json"
          hidden
          data-testid="pipeline-import-input"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) importFile(file);
            e.target.value = "";
          }}
        />

        <div
          ref={wrapper}
          className={`pipeline-canvas${dropping ? " is-dropping" : ""}`}
          data-testid="pipeline-canvas"
          onDragOver={(e) => {
            if (!e.dataTransfer.types.includes(NODE_DRAG_TYPE) && !e.dataTransfer.types.includes("text/plain")) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
            setDropping(true);
          }}
          onDragLeave={(e) => {
            if (e.currentTarget.contains(e.relatedTarget as Node)) return;
            setDropping(false);
          }}
          onDrop={(e) => {
            setDropping(false);
            const kind = (e.dataTransfer.getData(NODE_DRAG_TYPE) || e.dataTransfer.getData("text/plain")) as NodeKind;
            if (!NODE_KINDS.includes(kind)) return;
            e.preventDefault();
            const at = flow.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            addNode(kind, { x: at.x - 104, y: at.y - 40 });
          }}
        >
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={NODE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={(c) => {
              const verdict = verdictFor(c);
              pendingRefusal.current = verdict.ok ? null : verdict.reason;
              return verdict.ok;
            }}
            onConnectStart={() => {
              connected.current = false;
              pendingRefusal.current = null;
            }}
            onConnectEnd={() => {
              if (!connected.current && pendingRefusal.current) refuse(pendingRefusal.current);
              pendingRefusal.current = null;
            }}
            onNodesDelete={(deleted) => removeNodes(deleted.map((n) => n.id))}
            onEdgesDelete={(deleted) => removeEdges(deleted.map((e) => e.id))}
            onNodeClick={(_, node) => setPinned(node.id)}
            onNodeDragStop={(_, node) =>
              commit({
                ...doc,
                nodes: doc.nodes.map((n) =>
                  n.id === node.id ? { ...n, position: { x: node.position.x, y: node.position.y } } : n,
                ),
              })
            }
            onNodeDoubleClick={(_, node) => openNodeAt(node.id, null)}
            onNodeContextMenu={(e, node) => {
              e.preventDefault();
              const box = wrapper.current!.getBoundingClientRect();
              setMenu({ x: e.clientX - box.x, y: e.clientY - box.y, nodeId: node.id });
            }}
            onEdgeContextMenu={(e, edge) => {
              e.preventDefault();
              const box = wrapper.current!.getBoundingClientRect();
              setMenu({ x: e.clientX - box.x, y: e.clientY - box.y, edgeId: edge.id });
            }}
            onPaneClick={() => {
              setMenu(null);
              setSelectedEdges([]);
            }}
            snapToGrid
            snapGrid={[16, 16]}
            fitView
            // Never *magnify* (a lone card scaled 2x is what made the first screenshot's node look
            // enormous) and never shrink past readability either — below ~0.75 the 13 px card type
            // stops being type. Past that the answer is panning, not a smaller card.
            fitViewOptions={{ padding: 0.15, minZoom: 0.75, maxZoom: 1 }}
            minZoom={0.2}
            maxZoom={2}
            deleteKeyCode={["Delete", "Backspace"]}
            multiSelectionKeyCode={["Meta", "Shift", "Control"]}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls showInteractive={false} position="bottom-left" />
            {/* Sized by the inline `style`, which is the only size the minimap reads
                (`elementWidth = style?.width ?? 200`). A CSS-only size shrinks the box and leaves
                its contents laid out for the stock 200x150, spilling over the edge. */}
            <MiniMap
              pannable
              zoomable
              position="bottom-right"
              style={{ width: 132, height: 88 }}
              nodeStrokeWidth={2}
            />
          </ReactFlow>

          {doc.nodes.length === 0 && (
            <div className="pipeline-empty" data-testid="pipeline-empty">
              <p className="pipeline-empty-line">Add a step or import a pipeline.</p>
              <Button variant="secondary" size="sm" onClick={() => replaceDoc(samplePipeline(sampleSubject))} data-testid="pipeline-sample">
                <Sparkles size={14} aria-hidden /> Start from a sample
              </Button>
            </div>
          )}

          {menu && (
            <div className="pipeline-menu" style={{ left: menu.x, top: menu.y }} data-testid="pipeline-menu" role="menu">
              {menu.nodeId && (
                <button type="button" role="menuitem" onClick={() => openNodeAt(menu.nodeId!, null)}>
                  Edit step…
                </button>
              )}
              {menu.nodeId && (
                <button type="button" role="menuitem" className="is-destructive" data-testid="pipeline-menu-delete" onClick={() => removeNodes([menu.nodeId!])}>
                  <Trash2 size={12} aria-hidden /> Delete step
                </button>
              )}
              {menu.edgeId && (
                <button type="button" role="menuitem" className="is-destructive" data-testid="pipeline-menu-delete" onClick={() => removeEdges([menu.edgeId!])}>
                  <Trash2 size={12} aria-hidden /> Delete wire
                </button>
              )}
            </div>
          )}

          {refusal && (
            <div className="pipeline-refusal" role="status" data-testid="pipeline-refusal">
              {refusal}
            </div>
          )}
        </div>
      </div>

      {saveAs !== null && (
        <Dialog
          open
          onOpenChange={(open) => !open && setSaveAs(null)}
          title="Save pipeline"
          description="Saved under code/ti-toolbox/pipelines/ in this project."
          footer={
            <>
              <Button variant="ghost" onClick={() => setSaveAs(null)}>
                Cancel
              </Button>
              <Button variant="primary" disabled={!saveAs.trim() || save.isPending} onClick={() => save.mutate(saveAs.trim())} data-testid="pipeline-save-confirm">
                Save
              </Button>
            </>
          }
        >
          <Field label="Name" help="Letters, digits, space, '-' or '_'.">
            <input
              className="input"
              autoFocus
              value={saveAs}
              aria-label="Pipeline name"
              data-testid="pipeline-save-name"
              onChange={(e) => setSaveAs(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && saveAs.trim()) save.mutate(saveAs.trim());
              }}
            />
          </Field>
        </Dialog>
      )}

      {inspectedNode && inspectedEditor && (
        <NodeInspector
          doc={doc}
          node={inspectedNode}
          editor={inspectedEditor}
          focusPort={inspectField}
          onEditorChange={(next) => updateEditor(inspectedNode.id, next)}
          onLabelChange={(label) =>
            patch({ doc: { ...doc, nodes: doc.nodes.map((n) => (n.id === inspectedNode.id ? { ...n, label } : n)) } })
          }
          onClose={() => {
            if (inspectedEditor.kind === "analyzer" && !editorError(inspectedEditor)) {
              const targets = analyzerNodeTargets(inspectedEditor);
              if (targets.length > 1) {
                const configs = targets.map((target) => configFor(target, atlasLookup, inspectedNode.config, inspectedSubjects, inspectedEditor));
                const next = expandAnalysisTargets(doc, inspectedNode.id, configs);
                commit(next, Object.fromEntries(next.nodes.map((node) => [node.id, editorFromNode(node)])));
              }
            }
            setInspecting(null);
            setInspectField(null);
          }}
        />
      )}
    <ExistingOutputsDialog
        open={outputDecision !== null}
        onOpenChange={(open) => { if (!open) setOutputDecision(null); }}
        existing={outputDecision?.existing ?? 0}
        total={outputDecision?.total ?? 0}
        noun="pipeline output"
        skipWholeBatch
        replaceDisabledReason={outputDecision && !outputDecision.complete ? "Some pipeline outputs depend on unfinished steps and cannot be checked yet. Skip existing outputs or cancel." : undefined}
        busy={run.isPending}
        onDecide={(decision) => { setOutputDecision(null); if (decision === "replace") run.mutate(true); else notify.success("Pipeline skipped. No jobs were queued."); }}
      />
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
