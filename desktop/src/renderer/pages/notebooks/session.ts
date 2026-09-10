/**
 * One open notebook: the parsed document, its kernel, and what is running.
 *
 * Adapted from SUNA's `notebook/session.ts` (github.com/idossha/SUNA), GPL-3.0,
 * by the same author. The flux shape is SUNA's and so is every comment that
 * explains *why* it is that shape; what changed is the transport — SUNA invokes
 * Electron IPC channels against a kernel on the user's own machine, and this
 * calls `/api/kernels` and opens `/ws/kernels/{id}` against the container.
 *
 * Sessions live at MODULE scope. A kernel holds state a researcher spent
 * minutes building — a loaded leadfield, a fitted model — and leaving the page
 * must not silently throw that away. React sees only the version counter below;
 * the notebook itself is MUTATED in place, because the output objects arriving
 * from the kernel are exactly the objects that get written back to the .ipynb,
 * and copying them around is how they get mangled.
 */
import { create } from "zustand";
import { wsUrl } from "../../api/client";
import type { CompleteReply } from "./completion";
import {
  createNotebook,
  interruptKernel,
  readNotebook,
  restartKernel,
  saveNotebook,
  startKernel,
  stopKernel,
} from "./api";
import {
  cellKey,
  convertCell,
  isCodeCell,
  newCell,
  retireCellKey,
  type Cell,
  type CellType,
  type CodeCell,
  type Notebook,
  type Output,
} from "./notebook";

export type KernelStatus = "off" | "starting" | "idle" | "busy" | "dead";

export interface KernelFault {
  code: string;
  message: string;
}

export interface NotebookMeta {
  loading: boolean;
  loadError: string | null;
  dirty: boolean;
  kernelStatus: KernelStatus;
  /** Display name from the kernelspec, e.g. "SimNIBS + TI-Toolbox". */
  kernelName: string | null;
  kernelError: KernelFault | null;
  /** Cell keys currently executing or queued, in submission order. */
  running: string[];
  /** Bumped on every in-place mutation so React re-renders. */
  version: number;
}

const EMPTY_META: NotebookMeta = {
  loading: true,
  loadError: null,
  dirty: false,
  kernelStatus: "off",
  kernelName: null,
  kernelError: null,
  running: [],
  version: 0,
};

interface MetaState {
  byName: Record<string, NotebookMeta>;
}

const useMetaStore = create<MetaState>(() => ({ byName: {} }));

/** The meta store itself, so a unit test can read `dirty` without a React tree. */
export const useNotebookMetaStoreForTests = useMetaStore;

export function useNotebookMeta(name: string): NotebookMeta {
  return useMetaStore((s) => s.byName[name] ?? EMPTY_META);
}

function patch(name: string, changes: Partial<NotebookMeta>): void {
  useMetaStore.setState((s) => ({
    byName: { ...s.byName, [name]: { ...(s.byName[name] ?? EMPTY_META), ...changes } },
  }));
}

