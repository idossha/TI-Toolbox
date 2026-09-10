/**
 * The Simulator's **Jobs table** — one row per job, and the row owns its inputs.
 *
 * Maintainer, 2026-09-06, against a 2.5.0 screenshot of the "Simulation Jobs" cards: *"it's hard
 * to separate users, montages, modes in different jobs. In 2.5.0, within a job users could
 * manipulate the subject, the mode, the montage, the current intensities, and so on. We need that
 * capability."* The v3 page had replaced those cards with a **global** subject set plus a montage
 * list fanned out across it, so a run was a cross-product the user had to hold in their head and
 * could not break: three subjects × two montages was six jobs, and there was no way to say "ernie
 * on F3_F4, 101 on the flex result".
 *
 * So the row is the job again. Its cells are, left to right:
 *
 *   Subject · Source · EEG net · Montage · Pairs · Currents (mA) · actions
 *
 * and the cells that mean different things under different sources change *inside their column*:
 * the widths come from `resolveColumnWidths` and a `<colgroup>`, so switching a row from Montage
 * to Flex result moves nothing anywhere else in the table (the same reservation rule the currents
 * column already used for the TI ↔ mTI switch).
 *
 * What is still global lives on the page: electrodes, conductivity and output fields are
 * properties of the *run*, not of a job, and 2.5.0 had them global too.
 *
 * This file also keeps the montage **editor** (the "New montage" draft card, whose state is lifted
 * to the page so the 3-D pane and the pairs form edit one draft) and the delete confirmation.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Pencil, Trash2, X, Copy, SlidersHorizontal } from "lucide-react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Checkbox } from "../../ui/Toggle";
import { Button, IconButton } from "../../ui/Button";
import { AlertDialog, Dialog } from "../../ui/Overlay";
import { Field, TextInput } from "../../ui/Field";
import { Select } from "../../ui/Select";
import { SelectionPicker } from "../../ui/SelectionList";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Card, CardHeader, CardBody } from "../../ui/Layout";
import { ElectrodePairsEditor, type ElectrodePair } from "../../ui/ElectrodePairsEditor";
import { notify } from "../../ui/Toast";
import { NumberInput } from "../../ui/NumberInput";
import { channelCss } from "../_shared/scene/model";
import { deleteFreehand, deleteMontage, getEegNets, getFlexMapping, getFlexRuns, getFreehand, getMontages, putMontage, type FlexRun, type FreehandConfig } from "./api";
import { OPTIMIZED, placementsFor, type FlexPlacement } from "./FlexTab";
import { FreehandEditor } from "./FreehandEditor";
import { useFreehandDraft } from "./freehandDraft";
import "./simulator-page.css";
import {
  SOURCE_OPTIONS,
  currentsCount,
  defaultCurrents,
  defaultCurrentsFor,
  emptyRow,
  inferMontageKind,
  isRunnableRow,
  isCustomised,
  newRowId,
  polarityLabel,
  rowPairCount,
  settingsSummary,
  type JobSettings,
  type MontageKind,
  type MontagePreview,
  type MontageSource,
  type SelectedRow,
} from "./types";

export type Kind = MontageKind;

/** A montage as the table addresses it: which net's bucket it lives in, and its pairs. */
export interface CatalogMontage {
  net: string;
  kind: MontageKind;
  name: string;
  pairs: [string, string][];
}

type SavedDefinition = { type: "montage"; net: string; kind: MontageKind; name: string } | { type: "placement"; subject: string; name: string };
const definitionKey = (item: SavedDefinition) => JSON.stringify(item.type === "montage" ? [item.type, item.net, item.kind, item.name] : [item.type, item.subject, item.name]);
const matchesDefinition = (row: SelectedRow, item: SavedDefinition) => item.type === "montage"
  ? row.source === "montage" && row.eegNet === item.net && row.kind === item.kind && row.name === item.name
  : row.source === "freehand" && row.subjectId === item.subject && row.name === item.name;

/** `${kind}:${name}` — the montage `Select`'s option value, since one name can exist in both
 *  buckets of the same net. */
export function montageOptionValue(kind: MontageKind, name: string): string {
  return `${kind}:${name}`;
}

export function parseMontageOptionValue(value: string): { kind: MontageKind; name: string } {
  const cut = value.indexOf(":");
  return { kind: value.slice(0, cut) as MontageKind, name: value.slice(cut + 1) };
}

/** `E1–E2 · E3–E4` — the read-only pairs cell for a label-based montage. */
export function formatPairs(pairs: [string, string][]): string {
  return pairs.map(([a, b]) => `${a}–${b}`).join(" · ");
}

/** The Pairs text for any row, whichever form its electrodes came in. Empty — not a dash — for a
 *  row that has none yet: an unconfigured cell shows its own placeholder and nothing else. */
export function rowPairsText(row: SelectedRow): string {
  if (row.pairs && row.pairs.length > 0) return formatPairs(row.pairs);
  const n = row.xyzPairs?.length ?? 0;
  return n > 0 ? `${n * 2} XYZ coordinates` : "";
}

/** The row's currents, normalised to the count its polarity requires (extra values dropped, a
 *  short list padded with 1.0). */
export function currentValues(currents: string, count: number): number[] {
  // A blank cell is an *unset* current, not zero — `Number("")` is 0, which is why the empty wire
  // string used to normalise to `[0, 1]` rather than the documented `[1, 1]`.
  const parsed = currents.split(",").map((v) => (v.trim() === "" ? Number.NaN : Number(v.trim())));
  return Array.from({ length: count }, (_, i) => {
    const v = parsed[i];
    return v === undefined || Number.isNaN(v) ? 1.0 : v;
  });
}

/**
 * How many current inputs a row shows: a catalog montage's polarity is the bucket it lives in; a
 * flex or free-hand row has none, so it follows the pair count (`inferMontageKind`).
 */
export function rowCurrentsCount(row: SelectedRow): number {
  const pairs = rowPairCount(row);
  return currentsCount(row.kind ?? inferMontageKind(pairs), pairs);
}

/* ------------------------------------------------------------------------------------------------
 * Column widths.
 *
 * The table must never scroll sideways (its container's scrollWidth == clientWidth is asserted),
 * which rules out a pixel colgroup: the actions column is fixed and the four content columns share
 * what is left, resolved to exact pixels that sum to the container.
 *
 * **Why four and not six** (maintainer, 2026-09-06, on a screenshot of the six-column table):
 * *"Montage select truncated to 'Ch…', nets 'BioSemi-128-A1…', Pairs 'E09…'"*. Measured in the app
 * at 1280 with the default pane, the table container is 608px and its content needs
 * `GSN-HydroCel-185` 113px, `VAL_lhipp_flex_focality` 137px, `Flex result` 61px, a subject id 30px
 * — plus 36px of select chrome each (the table's own compact trigger padding, simulator-page.css)
 * and the 96px actions column. Six columns of controls cannot
 * hold that; four can, with 512px to share. So the job is **two lines**: line 1 is what the job
 * *is* (subject, source, net, montage/run) and line 2 is what it will *do* (placement, electrode
 * pairs in full, one current per pair). Line 2 is one `colspan` cell with its own flex layout, so
 * it never has to agree with line 1's column boundaries.
 * --------------------------------------------------------------------------------------------- */

export type ColumnKey = "subject" | "source" | "net" | "montage";

/** The widths a user can set. */
export type StoredColumns = Partial<Record<ColumnKey, number>>;

