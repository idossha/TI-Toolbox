/**
 * The Menu's composition tree — a subject, then Anatomy, Simulations and Analyses.
 *
 * Maintainer, on the `Type / Subject / Simulation / Field / Space` card it replaces (2026-09-07):
 * *"please change the menu such that there is subject and then it kind of like shows two little
 * branches with the anatomy and then there is a simulation section where they can choose the
 * different simulations — they can potentially choose multiple — and then they choose analysis
 * output; and in each one the user should be able to choose what input they want for each stage
 * ... It depends on what is available and what is selected, but it should be a continuous
 * integrated thing instead of what we have right now."*
 *
 * **What the old card got wrong** is worth stating, because it is not "it looked dated". It asked
 * for a *type* first — Subject anatomy, Simulation, Analysis, Group, Custom — and the type then
 * decided which of six dropdowns were even shown. So a person who wanted a T1 with a field on top
 * had to know that "Simulation" was the type that produced both, and a person who wanted two
 * simulations side by side could not say so at all. The type was a fact about the *server's* view
 * builders that a reader had to learn before they could describe what they wanted to look at.
 *
 * The tree has no type. It shows what this subject has, in the order the work was done, and a
 * scene is whatever is ticked.
 *
 * **The tree owns no selection.** A row is ticked when its path is in the page's one editable list
 * ("what will open"), ticking adds it and unticking removes it — see `lib.ts`'s note. That is what
 * makes it continuous rather than a fourth thing to keep in step: the branches and the list are
 * the same list, and Reset, reordering, presets and deep links all keep working with no second
 * mechanism. It also means this component is a pure function of `tree` + `chosen`, which is why
 * every rule in it is unit-testable from `lib.ts` without rendering anything.
 *
 * Availability is the server's answer, not a guess from here: a node arrives with `available` and
 * a `reason`, and an unavailable one is drawn greyed **with the reason** rather than hidden. A
 * missing input a person can see is a question they can answer ("the mesh has not been written
 * yet"); one that is silently absent is a bug report.
 */
import { useState } from "react";
import { ChevronRight, Circle } from "lucide-react";
import { Checkbox } from "../../ui";
import { branchCount, branchState, fieldOfNode, formatBytes, simulationNodeIds, toggleId, toggleMany, type TreeNode } from "./lib";
import type { ViewerTree } from "./api";

interface TreeProps {
  tree: ViewerTree | undefined;
  /** Container paths currently in the scene — the page's one list. */
  chosen: string[];
  /** Replace the list. Every tick, untick and branch toggle goes through this. */
  onChange: (next: string[]) => void;
  /** Which simulations are expanded. Drives which analyses the server lists. */
  expanded: string[];
  onExpandedChange: (next: string[]) => void;
  /** Told when a *field* row is ticked, so `draft.field` (and the window chip) keep up. */
  onFieldPicked: (simulation: string, field: string | null) => void;
  loading?: boolean;
}

/** One checkbox row. Unavailable rows stay visible and say why. */
function NodeRow({
  node,
  checked,
  onToggle,
  onPick,
}: {
  node: TreeNode;
  checked: boolean;
  onToggle: (on: boolean) => void;
  onPick?: () => void;
}) {
  const available = node.available !== false;
  return (
    <li className="viewer-tree-node" data-available={available ? undefined : "false"} data-testid={`viewer-tree-node-${node.name}`}>
      <Checkbox
        checked={checked}
        disabled={!available}
        onCheckedChange={(on) => {
          onToggle(on);
          if (on && onPick) onPick();
        }}
        aria-label={node.label}
      />
      <span className="viewer-tree-node-label" title={node.path}>
        {node.label}
      </span>
      <span className="viewer-tree-node-meta">
        {available ? (
          <>
            {node.kind === "mesh" && <span className="viewer-tree-tag">mesh</span>}
            {typeof node.bytes === "number" && formatBytes(node.bytes)}
          </>
        ) : (
          /* The reason, not a hidden row: a missing input a person can see is a question they can
             answer; one that is silently absent is a bug report. */
          <span className="viewer-tree-reason">{node.reason ?? "unavailable"}</span>
        )}
      </span>
    </li>
  );
}