function bump(name: string, changes: Partial<NotebookMeta> = {}): void {
  const current = useMetaStore.getState().byName[name] ?? EMPTY_META;
  patch(name, { ...changes, version: current.version + 1 });
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

interface KernelEvent {
  type: string;
  reqId?: string;
  matches?: string[];
  cursorStart?: number;
  cursorEnd?: number;
  metadata?: Record<string, unknown>;
  found?: boolean;
  text?: string;
  output?: Output;
  executionCount?: number | null;
  state?: string;
  status?: string;
  code?: string;
  message?: string;
  kernel?: { displayName?: string };
  wait?: boolean;
}

/** How long autosave waits after the last edit. Long enough not to fight typing. */
const AUTOSAVE_MS = 1500;

export class Session {
  readonly name: string;
  nb: Notebook | null = null;
  refs = 0;
  /** Readable so the unload path can name it; written only in here. */
  kernelId: string | null = null;
  private socket: WebSocket | null = null;
  private starting: Promise<boolean> | null = null;
  /** reqId → the cell that asked for it. */
  private inflight = new Map<string, CodeCell>();
  private reqSeq = 0;
  /** reqId → the promise waiting on a complete/inspect round trip. */
  private queries = new Map<string, (event: KernelEvent) => void>();
  private autosave: ReturnType<typeof setTimeout> | null = null;
  private saving: Promise<boolean> | null = null;
  /** A save queued behind the in-flight one because edits arrived mid-flight. */
  private followUp: Promise<boolean> | null = null;
  /** Bumped by every edit. What "the document has moved on" is measured against. */
  private revision = 0;
  /** The highest revision a PUT has actually written. */
  private savedRevision = 0;
  /** The last deleted cell and where it was; one slot, like Jupyter's. */
  private deleted: { cell: Cell; index: number } | null = null;

  constructor(name: string) {
    this.name = name;
  }

  async load(): Promise<void> {
    patch(this.name, { loading: true, loadError: null });
    try {
      const { content } = await readNotebook(this.name);
      this.nb = content;
      bump(this.name, { loading: false, loadError: null, dirty: false });
    } catch (error) {
      patch(this.name, { loading: false, loadError: message(error) });
    }
  }

  async save(): Promise<boolean> {
    if (this.nb === null) return false;
    if (this.autosave !== null) {
      clearTimeout(this.autosave);
      this.autosave = null;
    }
    // One save at a time: two PUTs of the same mutable document racing is how
    // the older one wins and the author's last edit disappears. But *joining*
    // the in-flight one is not enough — an edit made while it was in flight is
    // not in the body it already sent, so a caller that joined it would be told
    // the notebook is written when the newest text never left the app. Queue a
    // second write instead, and let flush() wait on that.
    if (this.saving !== null) {
      if (this.followUp === null) {
        const chained = this.saving.then(() =>
          this.revision > this.savedRevision ? this.save() : true,
        );
        this.followUp = chained;
        void chained.finally(() => {
          if (this.followUp === chained) this.followUp = null;
        });
      }
      return this.followUp;
    }
    const revision = this.revision;
    const document = this.nb;
    this.saving = saveNotebook(this.name, document)
      .then(() => {
        this.savedRevision = revision;
        // Only the revision this PUT carried is clean. A later edit keeps the
        // notebook dirty, so the queued write above still has a reason to run.
        if (this.revision === revision) patch(this.name, { dirty: false });
        return true;
      })
      .catch((error: unknown) => {
        patch(this.name, { loadError: null });
        bump(this.name, { dirty: true });
        console.warn("[notebook] save failed:", message(error));
        return false;
      })
      .finally(() => {
        this.saving = null;
      });
    return this.saving;
  }

  /**
   * Write a cell's source. The only path by which a cell's text changes.
   *
   * The cell is mutated rather than replaced, because it is the same object
   * that gets sent back as this notebook's document — and it goes through the
   * session rather than through the component that rendered it, so the thing
   * that owns the document is the thing that changes it.
   */
  setCellSource(cell: Cell, source: string): void {
    cell.source = source;
    this.markDirty();
    bump(this.name);
  }

  /** A save is queued or in flight — what a navigation guard has to wait on. */
  get pendingSave(): boolean {
    return this.autosave !== null || this.saving !== null || this.followUp !== null;
  }

  /**
   * Write now if anything is outstanding, and wait for it.
   *
   * Called when the page is left. Autosave already runs 1.5 s after the last
   * keystroke, so the window where a notebook is unsaved is small — but
   * "small" is not "none", and navigating away inside it used to lose the
   * edit. Flushing beats prompting: there is nothing for the author to decide,
   * and a modal asking them to confirm a save the app was going to do anyway
   * is a question with one answer.
   */
  async flush(): Promise<boolean> {
    const meta = useMetaStore.getState().byName[this.name] ?? EMPTY_META;
    if (!meta.dirty && !this.pendingSave) return true;
    return this.save();
  }

  markDirty(): void {
    this.revision += 1;
    bump(this.name, { dirty: true });
    if (this.autosave !== null) clearTimeout(this.autosave);
    this.autosave = setTimeout(() => {
      this.autosave = null;
      void this.save();
    }, AUTOSAVE_MS);
  }

  /** Start the kernel if it is not up. Concurrent callers share one start. */
  async ensureKernel(): Promise<boolean> {
    if (this.kernelId !== null && this.socket !== null) return true;
    if (this.starting !== null) return this.starting;
    this.starting = this.startKernel().finally(() => {
      this.starting = null;
    });
    return this.starting;
  }

  private async startKernel(): Promise<boolean> {
    patch(this.name, { kernelStatus: "starting", kernelError: null });
    try {
      const kernel = await startKernel();
      this.kernelId = kernel.id;
      await this.connect(kernel.id);
      patch(this.name, { kernelStatus: "idle", kernelName: kernel.displayName });
      return true;
    } catch (error) {
      // The server's own code travels in `detail`, and it is what the fault
      // panel switches on — "no kernelspec in this container" and "two kernels
      // are already running" want very different sentences.
      const detail = (error as { body?: { detail?: KernelFault } }).body?.detail;
      patch(this.name, {
        kernelStatus: "dead",
        kernelError:
          detail && typeof detail.code === "string"
            ? detail
            : { code: "start-failed", message: message(error) },
      });
      return false;
    }
  }

  private connect(kernelId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(wsUrl(`/ws/kernels/${encodeURIComponent(kernelId)}`));
      const failed = (): void => reject(new Error("The kernel socket would not open."));
      socket.onopen = () => {
        this.socket = socket;
        socket.onerror = null;
        resolve();
      };
      socket.onerror = failed;
      socket.onmessage = (event) => {
        try {
          this.onKernelEvent(JSON.parse(String(event.data)) as KernelEvent);
        } catch {
          // Not protocol. Logged rather than forwarded, so one bad frame
          // cannot break the stream.
          console.warn("[notebook] unparseable kernel frame");
        }
      };
      socket.onclose = () => {
        if (this.socket !== socket) return;
        this.socket = null;
        this.kernelId = null;
        this.inflight.clear();
        patch(this.name, { kernelStatus: "dead", running: [] });
      };
    });
  }

  private onKernelEvent(event: KernelEvent): void {
    switch (event.type) {
      case "ready":
        patch(this.name, {
          kernelStatus: "idle",
          kernelName: event.kernel?.displayName ?? null,
          kernelError: null,
        });
        return;
      case "status":
        // 'starting' from the kernel is a restart; keep the pill honest.
        patch(this.name, {
          kernelStatus:
            event.state === "busy"
              ? "busy"
              : event.state === "starting"
                ? "starting"
                : event.state === "dead"
                  ? "dead"
                  : "idle",
        });
        return;
      case "complete":
      case "inspect": {
        // A query is a request/response pair, not a stream: the one waiter
        // resolves and the entry goes, so a slow kernel cannot leave a
        // completion popup attached to a keystroke three edits ago.
        const settle = event.reqId === undefined ? undefined : this.queries.get(event.reqId);
        if (typeof settle === "function") {
          this.queries.delete(event.reqId as string);
          settle(event);
        }
        return;
      }
      case "fatal":
        patch(this.name, {
          kernelStatus: "dead",
          kernelError: { code: event.code ?? "fatal", message: event.message ?? "Kernel failed" },
        });
        return;
      default:
        break;
    }

    const cell = event.reqId === undefined ? undefined : this.inflight.get(event.reqId);
    if (cell === undefined) return;

    if (event.type === "input") {
      cell.execution_count = event.executionCount ?? null;
      this.markDirty();
      bump(this.name);
    } else if (event.type === "output" && event.output !== undefined) {
      cell.outputs.push(event.output);
      this.markDirty();
      bump(this.name);
    } else if (event.type === "clear") {
      cell.outputs.length = 0;
      this.markDirty();
      bump(this.name);
    } else if (event.type === "reply") {
      this.inflight.delete(event.reqId as string);
      const key = cellKey(cell);
      const meta = useMetaStore.getState().byName[this.name] ?? EMPTY_META;
      bump(this.name, { running: meta.running.filter((k) => k !== key) });
      this.markDirty();
    }
  }

  /**
   * One request/response round trip to the kernel, with a deadline.
   *
   * Completion runs on a keystroke, so it must never hang the editor: a kernel
   * busy in a FEM loop will not answer, and after `timeoutMs` the caller gets
   * `null` and CodeMirror simply shows nothing. Resolving with null beats
   * rejecting — a completion that did not arrive is not an error to report.
   */
  private query(op: "complete" | "inspect", code: string, cursorPos: number, timeoutMs = 2500): Promise<KernelEvent | null> {
    if (this.socket === null || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.resolve(null);
    }
    const reqId = `q${(this.reqSeq += 1)}`;
    return new Promise<KernelEvent | null>((resolve) => {
      const timer = setTimeout(() => {
        this.queries.delete(reqId);
        resolve(null);
      }, timeoutMs);
      this.queries.set(reqId, (event) => {
        clearTimeout(timer);
        resolve(event);
      });
      this.socket?.send(JSON.stringify({ id: reqId, op, code, cursorPos }));
    });
  }

  /**
   * What could follow the cursor, from the kernel's live namespace.
   *
   * The kernel is only asked when one is already up. Starting an interpreter
   * because someone pressed a key would be a several-second stall and a
   * container resource taken without asking.
   */
  async complete(code: string, cursorPos: number): Promise<CompleteReply | null> {
    if (this.socket === null) return null;
    const event = await this.query("complete", code, cursorPos);
    if (event === null || !Array.isArray(event.matches)) return null;
    return {
      matches: event.matches,
      cursorStart: event.cursorStart ?? cursorPos,
      cursorEnd: event.cursorEnd ?? cursorPos,
      metadata: event.metadata,
    };
  }

  /** The signature/docstring for the name under the cursor, or null. */
  async inspect(code: string, cursorPos: number): Promise<string | null> {
    if (this.socket === null) return null;
    const event = await this.query("inspect", code, cursorPos);
    if (event === null || event.found !== true) return null;
    const text = typeof event.text === "string" ? event.text : "";
    return text === "" ? null : text;
  }

  /** True when a kernel is up: what the editor checks before asking it. */
  get connected(): boolean {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }

  async runCell(cell: CodeCell): Promise<void> {
    if (!(await this.ensureKernel())) return;
    if (this.socket === null) return;
    const key = cellKey(cell);
    const meta = useMetaStore.getState().byName[this.name] ?? EMPTY_META;
    // A cell already in flight is not queued twice: two runs would push their
    // outputs into the same array and the cell would show both.
    if (meta.running.includes(key)) return;
    cell.outputs.length = 0;
    cell.execution_count = null;
    const reqId = `r${(this.reqSeq += 1)}`;
    this.inflight.set(reqId, cell);
    bump(this.name, { running: [...meta.running, key] });
    this.socket.send(JSON.stringify({ id: reqId, op: "execute", code: cellText(cell) }));
  }

  /**
   * Run every code cell top to bottom. The kernel executes its queue in order,
   * so this submits them all and lets it sequence them — which is also what
   * makes an interrupt cancel the REST of the run.
   */
  async runAll(): Promise<void> {
    if (this.nb === null) return;
    if (!(await this.ensureKernel())) return;
    for (const cell of this.nb.cells) {
      if (isCodeCell(cell)) await this.runCell(cell);
    }
  }

  // ---- editing the cell list ----------------------------------------------
  //
  // Every one of these mutates `nb.cells` in place and bumps the version, the
  // same contract the kernel events above follow: the array being edited IS the
  // array that gets sent back, so what the author sees and what the file will
  // say cannot drift.

  cellAt(index: number): Cell | null {
    return this.nb?.cells[index] ?? null;
  }

  /** Insert an empty cell at `index` and return its key, for selection. */
  insertCell(index: number, cellType: CellType): string | null {
    if (this.nb === null) return null;
    const at = Math.max(0, Math.min(index, this.nb.cells.length));
    const cell = newCell(cellType, this.nb);
    this.nb.cells.splice(at, 0, cell);
    this.markDirty();
    bump(this.name);
    return cellKey(cell);
  }

  /**
   * Delete a cell, keeping it and its position so `undoDelete` can put it back
   * — Jupyter's `dd` / `z`, and the reason `dd` is safe on a bare keystroke at
   * all. Returns the key to select next.
   */
  deleteCell(index: number): string | null {
    if (this.nb === null) return null;
    const cell = this.nb.cells[index];
    if (cell === undefined) return null;
    this.nb.cells.splice(index, 1);
    this.deleted = { cell, index };
    // A notebook with no cells has nowhere to type; Jupyter refills it too.
    if (this.nb.cells.length === 0) this.nb.cells.push(newCell("code", this.nb));
    const next = this.nb.cells[Math.min(index, this.nb.cells.length - 1)];
    this.markDirty();
    bump(this.name);
    return next === undefined ? null : cellKey(next);
  }

  undoDelete(): string | null {
    if (this.nb === null || this.deleted === null) return null;
    const { cell, index } = this.deleted;
    this.deleted = null;
    this.nb.cells.splice(Math.min(index, this.nb.cells.length), 0, cell);
    this.markDirty();
    bump(this.name);
    return cellKey(cell);
  }

  /** Move one cell by `delta` places. True when it actually moved. */
  moveCell(index: number, delta: number): boolean {
    if (this.nb === null) return false;
    const to = index + delta;
    if (index < 0 || to < 0 || index >= this.nb.cells.length || to >= this.nb.cells.length) {
      return false;
    }
    const [cell] = this.nb.cells.splice(index, 1);
    this.nb.cells.splice(to, 0, cell as Cell);
    this.markDirty();
    bump(this.name);
    return true;
  }

  duplicateCell(index: number): string | null {
    if (this.nb === null) return null;
    const cell = this.nb.cells[index];
    if (cell === undefined) return null;
    const copy = JSON.parse(JSON.stringify(cell)) as Cell;
    // The copy is a NEW cell: it may not carry the original's id, and a
    // duplicated code cell has not been run.
    delete copy.id;
    const minted = newCell(cell.cell_type, this.nb);
    if (minted.id !== undefined) copy.id = minted.id;
    if (copy.cell_type === "code") {
      (copy as CodeCell).outputs = [];
      (copy as CodeCell).execution_count = null;
    }
    this.nb.cells.splice(index + 1, 0, copy);
    this.markDirty();
    bump(this.name);
    return cellKey(copy);
  }

  setCellType(index: number, cellType: CellType): void {
    if (this.nb === null) return;
    const cell = this.nb.cells[index];
    if (cell === undefined || cell.cell_type === cellType) return;
    // The converted cell is the same object, so its React key would survive —
    // but its editor must not: retiring the key remounts it.
    convertCell(cell, cellType);
    retireCellKey(cell);
    this.markDirty();
    bump(this.name);
  }

  clearAllOutputs(): void {
    if (this.nb === null) return;
    for (const cell of this.nb.cells) {
      if (isCodeCell(cell)) {
        cell.outputs.length = 0;
        cell.execution_count = null;
      }
    }
    this.markDirty();
    bump(this.name);
  }

  async interrupt(): Promise<void> {
    if (this.kernelId !== null) await interruptKernel(this.kernelId);
  }

  /**
   * Restart the kernel, or start one when there is none.
   *
   * The fallback is the point. A kernel that died — reaped for idling, or lost
   * with the socket — leaves `kernelId` null, and the first version returned
   * silently: the button was enabled, said Restart, and did nothing at all. The
   * state the user is in when they press it is exactly the state with no kernel
   * to restart.
   */
  async restart(): Promise<void> {
    this.inflight.clear();
    patch(this.name, { running: [], kernelStatus: "starting", kernelError: null });
    if (this.kernelId === null || !this.connected) {
      await this.shutdown();
      await this.ensureKernel();
      return;
    }
    try {
      const kernel = await restartKernel(this.kernelId);
      patch(this.name, { kernelStatus: "idle", kernelName: kernel.displayName });
    } catch (error) {
      // The kernel is gone on the server's side too; start a fresh one rather
      // than leaving the pill spinning on "starting…" forever.
      const detail = (error as { body?: { detail?: KernelFault } }).body?.detail;
      if (detail?.code === "no-such-kernel") {
        await this.shutdown();
        await this.ensureKernel();
        return;
      }
      patch(this.name, {
        kernelStatus: "dead",
        kernelError: detail ?? { code: "op-failed", message: message(error) },
      });
    }
  }

  /** Shut the kernel down but keep the document and its outputs. */
  async shutdown(): Promise<void> {
    const id = this.kernelId;
    this.kernelId = null;
    this.inflight.clear();
    this.socket?.close();
    this.socket = null;
    patch(this.name, { kernelStatus: "off", kernelName: null, running: [] });
    if (id !== null) await stopKernel(id);
  }
}