export interface ColumnWidths {
  subject: number;
  source: number;
  net: number;
  montage: number;
  actions: number;
}

/**
 * Four 28px icon buttons (settings · duplicate · edit · remove), 2px apart, inside a cell with 4px
 * of padding. No slack column: the cell spans both lines of the job and its buttons sit on line 1.
 * (The montage-editor pencil is only on a catalog-montage row, so most rows show three.)
 */
export const ACTIONS_W = 124;

/** Below these a column stops being a control and becomes a sliver. They are *drag* floors, not
 *  the default widths: the defaults below are what keeps real names untruncated. */
export const COLUMN_MIN: Record<ColumnKey, number> = {
  subject: 56,
  source: 84,
  net: 120,
  montage: 156,
};

/** Shares of the resizable area when nothing is stored — the measured widths above, in order:
 *  a subject id, a source label, a net name and a montage or flex-run name, none truncated at the
 *  608px the default 1280 pane gives. */
const COLUMN_DEFAULT_FRACTION = { subject: 0.13, source: 0.2, net: 0.31, montage: 0.36 } as const;

/** New key: the columns are not the ones `tit-sim-jobs-columns-v1` stored. */
export const COLUMNS_STORAGE_KEY = "tit-sim-jobs-columns-v2";

/**
 * Exact pixel widths for a table `container` px wide. Total is always `container`, so a colgroup
 * built from it cannot overflow — that is the invariant, not an arithmetic coincidence.
 */
export function resolveColumnWidths(container: number, stored: StoredColumns): ColumnWidths {
  const avail = Math.max(0, Math.round(container) - ACTIONS_W);
  const keys = ["subject", "source", "net", "montage"] as const;
  const w = {
    subject: 0,
    source: 0,
    net: 0,
    montage: 0,
  };
  for (const k of keys) {
    w[k] = Math.max(COLUMN_MIN[k], Math.round(stored[k] ?? avail * COLUMN_DEFAULT_FRACTION[k]));
  }
  // The montage column absorbs what the others leave, then the shrink walks back up the row, then
  // — when even the minimums do not fit — everything scales and the residue lands on `montage`.
  const total = () => keys.reduce((sum, k) => sum + w[k], 0);
  if (total() !== avail) {
    w.montage = Math.max(COLUMN_MIN.montage, avail - w.subject - w.source - w.net);
  }
  if (total() > avail) {
    let need = total() - avail;
    // The column the user just dragged gives last: a drag that does not fit takes its room from
    // the others first, and only then stops growing.
    for (const k of ["montage", "subject", "source", "net"] as const) {
      const give = Math.min(w[k] - COLUMN_MIN[k], need);
      w[k] -= give;
      need -= give;
      if (need <= 0) break;
    }
  }
  if (total() > avail && total() > 0) {
    const scale = avail / total();
    for (const k of keys) w[k] = Math.max(1, Math.floor(w[k] * scale));
  }
  w.montage = Math.max(1, w.montage + (avail - total()));
  return { ...w, actions: ACTIONS_W };
}

/**
 * What to call the two content columns, given the sources in the table: the majority wins, and a
 * tie (or an empty table) reads as `Montage`, the source a fresh row starts on.
 */
export function headingsFor(sources: MontageSource[]): { pick: string; qualifier: string } {
  const counts = { montage: 0, flex: 0, freehand: 0 };
  for (const s of sources) counts[s] += 1;
  const majority: MontageSource =
    counts.flex > counts.montage && counts.flex >= counts.freehand
      ? "flex"
      : counts.freehand > counts.montage && counts.freehand > counts.flex
        ? "freehand"
        : "montage";
  if (majority === "flex") return { pick: "Flex run", qualifier: "Placement" };
  if (majority === "freehand") return { pick: "Free-hand set", qualifier: "Electrodes" };
  return { pick: "EEG net", qualifier: "Montage" };
}

/** Reads the persisted widths; never throws (storage can be disabled or corrupt). */
export function readStoredColumns(storage: Pick<Storage, "getItem"> | undefined): StoredColumns {
  if (!storage) return {};
  try {
    const raw = storage.getItem(COLUMNS_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const rec = parsed as Record<string, unknown>;
    const out: StoredColumns = {};
    for (const k of ["subject", "source", "net", "montage"] as const) {
      const v = rec[k];
      if (typeof v === "number" && Number.isFinite(v)) out[k] = Math.max(COLUMN_MIN[k], Math.round(v));
    }
    return out;
  } catch {
    return {};
  }
}

export function writeStoredColumns(storage: Pick<Storage, "setItem"> | undefined, cols: StoredColumns): void {
  if (!storage) return;
  try {
    storage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify(cols));
  } catch {
    /* storage disabled or full — the table still resizes, it just forgets. */
  }
}

/** One header boundary. Pointer capture and arrow keys, the same gesture as the pane divider. */
function ColumnHandle({ label, width, onResize }: { label: string; width: number; onResize: (next: number) => void }) {
  return (
    <button
      type="button"
      className="montage-col-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label} column`}
      tabIndex={0}
      onPointerDown={(e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startWidth = width;
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        const onMove = (ev: PointerEvent) => onResize(startWidth + (ev.clientX - startX));
        const onUp = () => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
      }}
      onKeyDown={(e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        e.stopPropagation();
        onResize(width + (e.key === "ArrowRight" ? 16 : -16));
      }}
    />
  );
}

/**
 * Line 2's channel list: one group per channel — `[colour dot] E034–E020 [1] mA` — so the current
 * sits **next to the pair it drives** rather than in a separate right-aligned block where nobody
 * could tell which value belonged to which channel (maintainer, 2026-09-06).
 *
 * The dot is the scene's own channel colour (Okabe-Ito, `channelCss`), which is what the 3-D pane's
 * legend and its electrode markers use: "channel 2 is orange" means one thing in this table, in the
 * legend and in the pane.
 */
function ChannelList({ row, onChange }: { row: SelectedRow; onChange: (currents: string) => void }) {
  const count = rowCurrentsCount(row);
  if (count === 0 || !row.name) return null;
  const values = currentValues(row.currents, count);
  const labels = channelLabels(row, count);
  return (
    <>
      {values.map((v, i) => (
        <span className="job-channel" key={i} data-channel={i}>
          <span className="job-channel-dot" style={{ background: channelCss(i) }} aria-hidden />
          <span className="job-channel-pair mono text-dense" data-cell="pair">
            {labels[i]}
          </span>
          <NumberInput
            value={v}
            onValueChange={(next) => onChange(values.map((old, idx) => (idx === i ? (next ?? old) : old)).join(","))}
            step={0.1}
            min={0}
            aria-label={`${row.name || "row"} channel ${i + 1} current (mA)`}
          />
          <span className="montage-unit">mA</span>
        </span>
      ))}
    </>
  );
}

/**
 * The chip line 2 carries when a job does not use the built-in defaults — on a half-filled row
 * too, because a row seeded from the last configured job is customised before it has a montage.
 */
function customChip(row: SelectedRow, defaults: JobSettings) {
  const summary = row.settings ? settingsSummary(row.settings, defaults) : "";
  if (!summary) return null;
  return (
    <span className="job-custom-chip" data-cell="custom" title="This job does not use the built-in defaults">
      custom: {summary}
    </span>
  );
}