/** A collapsible branch with a tri-state box that ticks or clears everything under it. */
function Branch({
  title,
  count,
  state,
  onToggleAll,
  open,
  onOpenChange,
  testId,
  children,
}: {
  title: string;
  count: string;
  state: "none" | "some" | "all";
  onToggleAll?: (on: boolean) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <section className="viewer-tree-branch" data-testid={testId} data-open={open ? "true" : "false"} data-state={state}>
      <header className="viewer-tree-branch-head">
        <button
          type="button"
          className="viewer-tree-disclose"
          onClick={() => onOpenChange(!open)}
          aria-expanded={open}
          aria-label={`${open ? "Collapse" : "Expand"} ${title}`}
          data-testid={`${testId}-toggle`}
        >
          <ChevronRight size={14} className="viewer-tree-chevron" />
        </button>
        {onToggleAll !== undefined && (
          <Checkbox
            checked={state === "all" ? true : state === "some" ? "indeterminate" : false}
            onCheckedChange={(on) => onToggleAll(on)}
            aria-label={`Select all of ${title}`}
          />
        )}
        <span className="viewer-tree-branch-title">{title}</span>
        <span className="viewer-tree-branch-count" data-testid={`${testId}-count`}>
          {count}
        </span>
      </header>
      {open && <div className="viewer-tree-branch-body">{children}</div>}
    </section>
  );
}