/** A cell's source as one string. Local so `notebook.ts` stays dependency-free. */
function cellText(cell: Cell): string {
  return typeof cell.source === "string" ? cell.source : cell.source.join("");
}

const sessions = new Map<string, Session>();

/**
 * The session for a notebook, created and loaded on first use. Callers release
 * their reference on unmount; the session and its kernel survive that, because
 * navigating away is not a reason to lose a loaded dataset.
 */
export function acquireNotebook(name: string): { session: Session; release: () => void } {
  let session = sessions.get(name);
  if (session === undefined) {
    session = new Session(name);
    sessions.set(name, session);
    void session.load();
  }
  session.refs += 1;
  const owner = session;
  return {
    session: owner,
    release: () => {
      owner.refs -= 1;
    },
  };
}

export function getNotebookSession(name: string): Session | null {
  return sessions.get(name) ?? null;
}

/** Drop a session and its kernel — the notebook is being deleted. */
export async function releaseNotebook(name: string): Promise<void> {
  const session = sessions.get(name);
  sessions.delete(name);
  useMetaStore.setState((s) => {
    const byName = { ...s.byName };
    delete byName[name];
    return { byName };
  });
  if (session) await session.shutdown();
}

/** Create a notebook on the server and pre-load its session. */
export async function newNotebook(name: string): Promise<string> {
  const created = await createNotebook(name);
  const session = new Session(created.name);
  session.nb = created.content;
  sessions.set(created.name, session);
  patch(created.name, { loading: false, loadError: null, dirty: false, version: 1 });
  return created.name;
}