/** What each channel of a row is, in words: its electrode pair, or its coordinate count. */
export function channelLabels(row: SelectedRow, count: number): string[] {
  return Array.from({ length: count }, (_, i) => {
    const pair = row.pairs?.[i];
    if (pair) return `${pair[0]}–${pair[1]}`;
    if (row.xyzPairs?.[i]) return "XYZ (2 pts)";
    return "—";
  });
}

/**
 * The montage being written — the editor's whole state, lifted to the page (SCC).
 *
 * The scene pane places electrodes into exactly these pairs, and a pane that had to reach into a
 * child component's private state could only do it by duplicating them. The page owns one draft;
 * the table and the pane are two editors of it.
 */
export interface MontageDraft {
  name: string;
  pairs: ElectrodePair[];
  /** The bucket an *existing* montage was opened from — a new draft has none and infers it. */
  savedAs?: MontageKind;
}

/** A fresh draft: two empty pairs, the smallest real montage (TI). Its polarity is not a choice —
 *  it follows from how many pairs the user ends up filling in (`inferMontageKind`). */
export function emptyDraft(): MontageDraft {
  return { name: "", pairs: [["", ""], ["", ""]] };
}

/** Matches `Montage.simulation_mode`: exactly 2 pairs (TI) or 4+ pairs (mTI); 1 or 3 is invalid. */
function isValidPairCount(n: number): boolean {
  return n === 2 || n >= 4;
}

/** A subject as the Subject cell addresses it: its id and whether a simulation can run on it. */
export interface JobSubject {
  id: string;
  /** `undefined` when the subject is usable; otherwise the reason it is not (J3 wording). */
  blockedReason?: string;
}

export interface JobsTableProps {
  /** Every subject in the project, with this page's own readiness verdict. */
  subjects: JobSubject[];
  /** subjectId -> eeg net names it has (from SubjectDetail.eeg_nets). */
  subjectNets: Record<string, string[]>;
  rows: SelectedRow[];
  onRowsChange: (next: SelectedRow[]) => void;
  /** The montage being written, owned by the page and shared with the scene pane. */
  draft: MontageDraft | null;
  onDraftChange: (draft: MontageDraft | null) => void;
  /** The resolved net, reported upward so the scene pane draws the same one's electrodes. */
  onNetChange?: (net: string | undefined) => void;
  /**
   * The row the user clicked, reported upward so the 3-D pane draws THAT job (its net's electrodes
   * as idle dots, its own pairs coloured by channel) — visual confirmation of a job that is
   * already configured, not an editor. `null` when no row is active or the row has no net.
   */
  onPreviewChange?: (preview: MontagePreview | null) => void;
  /** The source of the active row, so the page can note that flex/free-hand carry their own
   *  coordinates rather than the previewed net's. */
  onActiveSourceChange?: (source: MontageSource | null) => void;
  /** The built-in defaults — what a row that carries no settings of its own runs with. */
  defaults: JobSettings;
  /** What a NEW row starts from: the settings of the row the user configured last, if any. */
  seedSettings?: JobSettings;
  /** Open this row's own settings editor (electrodes · conductivity · output fields). */
  onEditSettings?: (row: SelectedRow) => void;
}

