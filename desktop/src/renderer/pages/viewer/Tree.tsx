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
import {
  branchCount,
  branchState,
  fieldOfNode,
  formatBytes,
  groupAnatomy,
  kindChip,
  simulationNodeIds,
  toggleId,
  toggleMany,
  type TreeNode,
} from "./lib";
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

/**
 * One checkbox row. Unavailable rows stay visible and say why.
 *
 * The chip is the server's `kind` verbatim (`tit/catalog.py::classify_view_file`) and never a
 * guess from the extension — which is what put MESH on `lh.central.gii` beside the real
 * `Head mesh (ernie)` in the maintainer's screenshot of 2026-09-07. A **surface** row also draws
 * its attachments underneath as sub-checkboxes, because a `.annot` is a colour table with nowhere
 * to go until a surface is ticked, and putting it at the same level as one said otherwise.
 */
function NodeRow({
  node,
  chosen,
  onToggle,
  onPick,
  depth = 0,
  owner,
}: {
  node: TreeNode;
  chosen: ReadonlySet<string>;
  onToggle: (id: string, on: boolean) => void;
  onPick?: () => void;
  depth?: number;
  /**
   * The surface this row hangs under, for an attachment row's test id.
   *
   * A hemisphere's `.annot` files apply to *every* surface of that hemisphere — they share a
   * vertex numbering — so ernie's three `lh.*` sheets each offer the same three parcellations,
   * and the file name alone does not identify a row. The tick is still keyed on the file (a
   * parcellation is chosen once per hemisphere; `tit/viewspec.py::_surface_for_attachment` puts
   * it on the last surface of that hemisphere in the list), so this names the row and nothing
   * else.
   */
  owner?: string;
}) {
  const available = node.available !== false;
  const checked = chosen.has(node.id);
  const attachments = node.attachments ?? [];
  return (
    <>
      <li
        className="viewer-tree-node"
        data-available={available ? undefined : "false"}
        data-kind={node.kind}
        data-depth={depth > 0 ? String(depth) : undefined}
        data-testid={owner === undefined ? `viewer-tree-node-${node.name}` : `viewer-tree-attachment-${owner}-${node.name}`}
      >
        <Checkbox
          checked={checked}
          disabled={!available}
          onCheckedChange={(on) => {
            onToggle(node.id, on);
            if (on && onPick) onPick();
          }}
          aria-label={node.label}
        />
        <span className="viewer-tree-node-label" title={node.path}>
          {node.label}
        </span>
        <span className="viewer-tree-node-meta">
          <span className="viewer-tree-tag" data-kind={node.kind} data-testid={`viewer-tree-chip-${owner === undefined ? node.name : `${owner}-${node.name}`}`}>
            {kindChip(node.kind)}
          </span>
          {available ? (
            typeof node.bytes === "number" && formatBytes(node.bytes)
          ) : (
            /* The reason, not a hidden row: a missing input a person can see is a question they
               can answer; one that is silently absent is a bug report. This is also where an
               embed too old to draw a surface says so, rather than the row being sent as a mesh. */
            <span className="viewer-tree-reason">{node.reason ?? "unavailable"}</span>
          )}
        </span>
      </li>
      {attachments.map((attachment) => (
        <NodeRow key={attachment.id} node={attachment} chosen={chosen} onToggle={onToggle} depth={depth + 1} owner={node.name} />
      ))}
    </>
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
        {/* Grouped by what the file *is*, not by the directory it came out of. A flat list put
            `lh.central.gii` (an 8 MB cortical sheet) between `T1.nii.gz` and `ernie.msh` (a 64 MB
            FEM volume) with nothing to say they were three different kinds of thing. */}
        {groupAnatomy(anatomy).map((group) => (
          <div className="viewer-tree-group" key={group.key} data-testid={`viewer-tree-anatomy-${group.key}`}>
            <p className="viewer-tree-group-title">{group.title}</p>
            <ul className="viewer-tree-nodes">
              {group.nodes.map((node) => (
                <NodeRow key={node.id} node={node} chosen={picked} onToggle={toggle} />
              ))}
            </ul>
          </div>
        ))}
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
                    /* Surfaces are their own group here for the same reason they are their own
                       kind: an fsaverage `.gii` is a few MB and a `.msh` is 64, and filing them
                       together said they were the same sort of wait. */
                    ["Surfaces", ((sim as { surfaces?: TreeNode[] }).surfaces ?? []) as TreeNode[], false],
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
                            chosen={picked}
                            onToggle={toggle}
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
                    <NodeRow key={node.id} node={node} chosen={picked} onToggle={toggle} />
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