/** Store an imported document under `name` and pre-load its session. */
export async function importNotebook(name: string, content: Notebook): Promise<string> {
  const created = await createNotebook(name, content);
  const session = new Session(created.name);
  session.nb = created.content;
  sessions.set(created.name, session);
  patch(created.name, { loading: false, loadError: null, dirty: false, version: 1 });
  return created.name;
}

/** Every session that currently holds a notebook. */
export function openSessions(): Session[] {
  return [...sessions.values()];
}

/** Flush every unsaved notebook. Resolves false when one could not be written. */
export async function flushAllNotebooks(): Promise<boolean> {
  const results = await Promise.all(openSessions().map((session) => session.flush()));
  return results.every(Boolean);
}

/**
 * Shut every kernel down. Called when the window is going away.
 *
 * A kernel is a full SimNIBS Python interpreter and the container allows two,
 * so one leaked by a closed window is half the budget gone until the 30-minute
 * reaper notices. `keepalive` is what makes this work at all during `unload`:
 * an ordinary fetch is cancelled with the document, and `Session.shutdown`'s
 * awaited DELETE never leaves the machine.
 */
export function shutdownAllKernelsOnUnload(): void {
  for (const session of openSessions()) {
    const id = session.kernelId;
    if (id === null) continue;
    try {
      void fetch(`/api/kernels/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "same-origin",
        keepalive: true,
      });
    } catch {
      // Nothing to do on the way out; the server's idle reaper is the backstop.
    }
  }
}