export function JobsTable({
  subjects,
  subjectNets,
  rows,
  onRowsChange,
  draft,
  onDraftChange,
  onNetChange,
  onPreviewChange,
  onActiveSourceChange,
  defaults,
  seedSettings,
  onEditSettings,
}: JobsTableProps) {
  const queryClient = useQueryClient();
  const montages = useQuery({ queryKey: ["montages"], queryFn: getMontages });

  const usable = useMemo(() => subjects.filter((s) => !s.blockedReason).map((s) => s.id), [subjects]);

  // Flex runs and free-hand configs, per usable subject: a row's Montage cell needs the catalog for
  // *its own* subject, so this is one query each rather than one for the page's "current" subject.
  const flexQueries = useQueries({
    queries: usable.map((id) => ({ queryKey: ["flex-runs", id], queryFn: () => getFlexRuns(id), staleTime: 60_000 })),
  });
  const freehandQueries = useQueries({
    queries: usable.map((id) => ({ queryKey: ["freehand", id], queryFn: () => getFreehand(id), staleTime: 60_000 })),
  });
  /* Derived on every render rather than memoized, the precedent `RunControls.tsx`'s `useSimPlan`
     set: `useQueries` hands back a fresh array each render, so a `useMemo` over it can only be
     keyed on a serialisation — which React Compiler correctly refuses to treat as preserved
     memoization. Both are maps over a project's few subjects. */
  const flexBySubject: Record<string, FlexRun[]> = {};
  const freehandBySubject: Record<string, FreehandConfig[]> = {};
  usable.forEach((id, i) => {
    flexBySubject[id] = flexQueries[i]?.data ?? [];
    freehandBySubject[id] = freehandQueries[i]?.data ?? [];
  });

  const availableNets = useMemo(() => {
    const nets = new Set<string>();
    for (const list of Object.values(subjectNets)) for (const n of list) nets.add(n);
    if (montages.data) for (const n of Object.keys(montages.data.nets)) nets.add(n);
    return [...nets].sort();
  }, [subjectNets, montages.data]);

  /*
   * The net is a cell of the row, not a control above the table. `editorNet` is only the net a
   * *new* row and the montage editor start on — the last net the user touched, falling back to the
   * first available.
   */
  const [netChoice, setNetChoice] = useState<string | undefined>(undefined);
  const editorNet = netChoice && availableNets.includes(netChoice) ? netChoice : availableNets[0];

  const editing = draft;
  const setEditing = onDraftChange;
  const [manageOpen, setManageOpen] = useState(false);
  const [selectedDefinitions, setSelectedDefinitions] = useState<SavedDefinition[]>([]);
  const [bulkTargets, setBulkTargets] = useState<SavedDefinition[] | null>(null);
  function selectDefinition(item: SavedDefinition, selected: boolean) {
    setSelectedDefinitions((items) => selected ? [...items.filter((value) => definitionKey(value) !== definitionKey(item)), item] : items.filter((value) => definitionKey(value) !== definitionKey(item)));
  }
  const [managedNet, setManagedNet] = useState<string | undefined>();
  const [managedSubject, setManagedSubject] = useState<string | undefined>();
  const managementNet = managedNet ?? editorNet;
  const managementSubject = managedSubject ?? usable[0];
  const [deletePlacement, setDeletePlacement] = useState<{ subject: string; name: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CatalogMontage | null>(null);
  /*
   * Free-hand placements are authored from this same footer ("New placement"), not from a section
   * of their own (maintainer, 2026-09-06). Only one editor is open at a time; the fact one is open
   * is page-session state so the page comes back as the user left it.
   */
  // The draft itself (open, subject, name, rows) is the page's, not this table's: the 3-D pane
  // writes into the same rows. See `freehandDraft.tsx`.
  const { open: freehandOpen, setOpen: setFreehandOpen } = useFreehandDraft();
  /** The row the 3-D pane is drawing. Click a row (not a control in it) to change it. */
  const [activeId, setActiveId] = useState<string | null>(null);

  // The scene pane draws the net the editor is on. Reported in an effect, not during render: it
  // is the parent's state.
  useEffect(() => {
    onNetChange?.(editorNet);
  }, [editorNet, onNetChange]);

  const netElectrodes = useQuery({
    queryKey: ["eeg-net-electrodes", editorNet, usable[0]],
    queryFn: async () => {
      const subject = usable.find((s) => subjectNets[s]?.includes(editorNet!)) ?? usable[0];
      if (!subject || !editorNet) return [] as string[];
      const nets = await getEegNets(subject);
      return nets.find((n) => n.name === editorNet)?.electrodes ?? [];
    },
    enabled: !!editorNet && usable.length > 0,
  });

  /** Every montage of one net, both buckets, in one list — the Montage cell's options. */
  const montagesOf = useMemo(() => {
    return (net: string | undefined): CatalogMontage[] => {
      if (!net) return [];
      const entry = montages.data?.nets[net];
      if (!entry) return [];
      const of = (kind: MontageKind, bucket: Record<string, string[][]> | undefined) =>
        Object.entries(bucket ?? {}).map(([name, pairs]) => ({
          net,
          kind,
          name,
          pairs: pairs.map((p) => [p[0], p[1]] as [string, string]),
        }));
      return [...of("uni_polar", entry.uni_polar), ...of("multi_polar", entry.multi_polar)];
    };
  }, [montages.data]);

  const saveMontage = useMutation({
    mutationFn: ({ net, kind, name, pairs }: { net: string; kind: MontageKind; name: string; pairs: ElectrodePair[] }) =>
      putMontage(net, kind, name, pairs.map((p) => [p[0], p[1]])),
    onSuccess: (_data, vars) => {
      notify.success(`Saved montage "${vars.name}".`);
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
    },
    onError: (err: unknown) => notify.error("Could not save the montage.", err instanceof Error ? err.message : undefined),
  });

  const removeMontage = useMutation({
    mutationFn: (m: CatalogMontage) => deleteMontage(m.net, m.kind, m.name),
    onSuccess: (_data, m) => {
      notify.success(`Deleted montage "${m.name}".`);
      setDeleteTarget(null);
      selectDefinition({ type: "montage", ...m }, false);
      // Every row that pointed at it goes back to "pick a montage" rather than silently planning a
      // montage that no longer exists.
      onRowsChange(
        rowsRef.current.map((r) =>
          r.source === "montage" && r.eegNet === m.net && r.kind === m.kind && r.name === m.name
            ? { ...r, name: "", kind: undefined, pairs: undefined }
            : r,
        ),
      );
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
    },
    onError: (err: unknown) => notify.error("Could not delete the montage.", err instanceof Error ? err.message : undefined),
  });

  const removePlacement = useMutation({
    mutationFn: ({ subject, name }: { subject: string; name: string }) => deleteFreehand(subject, name),
    onSuccess: (_data, target) => {
      notify.success(`Deleted placement "${target.name}".`);
      setDeletePlacement(null);
      selectDefinition({ type: "placement", ...target }, false);
      onRowsChange(rowsRef.current.map((row) => row.source === "freehand" && row.subjectId === target.subject && row.name === target.name
        ? { ...row, name: "", xyzPairs: undefined, pairs: undefined, kind: undefined }
        : row));
      void queryClient.invalidateQueries({ queryKey: ["freehand", target.subject] });
    },
    onError: (error: unknown) => notify.error("Could not delete the placement.", error instanceof Error ? error.message : undefined),
  });

  const removeSelected = useMutation({
    mutationFn: async (targets: SavedDefinition[]) => {
      const results = await Promise.allSettled(targets.map((item) => item.type === "montage"
        ? deleteMontage(item.net, item.kind, item.name) : deleteFreehand(item.subject, item.name)));
      return { deleted: targets.filter((_, index) => results[index]?.status === "fulfilled"), failed: targets.filter((_, index) => results[index]?.status === "rejected") };
    },
    onSuccess: ({ deleted, failed }) => {
      onRowsChange(rowsRef.current.map((row) => deleted.some((item) => matchesDefinition(row, item)) ? { ...row, name: "", kind: undefined, pairs: undefined, xyzPairs: undefined } : row));
      setSelectedDefinitions(failed);
      void queryClient.invalidateQueries({ queryKey: ["montages"] });
      void queryClient.invalidateQueries({ queryKey: ["freehand"] });
      if (deleted.length) notify.success(`Deleted ${deleted.length} saved definition${deleted.length === 1 ? "" : "s"}.`);
      if (failed.length) notify.error(`${failed.length} definition${failed.length === 1 ? "" : "s"} could not be deleted. They remain selected so you can retry.`);
    },
  });
  const deletingDefinitions = removeSelected.isPending || removeMontage.isPending || removePlacement.isPending;

  // The mapping fetch resolves after other edits may have landed; the continuation must patch the
  // rows as they are then, not as they were when the request went out.
  const rowsRef = useRef(rows);
  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);

  const patch = useCallback(
    (id: string, next: Partial<SelectedRow>) => onRowsChange(rows.map((r) => (r.id === id ? { ...r, ...next } : r))),
    [rows, onRowsChange],
  );

  /* ------------------------------------------------------------------ Row edits */

  function setRowSubject(row: SelectedRow, subjectId: string) {
    // A montage/net the new subject does not have is not a job — clear back to "pick one" rather
    // than carrying an unrunnable row forward.
    const keepsNet = row.source !== "montage" || !row.eegNet || (subjectNets[subjectId]?.includes(row.eegNet) ?? false);
    patch(row.id, keepsNet && row.source === "montage" ? { subjectId } : { subjectId, name: "", kind: undefined, pairs: undefined, xyzPairs: undefined, eegNet: row.source === "montage" ? row.eegNet : undefined });
  }

  function setRowSource(row: SelectedRow, source: MontageSource) {
    setActiveId(row.id);
    patch(row.id, {
      source,
      name: "",
      kind: undefined,
      pairs: undefined,
      xyzPairs: undefined,
      eegNet: source === "montage" ? (row.eegNet ?? editorNet) : undefined,
      currents: "1.0,1.0",
    });
  }

  function setRowNet(row: SelectedRow, net: string) {
    setNetChoice(net);
    // The montage belonged to the old net.
    patch(row.id, { eegNet: net, name: "", kind: undefined, pairs: undefined });
  }

  function setRowMontage(row: SelectedRow, value: string) {
    const { kind, name } = parseMontageOptionValue(value);
    const montage = montagesOf(row.eegNet).find((m) => m.kind === kind && m.name === name);
    if (!montage) return;
    setNetChoice(montage.net);
    patch(row.id, {
      kind: montage.kind,
      name: montage.name,
      pairs: montage.pairs,
      xyzPairs: undefined,
      currents: defaultCurrentsFor(montage.kind, montage.pairs.length),
    });
  }

  /** The placements a flex row can be simulated in, for the row's own subject and run. */
  function placementsForRow(row: SelectedRow): FlexPlacement[] {
    const run = (flexBySubject[row.subjectId] ?? []).find((r) => r.name === row.name);
    return run ? placementsFor(run) : [];
  }

  function applyFlexPlacement(row: SelectedRow, placement: FlexPlacement) {
    const numPairs = placement.pairs?.length ?? placement.xyzPairs?.length ?? 0;
    patch(row.id, {
      eegNet: placement.value === OPTIMIZED ? undefined : placement.value,
      pairs: placement.pairs,
      xyzPairs: placement.xyzPairs,
      currents: defaultCurrents(numPairs),
    });
  }

  /** EEG nets are named by their CSV filename on a real project and by their stem in some
   *  catalogs; a placement's net and the subject's net list must still compare equal. */
  const netStem = (net: string) => net.replace(/\.csv$/, "");

  /**
   * The row's mapped net, whether or not the run was ever mapped onto it.
   *
   * Maintainer, 2026-09-06: *"allow users to choose if they want to run the job with the fully
   * optimised locations or map them to a certain net."* A run only writes
   * `electrode_mapping_<net>.json` for the nets it was already mapped onto, so offering only those
   * would hide most of the subject's caps. The server maps the optimised XYZ onto any net
   * (`tit/sim/montage_sources.py`, Hungarian assignment) and caches the file it writes, so a net
   * picked here resolves to real labels — which is what the row must carry, since `POST /api/jobs`
   * takes a fully-resolved `Montage`.
   */
  async function mapRowToNet(row: SelectedRow, net: string) {
    const known = placementsForRow(row).find((p) => p.value !== OPTIMIZED && netStem(p.value) === netStem(net));
    if (known) {
      applyFlexPlacement(row, known);
      return;
    }
    // Optimistic: the cell shows the net at once, the pairs land when the mapping comes back.
    patch(row.id, { eegNet: net, pairs: undefined, xyzPairs: undefined });
    try {
      const mapping = await queryClient.fetchQuery({
        queryKey: ["flex-mapping", row.subjectId, row.name, net],
        queryFn: () => getFlexMapping(row.subjectId, row.name, net),
        staleTime: 60_000,
      });
      const pairs = (mapping.pairs ?? []).filter((p) => p.length === 2).map((p) => [p[0], p[1]] as [string, string]);
      onRowsChange(
        rowsRef.current.map((r) =>
          r.id === row.id && r.eegNet === net
            ? { ...r, pairs, xyzPairs: undefined, currents: defaultCurrents(pairs.length) }
            : r,
        ),
      );
      void queryClient.invalidateQueries({ queryKey: ["flex-runs", row.subjectId] });
    } catch (err) {
      notify.error(`Could not map ${row.name} onto ${net}.`, err instanceof Error ? err.message : undefined);
    }
  }

  /** Switches a flex row between the optimiser's own coordinates and a net's labels. */
  function setRowPlacementMode(row: SelectedRow, mode: "optimised" | "mapped") {
    if (mode === "optimised") {
      const free = placementsForRow(row).find((p) => p.value === OPTIMIZED);
      if (free) applyFlexPlacement(row, free);
      return;
    }
    if (row.eegNet) return;
    // The net the run was already mapped onto is the natural first choice; otherwise the subject's
    // first cap, which the server will map on demand.
    const nets = netsForSubject(row.subjectId);
    const mapped = placementsForRow(row).find((p) => p.value !== OPTIMIZED);
    const net = (mapped && nets.find((n) => netStem(n) === netStem(mapped.value))) ?? mapped?.value ?? nets[0];
    if (net) void mapRowToNet(row, net);
  }

  function setRowFlexRun(row: SelectedRow, name: string) {
    const run = (flexBySubject[row.subjectId] ?? []).find((r) => r.name === name);
    const first = run ? placementsFor(run)[0] : undefined;
    const numPairs = first?.pairs?.length ?? first?.xyzPairs?.length ?? 0;
    patch(row.id, {
      name,
      kind: undefined,
      eegNet: first && first.value !== OPTIMIZED ? first.value : undefined,
      pairs: first?.pairs,
      xyzPairs: first?.xyzPairs,
      currents: defaultCurrents(numPairs),
    });
  }

  function setRowFreehand(row: SelectedRow, name: string) {
    const config = (freehandBySubject[row.subjectId] ?? []).find((c) => c.name === name);
    const pairs: [[number, number, number], [number, number, number]][] = [];
    for (let i = 0; config && i + 1 < config.electrode_positions.length; i += 2) {
      const a = config.electrode_positions[i]!;
      const b = config.electrode_positions[i + 1]!;
      pairs.push([[a.x, a.y, a.z], [b.x, b.y, b.z]]);
    }
    patch(row.id, { name, kind: undefined, eegNet: undefined, pairs: undefined, xyzPairs: pairs, currents: defaultCurrents(pairs.length) });
  }

  function addRow() {
    const last = rows[rows.length - 1];
    const seedSubject = last?.subjectId || usable[0] || "";
    // A new row starts from the settings the user configured last — assembling a batch is
    // configuring one job and adding the next one like it — and from the built-ins before that.
    onRowsChange([...rows, { ...emptyRow(seedSubject, "montage", editorNet), settings: seedSettings }]);
  }

  function duplicateRow(row: SelectedRow) {
    const at = rows.findIndex((r) => r.id === row.id);
    const copy = { ...row, id: newRowId() };
    onRowsChange([...rows.slice(0, at + 1), copy, ...rows.slice(at + 1)]);
    setActiveId(copy.id);
  }

  function removeRow(id: string) {
    if (activeId === id) setActiveId(null);
    onRowsChange(rows.filter((r) => r.id !== id));
  }

  /** A brand-new montage always starts as a 2-pair draft; adding pairs makes it multi-polar. */
  function startNewMontage() {
    setFreehandOpen(false);
    setEditing(emptyDraft());
  }

  function startNewFreehand() {
    setEditing(null);
    setFreehandOpen(true);
  }

  const draftKind = editing ? inferMontageKind(editing.pairs.length) : "uni_polar";

  /* ------------------------------------------------------------------ Preview */

  const activeRow = rows.find((r) => r.id === activeId) ?? null;
  const activeNet = activeRow?.eegNet;
  const activeName = activeRow?.name;
  const activePairs = activeRow?.pairs;
  const activeSource = activeRow?.source ?? null;
  const activeSubject = activeRow?.subjectId;
  // A free-hand row's positions are already resolved on the row (`xyzPairs`), so a saved set can be
  // drawn on the subject's scalp without a second request — "what will this job actually stimulate"
  // answered by the same click that selects it. Serialised as the dependency because `xyzPairs` is
  // a fresh nested array on every patch.
  const activeXyz = activeSource === "freehand" ? JSON.stringify(activeRow?.xyzPairs ?? []) : "";
  useEffect(() => {
    if (activeXyz && activeName && activeSubject) {
      const pairs = JSON.parse(activeXyz) as [[number, number, number], [number, number, number]][];
      return onPreviewChange?.({
        name: activeName,
        subject: activeSubject,
        positions: pairs.flat().map(([x, y, z]) => ({ x, y, z })),
      });
    }
    onPreviewChange?.(
      activeNet && activeName && activePairs?.length ? { net: activeNet, name: activeName, subject: activeSubject, pairs: activePairs } : null,
    );
  }, [activeNet, activeName, activePairs, activeSubject, activeXyz, onPreviewChange]);
  useEffect(() => {
    onActiveSourceChange?.(activeSource);
  }, [activeSource, onActiveSourceChange]);

  /* ------------------------------------------------------------------ Geometry */

  const [tableWidth, setTableWidth] = useState(0);
  const [storedColumns, setStoredColumns] = useState<StoredColumns>(() =>
    readStoredColumns(typeof window === "undefined" ? undefined : window.localStorage),
  );
  const tableBox = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = tableBox.current;
    if (!node) return;
    setTableWidth(node.clientWidth);
    const ro = new ResizeObserver(() => setTableWidth(node.clientWidth));
    ro.observe(node);
    return () => ro.disconnect();
  }, [montages.data, availableNets.length]);
  const cols = useMemo(() => resolveColumnWidths(tableWidth, storedColumns), [tableWidth, storedColumns]);
  const setColumn = useCallback((key: ColumnKey, next: number) => {
    setStoredColumns((prev) => {
      const merged = { ...prev, [key]: Math.max(COLUMN_MIN[key], Math.round(next)) };
      writeStoredColumns(typeof window === "undefined" ? undefined : window.localStorage, merged);
      return merged;
    });
  }, []);

  /** Up/Down moves the active row — the one the 3-D pane is drawing. */
  function onTableKeyDown(e: React.KeyboardEvent<HTMLTableElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    if (rows.length === 0) return;
    e.preventDefault();
    const at = rows.findIndex((r) => r.id === activeId);
    const next = e.key === "ArrowDown" ? Math.min(rows.length - 1, at + 1) : Math.max(0, (at === -1 ? 0 : at) - 1);
    setActiveId(rows[next]?.id ?? null);
    const row = e.currentTarget.querySelectorAll<HTMLElement>("tbody tr[data-job-row]")[next];
    row?.focus();
  }

  /* ------------------------------------------------------------------ Cells */

  const subjectItems = useMemo(
    () =>
      subjects.map((s) => ({
        id: s.id,
        label: s.id,
        reason: s.blockedReason,
        // Blocked subjects are LISTED with their reason and cannot be picked — the row's own
        // version of the subject grammar's J3 rule, which is why this is a `SelectionPicker` and
        // not a `Select` whose options carry no explanation.
        disabled: !!s.blockedReason,
      })),
    [subjects],
  );

  function montageOptions(net: string | undefined) {
    return montagesOf(net).map((m) => ({
      value: montageOptionValue(m.kind, m.name),
      label: `${m.name} · ${polarityLabel(m.kind)}`,
    }));
  }

  function netsForSubject(subjectId: string): string[] {
    const own = subjectNets[subjectId] ?? [];
    return own.length > 0 ? own : availableNets;
  }

  /**
   * Column 3 — **what you pick first**, whatever the source: a montage row's EEG net, a flex row's
   * run, a free-hand row's saved set. It sits next to Source because it is the choice the rest of
   * the row depends on (maintainer, 2026-09-06: a flex row used to leave this column empty and put
   * its run two columns further right, past a gap).
   */
  function renderPickCell(row: SelectedRow) {
    if (row.source === "montage") {
      const nets = netsForSubject(row.subjectId);
      return (
        <Select
          value={nets.find((n) => n === row.eegNet)}
          onValueChange={(v) => setRowNet(row, v)}
          options={nets.map((n) => ({ value: n, label: netStem(n) }))}
          placeholder="Choose a net"
          aria-label="EEG net"
        />
      );
    }
    if (row.source === "flex") {
      const runs = flexBySubject[row.subjectId] ?? [];
      return (
        <Select
          value={runs.some((r) => r.name === row.name) ? row.name : undefined}
          onValueChange={(v) => setRowFlexRun(row, v)}
          options={runs.map((r) => ({ value: r.name, label: r.name }))}
          placeholder={runs.length === 0 ? "No flex runs" : "Choose a run"}
          disabled={runs.length === 0}
          aria-label="Flex run"
        />
      );
    }
    const configs = freehandBySubject[row.subjectId] ?? [];
    return (
      <Select
        value={configs.some((c) => c.name === row.name) ? row.name : undefined}
        onValueChange={(v) => setRowFreehand(row, v)}
        options={configs.map((c) => ({ value: c.name, label: c.name }))}
        placeholder={configs.length === 0 ? "No free-hand sets" : "Choose a set"}
        disabled={configs.length === 0}
        aria-label="Free-hand configuration"
      />
    );
  }

  /**
   * Column 4 — **what qualifies that pick**: the montage of the chosen net, or the placement the
   * chosen flex run is simulated in. A free-hand set carries its own coordinates and has no net to
   * qualify it, so the cell is empty rather than holding a control that would do nothing.
   */
  function renderQualifierCell(row: SelectedRow) {
    if (row.source === "montage") {
      const options = montageOptions(row.eegNet);
      const selected = row.name && row.kind ? montageOptionValue(row.kind, row.name) : undefined;
      return (
        // The polarity chip is on line 2, beside the pairs it describes: the select gets the whole
        // column, which is what a montage name needs to be readable (maintainer's "Ch…").
        <Select
          value={options.some((option) => option.value === selected) ? selected : undefined}
          onValueChange={(v) => setRowMontage(row, v)}
          options={options}
          placeholder={!row.eegNet ? "Choose a net first" : options.length === 0 ? "No montages available" : "Choose a montage"}
          disabled={options.length === 0}
          aria-label="Montage"
        />
      );
    }
    if (row.source !== "flex" || !row.name) return null;
    /*
     * A flex row's placement: the optimiser's own coordinates, or the EEG net its electrodes are
     * mapped onto — **one** select, listing every net the subject has (the server maps on demand),
     * not only the nets the run was pre-mapped to.
     *
     * Why one control and not an `Optimised · Map to net` pair plus a net select: measured in the
     * app at 1280 with the default pane the four line-1 columns share 512px, and the two controls
     * together need 290px in a column that can be ~176px at most without starving the run name
     * beside it. Splitting them across the two lines instead made a flex job a line taller than a
     * montage job. One select keeps every name whole and every job exactly two lines.
     */
    const options = placementsForRow(row);
    const hasOptimised = options.some((o) => o.value === OPTIMIZED);
    const nets = netsForSubject(row.subjectId);
    const choices = [
      ...(hasOptimised ? [{ value: OPTIMIZED, label: "Optimised (XYZ)" }] : []),
      ...nets.map((n) => ({ value: n, label: netStem(n) })),
    ];
    const current = row.eegNet ? nets.find((n) => netStem(n) === netStem(row.eegNet!)) : OPTIMIZED;
    return (
      <Select
        value={choices.some((c) => c.value === current) ? current : undefined}
        onValueChange={(v) => (v === OPTIMIZED ? setRowPlacementMode(row, "optimised") : void mapRowToNet(row, v))}
        options={choices}
        placeholder="Placement"
        aria-label="Placement"
      />
    );
  }

  const catalogMontageOf = (row: SelectedRow): CatalogMontage | null =>
    row.source === "montage" && row.eegNet && row.kind && row.name
      ? { net: row.eegNet, kind: row.kind, name: row.name, pairs: row.pairs ?? [] }
      : null;

  /**
   * The two content columns hold different controls per source, so their headers name what most of
   * the table's rows actually put there rather than a neutral word ("Selection", "Placement / net")
   * that would be wrong for every row in a single-source table. The columns themselves never move —
   * their widths come from the resolver — so only the words change.
   */
  const headings = useMemo(() => headingsFor(rows.map((r) => r.source)), [rows]);

  const loading = montages.isPending;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      {usable.length === 0 && subjects.length > 0 && (
        <Callout kind="warning">No subject in this project has a head model — a simulation cannot run yet.</Callout>
      )}
      {loading && <Skeleton height={160} />}
      {montages.error && <Callout kind="danger">Could not load montages.</Callout>}
      {montages.data && availableNets.length === 0 && (
        <EmptyState icon={<Plus size={24} />} message="No EEG nets available in this project." />
      )}
      {montages.data && availableNets.length > 0 && (
        <div className="data-table-container" ref={tableBox} data-testid="sim-jobs-table-container">
          {/* Fixed geometry: an explicit `<colgroup>` plus `table-layout: fixed` (simulator-page.css).
              Nothing a user does to one ROW — its subject, its source, its montage, its polarity —
              may move a cell in another; only a deliberate drag of a header boundary changes a
              COLUMN. The widths come from `resolveColumnWidths`, which always sums to the
              container, so the table cannot scroll sideways at any pane width. */}
          <table className="data-table montage-table sim-jobs-table" onKeyDown={onTableKeyDown} data-testid="sim-jobs-table">
            <colgroup>
              <col style={{ width: tableWidth ? cols.subject : "16%" }} />
              <col style={{ width: tableWidth ? cols.source : "18%" }} />
              <col style={{ width: tableWidth ? cols.net : "30%" }} />
              <col style={{ width: tableWidth ? cols.montage : "26%" }} />
              <col style={{ width: tableWidth ? cols.actions : "10%" }} />
            </colgroup>
            <thead>
              <tr>
                <th data-column="subject">
                  Subject
                  <ColumnHandle label="Subject" width={cols.subject} onResize={(w) => setColumn("subject", w)} />
                </th>
                <th data-column="source">
                  Source
                  <ColumnHandle label="Source" width={cols.source} onResize={(w) => setColumn("source", w)} />
                </th>
                <th data-column="net">
                  {headings.pick}
                  <ColumnHandle label={headings.pick} width={cols.net} onResize={(w) => setColumn("net", w)} />
                </th>
                <th data-column="montage">
                  {headings.qualifier}
                  <ColumnHandle label={headings.qualifier} width={cols.montage} onResize={(w) => setColumn("montage", w)} />
                </th>
                <th data-column="actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const montage = catalogMontageOf(row);
                const active = activeId === row.id;
                // A click on a control is that control's, not the row's.
                const claim = (e: React.MouseEvent) => {
                  if ((e.target as HTMLElement).closest("button, input, [role='combobox'], [role='dialog']")) return;
                  setActiveId(row.id);
                };
                return (
                  <Fragment key={row.id}>
                    <tr
                      data-job-row={row.id}
                      data-subject={row.subjectId || undefined}
                      data-source={row.source}
                      data-montage-row={row.name || ""}
                      data-polarity={row.kind ?? ""}
                      data-runnable={isRunnableRow(row) ? "true" : "false"}
                      data-active={active ? "true" : undefined}
                      aria-selected={active}
                      tabIndex={0}
                      onClick={claim}
                      onDoubleClick={() => onEditSettings?.(row)}
                      onFocus={() => setActiveId(row.id)}
                    >
                      <td data-cell="subject">
                        <SelectionPicker
                          mode="single"
                          label="Subject"
                          items={subjectItems}
                          value={row.subjectId ? [row.subjectId] : []}
                          onChange={(v) => v[0] && setRowSubject(row, v[0])}
                          placeholder="Subject"
                          headers={{ label: "Subject", reason: "Why not" }}
                          hideBulk
                          idPrefix={`job-subject-${row.id}`}
                          triggerTestId={`job-subject-${row.id}`}
                        />
                      </td>
                      <td data-cell="source">
                        <Select
                          value={row.source}
                          onValueChange={(v) => setRowSource(row, v as MontageSource)}
                          options={SOURCE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                          aria-label="Source"
                        />
                      </td>
                      <td data-cell="net">{renderPickCell(row)}</td>
                      <td data-cell="montage">{renderQualifierCell(row)}</td>
                      {/* One actions cell for the whole two-line job, its buttons on line 1. */}
                      <td data-cell="actions" className="montage-actions" rowSpan={2}>
                        <div className="montage-actions-row">
                        <IconButton
                          aria-label={`Job settings ${rows.indexOf(row) + 1}`}
                          title="Electrodes, conductivity and output fields for this job"
                          icon={<SlidersHorizontal size={14} />}
                          data-customised={isCustomised(row) ? "true" : undefined}
                          onClick={() => onEditSettings?.(row)}
                        />
                        <IconButton
                          aria-label={`Duplicate job ${rows.indexOf(row) + 1}`}
                          icon={<Copy size={14} />}
                          onClick={() => duplicateRow(row)}
                        />
                        {montage && (
                          <IconButton
                            aria-label={`Edit ${montage.name}`}
                            icon={<Pencil size={14} />}
                            onClick={() => {
                              setNetChoice(montage.net);
                              setFreehandOpen(false);
                              setEditing({ name: montage.name, pairs: montage.pairs.map((p) => [p[0], p[1]] as ElectrodePair), savedAs: montage.kind });
                            }}
                          />
                        )}
                        <IconButton aria-label={`Remove job ${rows.indexOf(row) + 1}`} icon={<X size={14} />} onClick={() => removeRow(row.id)} />
                        </div>
                      </td>
                    </tr>
                    {/*
                      Line 2: what the job will DO, on the same column grid as line 1 — the
                      polarity chip under Source, the placement and the electrode pairs under EEG
                      net, the currents right-aligned to the Montage column's right edge. An
                      unconfigured job says so in one muted line, at the same height, so picking a
                      montage never makes the table jump (maintainer, 2026-09-06).
                    */}
                    <tr data-job-detail={row.id} data-active={active ? "true" : undefined} onClick={claim}>
                      {row.name ? (
                        <>
                          <td data-cell="detail-pad" />
                          <td data-cell="polarity">
                            {/* Polarity is implied by the channel count; kept as a quiet label, not
                                a chip competing with the per-channel colours. */}
                            <span className="job-polarity">{polarityLabel(row.kind ?? inferMontageKind(rowPairCount(row)))}</span>
                          </td>
                          <td colSpan={2} data-cell="detail">
                            <div className="job-line2" data-cell="pairs">
                              {customChip(row, defaults)}
                              <ChannelList row={row} onChange={(currents) => patch(row.id, { currents })} />
                            </div>
                          </td>
                        </>
                      ) : (
                        <td colSpan={4} data-cell="detail">
                          <div className="job-line2">
                            {customChip(row, defaults)}
                            <span className="job-line2-empty">Pairs and currents appear once a montage is chosen</span>
                          </div>
                        </td>
                      )}
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={availableNets.length === 0} onClick={addRow}>
          Add job
        </Button>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={!editorNet} onClick={startNewMontage}>
          New montage
        </Button>
        <Button variant="secondary" icon={<Plus size={14} />} disabled={usable.length === 0} onClick={startNewFreehand}>
          New placement
        </Button>
        <Button variant="secondary" onClick={() => { setSelectedDefinitions([]); setManageOpen(true); }}>Manage montages</Button>
      </div>

      {freehandOpen && <FreehandEditor subjects={usable} onClose={() => setFreehandOpen(false)} />}

      {editing && (
        <Card>
          <CardHeader title={editing.name ? `Edit montage "${editing.name}"` : "New montage"} />
          <CardBody>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <Field label="EEG net">
                <Select
                  value={editorNet}
                  onValueChange={setNetChoice}
                  options={availableNets.map((n) => ({ value: n, label: n }))}
                  placeholder="Choose a net"
                />
              </Field>
              <Field label="Montage name" required>
                <TextInput value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="e.g. F3_F4" />
              </Field>
              {/* Polarity is a readout, not a choice: it follows from the pairs picked. */}
              <Field label="Polarity">
                <div data-testid="montage-draft-polarity" className="montage-cell" style={{ minHeight: 28 }}>
                  <span className="montage-chip-slot" style={{ "--slot": "40px" } as React.CSSProperties}>
                    <span className="chip chip-neutral">{polarityLabel(draftKind)}</span>
                  </span>
                  <span className="field-help">
                    {editing.pairs.length} pairs · {draftKind === "uni_polar" ? "uni-polar" : "multi-polar"}
                  </span>
                </div>
              </Field>
              <Field label="Electrode pairs" help="Selected from the net's electrode labels.">
                {netElectrodes.isFetching && <Skeleton height={32} />}
                {!netElectrodes.isFetching && (
                  <ElectrodePairsEditor
                    mode="net"
                    electrodes={netElectrodes.data ?? []}
                    pairs={editing.pairs}
                    onPairsChange={(pairs) => setEditing({ ...editing, pairs })}
                    pairStep={2}
                    freehandPairs={[]}
                    onFreehandPairsChange={() => {}}
                  />
                )}
                {!isValidPairCount(editing.pairs.length) && (
                  <span className="field-error">Use exactly 2 pairs (standard TI) or 4 or more pairs (multi-channel mTI).</span>
                )}
              </Field>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-2)" }}>
                {/* Deleting a catalog entry is an act on the CATALOG, so it lives with the editor
                    rather than in a job row's actions. Only offered for a montage that exists. */}
                {editing.savedAs && editorNet && (
                  <Button
                    variant="secondary"
                    icon={<Trash2 size={14} />}
                    style={{ marginRight: "auto" }}
                    onClick={() => setDeleteTarget({ net: editorNet, kind: editing.savedAs as MontageKind, name: editing.name.trim(), pairs: [] })}
                  >
                    Delete montage
                  </Button>
                )}
                <Button variant="secondary" onClick={() => setEditing(null)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={saveMontage.isPending}
                  disabled={
                    !editorNet ||
                    !editing.name.trim() ||
                    editing.pairs.some((p) => !p[0] || !p[1]) ||
                    !isValidPairCount(editing.pairs.length)
                  }
                  onClick={() => {
                    if (!editorNet) return;
                    // An edit that changed a montage's polarity moves buckets: delete the old
                    // entry so the same name cannot exist in both.
                    if (editing.savedAs && editing.savedAs !== draftKind) {
                      void deleteMontage(editorNet, editing.savedAs, editing.name.trim()).catch(() => undefined);
                    }
                    saveMontage.mutate({ net: editorNet, kind: draftKind, name: editing.name.trim(), pairs: editing.pairs });
                  }}
                >
                  Save montage
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      <Dialog open={manageOpen} onOpenChange={setManageOpen} title="Manage montages"
        description="Delete saved definitions. Existing simulation results are kept."
        footer={<><Button variant="destructive" disabled={selectedDefinitions.length === 0 || deletingDefinitions} onClick={() => setBulkTargets([...selectedDefinitions])}>{removeSelected.isPending ? "Deleting…" : `Delete selected (${selectedDefinitions.length})`}</Button><Button onClick={() => setManageOpen(false)}>Done</Button></>}>
        <div data-testid="montage-manager-scroll" style={{ display: "grid", alignContent: "start", gap: "var(--space-4)", height: "min(440px, 55vh)", overflowY: "auto", paddingRight: "var(--space-2)" }}>
          <section>
            <h3 className="card-title">Montages</h3>
            <Field label="EEG net"><Select aria-label="Managed EEG net" value={managementNet ?? ""} options={availableNets.map((net) => ({ value: net, label: net }))} disabled={deletingDefinitions} onValueChange={(value) => { setManagedNet(value); setSelectedDefinitions([]); }} /></Field>
            {montages.isPending ? <p>Loading montages…</p> : montages.isError ? <p>Could not load montages.</p> : montagesOf(managementNet).length === 0 ? <p className="field-help">No saved montages for this net.</p> : montagesOf(managementNet).map((montage) => (
              <div key={`${montage.kind}:${montage.name}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)", paddingBlock: "var(--space-2)" }}>
                <Checkbox aria-label={`Select montage ${montage.name}`} label={`${montage.name} · ${polarityLabel(montage.kind)}`} disabled={deletingDefinitions} checked={selectedDefinitions.some((item) => definitionKey(item) === definitionKey({ type: "montage", ...montage }))} onCheckedChange={(checked) => selectDefinition({ type: "montage", ...montage }, checked)} />
                <IconButton aria-label={`Delete montage ${montage.name}`} icon={<Trash2 size={16} />} disabled={deletingDefinitions} onClick={() => setDeleteTarget(montage)} />
              </div>
            ))}
          </section>
          <section>
            <h3 className="card-title">Freehand placements</h3>
            <Field label="Subject"><Select aria-label="Managed placement subject" value={managementSubject ?? ""} options={usable.map((subject) => ({ value: subject, label: subject }))} disabled={deletingDefinitions} onValueChange={(value) => { setManagedSubject(value); setSelectedDefinitions([]); }} /></Field>
            {freehandQueries[usable.indexOf(managementSubject ?? "")]?.isPending ? <p>Loading placements…</p> : freehandQueries[usable.indexOf(managementSubject ?? "")]?.isError ? <p>Could not load placements.</p> : (freehandBySubject[managementSubject ?? ""] ?? []).length === 0 ? <p className="field-help">No saved placements for this subject.</p> : (freehandBySubject[managementSubject ?? ""] ?? []).map((placement) => (
              <div key={placement.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)", paddingBlock: "var(--space-2)" }}>
                <Checkbox aria-label={`Select placement ${placement.name}`} label={placement.name} disabled={deletingDefinitions} checked={selectedDefinitions.some((item) => definitionKey(item) === definitionKey({ type: "placement", subject: managementSubject!, name: placement.name }))} onCheckedChange={(checked) => selectDefinition({ type: "placement", subject: managementSubject!, name: placement.name }, checked)} />
                <IconButton aria-label={`Delete placement ${placement.name}`} icon={<Trash2 size={16} />} disabled={deletingDefinitions} onClick={() => setDeletePlacement({ subject: managementSubject!, name: placement.name })} />
              </div>
            ))}
          </section>
        </div>
      </Dialog>
      <AlertDialog open={bulkTargets !== null} onOpenChange={(open) => !open && setBulkTargets(null)}
        title={`Delete ${bulkTargets?.length ?? 0} selected definitions?`}
        description="This removes the selected saved montages and placements. Existing simulation results are kept."
        confirmLabel="Delete selected" onConfirm={() => { if (bulkTargets) { setEditing(null); removeSelected.mutate(bulkTargets); } }} />
      <AlertDialog open={deletePlacement !== null} onOpenChange={(open) => !open && setDeletePlacement(null)}
        title={`Delete placement "${deletePlacement?.name ?? ""}"?`}
        description="This removes the saved freehand definition for this subject. Existing simulation results are kept."
        confirmLabel="Delete placement" onConfirm={() => { if (deletePlacement) removePlacement.mutate(deletePlacement); }} />

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title={`Delete montage "${deleteTarget?.name ?? ""}"?`}
        description="This removes the montage definition for this net. Simulations already run from it are unaffected."
        confirmLabel="Delete montage"
        onConfirm={() => {
          if (!deleteTarget) return;
          setEditing(null);
          removeMontage.mutate(deleteTarget);
        }}
      />
    </div>
  );
}