export function CompositionTree({ tree, chosen, onChange, expanded, onExpandedChange, onFieldPicked, loading }: TreeProps) {
  const [openBranches, setOpenBranches] = useState<Record<string, boolean>>({ anatomy: true, simulations: true, analyses: true });
  const picked = new Set(chosen);
  const setOpen = (key: string, open: boolean) => setOpenBranches((current) => ({ ...current, [key]: open }));
  const toggle = (id: string, on: boolean) => onChange(toggleId(chosen, id, on));

  if (tree !== undefined && tree.available === false) {
    // The server says why, and the two reasons are different problems: "no subject chosen" is a
    // next step, "no head model" is a missing pre-processing run.
    return (
      <p className="viewer-empty" data-testid="viewer-tree-unavailable">
        {tree.reason ?? "Nothing to compose from yet."}
      </p>
    );
  }

  if (tree === undefined) {
    return (
      <p className="viewer-empty" data-testid="viewer-tree-loading">
        {loading === true ? "Reading what this subject has…" : "Choose a subject to see what it offers."}
      </p>
    );
  }

  const anatomy = (tree.anatomy ?? []) as TreeNode[];
  const anatomyIds = anatomy.filter((n) => n.available !== false).map((n) => n.id);
  const simulations = tree.simulations ?? [];
  const analyses = tree.analyses ?? [];
  const simsSelected = simulations.filter((sim) => simulationNodeIds(sim as never).some((id) => picked.has(id))).length;
  const analysisSelected = analyses.filter((run) => (run.outputs ?? []).some((n) => picked.has(n.id))).length;

  return (
    <div className="viewer-tree" data-testid="viewer-tree">
      <Branch
        title="Anatomy"
        testId="viewer-tree-anatomy"
        count={branchCount(anatomy.length, anatomy.filter((n) => picked.has(n.id)).length, "input")}
        state={branchState(anatomyIds, picked)}
        onToggleAll={(on) => onChange(toggleMany(chosen, anatomyIds, on))}
        open={openBranches.anatomy}
        onOpenChange={(open) => setOpen("anatomy", open)}
      >
        <ul className="viewer-tree-nodes">
          {anatomy.map((node) => (
            <NodeRow key={node.id} node={node} checked={picked.has(node.id)} onToggle={(on) => toggle(node.id, on)} />
          ))}
        </ul>
      </Branch>

      <Branch
        title="Simulations"
        testId="viewer-tree-simulations"
        count={branchCount(simulations.length, simsSelected, "simulation")}
        state={simsSelected === 0 ? "none" : simsSelected === simulations.length ? "all" : "some"}
        open={openBranches.simulations}
        onOpenChange={(open) => setOpen("simulations", open)}
      >
        {simulations.length === 0 ? (
          <p className="viewer-tree-note">This subject has no simulations yet.</p>
        ) : (
          simulations.map((sim) => {
            const ids = simulationNodeIds(sim as never);
            const isOpen = expanded.includes(sim.name);
            const state = branchState(ids, picked);
            return (
              <Branch
                key={sim.name}
                title={sim.name}
                testId={`viewer-tree-sim-${sim.name}`}
                count={branchCount(ids.length, ids.filter((id) => picked.has(id)).length, "output")}
                state={state}
                onToggleAll={(on) => onChange(toggleMany(chosen, ids, on))}
                open={isOpen}
                onOpenChange={(open) =>
                  onExpandedChange(open ? [...expanded, sim.name] : expanded.filter((name) => name !== sim.name))
                }
              >
                {(
                  [
                    ["Fields", (sim.fields ?? []) as TreeNode[], true],
                    ["Meshes", (sim.meshes ?? []) as TreeNode[], false],
                    ["Electrodes", (sim.electrodes ?? []) as TreeNode[], false],
                  ] as [string, TreeNode[], boolean][]
                )
                  .filter(([, nodes]) => nodes.length > 0)
                  .map(([group, nodes, isField]) => (
                    <div className="viewer-tree-group" key={group}>
                      <p className="viewer-tree-group-title">{group}</p>
                      <ul className="viewer-tree-nodes">
                        {nodes.map((node) => (
                          <NodeRow
                            key={node.id}
                            node={node}
                            checked={picked.has(node.id)}
                            onToggle={(on) => toggle(node.id, on)}
                            /* Ticking a field row is a *selection* change, not just a list edit:
                               it decides which field the window chip describes, so the draft has
                               to follow it. Ticking anything else stays a free local edit. */
                            onPick={isField ? () => onFieldPicked(sim.name, fieldOfNode(node.name)) : undefined}
                          />
                        ))}
                      </ul>
                    </div>
                  ))}
              </Branch>
            );
          })
        )}
      </Branch>

      <Branch
        title="Analyses"
        testId="viewer-tree-analyses"
        count={branchCount(analyses.length, analysisSelected, "run")}
        state={analysisSelected === 0 ? "none" : analysisSelected === analyses.length ? "all" : "some"}
        open={openBranches.analyses}
        onOpenChange={(open) => setOpen("analyses", open)}
      >
        {analyses.length === 0 ? (
          <p className="viewer-tree-note">
            {expanded.length === 0
              ? "Expand a simulation above to see its analyses."
              : "No analyses have been run on the expanded simulations."}
          </p>
        ) : (
          analyses.map((run) => {
            const nodes = (run.outputs ?? []) as TreeNode[];
            const ids = nodes.map((n) => n.id);
            return (
              <div className="viewer-tree-group" key={`${run.simulation}/${run.name}`}>
                <p className="viewer-tree-group-title">
                  <Circle size={7} className="viewer-tree-dot" aria-hidden />
                  {run.name}
                  <span className="viewer-tree-group-meta">{run.simulation}</span>
                </p>
                <ul className="viewer-tree-nodes">
                  {nodes.map((node) => (
                    <NodeRow key={node.id} node={node} checked={picked.has(node.id)} onToggle={(on) => toggle(node.id, on)} />
                  ))}
                </ul>
                {ids.length > 1 && (
                  <button type="button" className="viewer-link" onClick={() => onChange(toggleMany(chosen, ids, true))}>
                    Add all
                  </button>
                )}
              </div>
            );
          })
        )}
      </Branch>
    </div>
  );
}