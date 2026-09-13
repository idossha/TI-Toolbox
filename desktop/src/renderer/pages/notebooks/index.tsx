/**
 * Notebooks — a Jupyter environment inside TI-Toolbox.
 *
 * The kernel is the container's SimNIBS Python with `tit` importable, started
 * by the server (`tit/server/kernels.py`) and driven over `/ws/kernels/{id}`.
 * So "the TI-Toolbox environment is automatically loaded" is not a claim this
 * page makes in prose — it is what the kernel *is*, and a new notebook's first
 * code cell already imports `tit` and prints this project's root to show it.
 *
 * The notebook half is ported from SUNA (github.com/idossha/SUNA,
 * `apps/desktop/src/renderer/src/notebook/NotebookTab.tsx`), GPL-3.0, by the
 * same author, and so is the modal editing:
 *
 *   Editing is modal, as it is in Jupyter: the selected cell is either being
 *   TYPED IN (edit mode — the editor inside it holds focus) or being ACTED ON
 *   (command mode — the scroller holds focus, and single letters insert, delete
 *   and re-type cells). Escape and Enter cross between them. Modal editing is
 *   not decoration here: it is the only way `d`, `a` and `m` can be bare
 *   keystrokes without eating the author's typing.
 *
 * What is new is the left pane: SUNA opens a notebook as a dock tab from its
 * file explorer, and TI-Toolbox has no explorer, so the notebook list is part
 * of the page.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, FilePlus, RotateCw, Trash2, Upload } from "lucide-react";
import type { PageDef } from "../../app/registry";
import { usePageActive } from "../../app/pageActivity";
import { Button, Cluster, EmptyState, PageLayout, Stack, StatusDot, type SemanticKind } from "../../ui";
import { deleteNotebook, listNotebooks, type NotebookEntry } from "./api";
import { CellView, type CellCommands } from "./CellView";
import { NotebookSettings } from "./SettingsPopover";
import { useNotebookPrefs } from "./settings";
import { cellKey, isCodeCell, type CellType, type Notebook } from "./notebook";
import {
  acquireNotebook,
  flushAllNotebooks,
  importNotebook,
  newNotebook,
  releaseNotebook,
  shutdownAllKernelsOnUnload,
  useNotebookMeta,
  type KernelStatus,
  type Session,
} from "./session";
// KaTeX ships its own stylesheet and its own woff2 faces; both are bundled by
// Vite, so a rendered equation needs no network. See markdown.ts.
import "katex/dist/katex.min.css";
import "./notebooks.css";

const STATUS_LABEL: Record<KernelStatus, string> = {
  off: "no kernel",
  starting: "starting…",
  idle: "idle",
  busy: "busy",
  dead: "not running",
};

const STATUS_KIND: Record<KernelStatus, SemanticKind> = {
  off: "neutral",
  starting: "warning",
  idle: "success",
  busy: "accent",
  dead: "danger",
};

function modified(entry: NotebookEntry): string {
  return new Date(entry.modified * 1000).toLocaleString();
}

/** A name the server will accept, or null. The same rule, said in one place. */
function proposeName(raw: string): string | null {
  const trimmed = raw.trim().replace(/\.ipynb$/i, "");
  return /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}$/.test(trimmed) ? trimmed : null;
}

function NotebookListPane({
  notebooks,
  open,
  onOpen,
  onNew,
  onImport,
  onDelete,
  busy,
}: {
  notebooks: NotebookEntry[];
  open: string | null;
  onOpen: (name: string) => void;
  onNew: () => void;
  onImport: (event: ChangeEvent<HTMLInputElement>) => void;
  onDelete: (name: string) => void;
  busy: boolean;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="nb-list" data-testid="nb-list">
      <Cluster gap={2} className="nb-list__actions">
        <Button size="sm" onClick={onNew} disabled={busy} data-testid="nb-new">
          <FilePlus size={13} /> New
        </Button>
        <Button size="sm" variant="ghost" onClick={() => fileRef.current?.click()} disabled={busy}>
          <Upload size={13} /> Import .ipynb
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".ipynb,application/json"
          className="nb-list__file"
          data-testid="nb-import"
          onChange={onImport}
        />
      </Cluster>
      {notebooks.length === 0 ? (
        <p className="nb-list__empty">
          No notebooks yet. A new one opens with <code>tit</code> already imported and this
          project&rsquo;s subjects listed.
        </p>
      ) : (
        <ul className="nb-list__items">
          {notebooks.map((entry) => (
            <li key={entry.name}>
              <button
                className={`nb-list__item${entry.name === open ? " nb-list__item--open" : ""}`}
                data-testid="nb-list-item"
                data-example={entry.example ? "1" : undefined}
                onClick={() => onOpen(entry.name)}
              >
                <span className="nb-list__name">
                  {entry.example ? entry.name.slice("examples/".length) : entry.name}
                </span>
                <span className="nb-list__meta">
                  {/* The example is reference material the app wrote, so it is
                      labelled rather than dated: its mtime says nothing a
                      reader wants. */}
                  {entry.example ? "example" : modified(entry)}
                </span>
              </button>
              <button
                className="nb-list__delete"
                title={`Delete ${entry.name}`}
                aria-label={`Delete ${entry.name}`}
                onClick={() => onDelete(entry.name)}
              >
                <Trash2 size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Toolbar({ session, name }: { session: Session; name: string }) {
  const meta = useNotebookMeta(name);
  const busy = meta.kernelStatus === "busy";
  return (
    <div className="nb-toolbar" data-testid="nb-toolbar">
      <Button size="sm" variant="ghost" onClick={() => session.insertCell(Number.MAX_SAFE_INTEGER, "code")}>
        + Code
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => session.insertCell(Number.MAX_SAFE_INTEGER, "markdown")}
      >
        + Markdown
      </Button>
      <span className="nb-toolbar__divider" />
      <Button size="sm" onClick={() => void session.runAll()} data-testid="nb-run-all">
        Run all
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => void session.interrupt()}
        disabled={!busy}
        data-testid="nb-interrupt"
      >
        Interrupt
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => void session.restart()}
        disabled={meta.kernelStatus === "off"}
        title="Restart the kernel — every variable is lost"
        data-testid="nb-restart"
      >
        Restart
      </Button>
      <Button size="sm" variant="ghost" onClick={() => session.clearAllOutputs()}>
        Clear outputs
      </Button>
      <span className="nb-toolbar__spacer" />
      <NotebookSettings />
      <Button
        size="sm"
        variant="ghost"
        onClick={() => void session.save()}
        disabled={!meta.dirty}
        data-testid="nb-save"
      >
        {meta.dirty ? "Save" : "Saved"}
      </Button>
      <button
        className={`nb-toolbar__kernel nb-toolbar__kernel--${meta.kernelStatus}`}
        data-testid="nb-kernel-status"
        data-state={meta.kernelStatus}
        // The pill is the status AND the recovery. A dead kernel is the one
        // state where a user needs to do something, and making them find a
        // separate button for it is a step with no decision in it.
        title={
          meta.kernelStatus === "dead" || meta.kernelStatus === "off"
            ? "Start a kernel"
            : "Restart the kernel — every variable is lost"
        }
        onClick={() => void session.restart()}
        disabled={meta.kernelStatus === "starting"}
      >
        <StatusDot kind={STATUS_KIND[meta.kernelStatus]} pulse={meta.kernelStatus === "starting"} />
        {meta.kernelName ?? "Kernel"} · {STATUS_LABEL[meta.kernelStatus]}
        {(meta.kernelStatus === "dead" || meta.kernelStatus === "off") && (
          <RotateCw size={11} aria-hidden />
        )}
      </button>
    </div>
  );
}

/**
 * The kernel could not start, and the message is the server's own — it names
 * the container's state (no kernelspec, no jupyter_client, two kernels already
 * running), which is the only thing that tells the user what to do next.
 */
function KernelFault({ name, session }: { name: string; session: Session }) {
  const meta = useNotebookMeta(name);
  if (meta.kernelError === null) return null;
  return (
    <div className="nb-fault" data-testid="nb-fault">
      <strong className="nb-fault__title">No kernel</strong>
      <span className="nb-fault__message">{meta.kernelError.message}</span>
      <Button size="sm" onClick={() => void session.ensureKernel()}>
        Try again
      </Button>
    </div>
  );
}

function NotebookView({ name }: { name: string }) {
  const meta = useNotebookMeta(name);
  const prefs = useNotebookPrefs((state) => state.prefs);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const cellsRef = useRef<HTMLDivElement>(null);
  /** `d` waiting for its second `d`; cleared by any other key. */
  const pendingD = useRef(false);
  // The component is keyed by the notebook name, so this runs exactly once per
  // open notebook — which is why the session can be read straight through
  // during render rather than arriving later through a ref.
  const [handle] = useState(() => acquireNotebook(name));
  const session = handle.session;
  useEffect(() => handle.release, [handle]);

  // Command mode IS "the scroller has focus", so leaving edit mode focuses it.
  // Done in an effect rather than inside the callbacks that set the state: the
  // DOM node is only guaranteed to exist after the commit that set it.
  useEffect(() => {
    if (!editing && selected !== null) cellsRef.current?.focus({ preventScroll: true });
  }, [editing, selected]);

  const toCommandMode = useCallback((): void => {
    setEditing(false);
  }, []);

  const select = useCallback((key: string | null, edit = false): void => {
    setSelected(key);
    setEditing(edit);
  }, []);

  const cells = session.nb?.cells ?? [];
  const selectedIndex = selected === null ? -1 : cells.findIndex((c) => cellKey(c) === selected);
  const index = selectedIndex === -1 ? 0 : selectedIndex;

  const runSelected = useCallback(
    (after: "stay" | "next" | "insert"): void => {
      const s = session;
      if (s.nb === null) return;
      const cell = s.nb.cells[index];
      if (cell === undefined) return;
      if (isCodeCell(cell)) void s.runCell(cell);
      // "Running" a markdown cell is rendering it, i.e. leaving edit mode.
      setEditing(false);

      if (after === "stay") {
        select(cellKey(cell), isCodeCell(cell));
        return;
      }
      if (after === "insert" || s.nb.cells[index + 1] === undefined) {
        const key = s.insertCell(index + 1, "code");
        if (key !== null) select(key, true);
        return;
      }
      const next = s.nb.cells[index + 1];
      if (next !== undefined) select(cellKey(next));
    },
    [index, select, session],
  );

  const moveSelected = useCallback(
    (delta: number): void => {
      const s = session;
      if (s.nb === null) return;
      if (!s.moveCell(index, delta)) return;
      const moved = s.nb.cells[index + delta];
      if (moved !== undefined) setSelected(cellKey(moved));
    },
    [index, session],
  );

  // Passed to every cell by value. SUNA hands its cells a *getter*, because a
  // CodeMirror keymap is built once and would otherwise close over the first
  // render's callbacks forever; a textarea's onKeyDown is read fresh on every
  // render, so the indirection would buy nothing here.
  const commands = useMemo<CellCommands>(
    () => ({
      run: runSelected,
      move: moveSelected,
      toCommandMode,
      save: () => void session.save(),
    }),
    [runSelected, moveSelected, toCommandMode, session],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent): void => {
      const s = session;
      if (s.nb === null) return;
      const target = event.target as HTMLElement;
      // An editor that has focus has already acted on these keys through its
      // own keymap; handling them again here would run the cell twice — and,
      // worse, would let command mode see ordinary typing.
      //
      // THE defect this exists for: the guard used to test `tagName ===
      // "TEXTAREA"`, which was true while a cell was a textarea and false the
      // moment it became a CodeMirror (a contenteditable `div`). Typing
      // `print(...)` then delivered `r` to command mode, which re-typed the
      // cell as **raw** and destroyed the editor mid-word. The test is now
      // "did this come from inside an editor", which is what was always meant.
      if (target.closest(".cm-editor") !== null || target.tagName === "TEXTAREA") return;

      const mod = event.metaKey || event.ctrlKey;
      const stop = (): void => {
        event.preventDefault();
        event.stopPropagation();
      };

      if (event.key === "Enter" && (event.shiftKey || mod || event.altKey)) {
        stop();
        runSelected(event.altKey ? "insert" : event.shiftKey ? "next" : "stay");
        return;
      }
      if (mod && event.shiftKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
        stop();
        moveSelected(event.key === "ArrowUp" ? -1 : 1);
        return;
      }
      if (mod && event.key.toLowerCase() === "s") {
        stop();
        void s.save();
        return;
      }
      if (event.key === "Escape") {
        if (!editing) return;
        stop();
        toCommandMode();
        return;
      }

      // ---- command mode ------------------------------------------------
      if (mod || event.altKey) return;
      const wasPendingD = pendingD.current;
      pendingD.current = false;

      switch (event.key) {
        case "Enter":
          stop();
          if (selected !== null) select(selected, true);
          return;
        case "j":
        case "ArrowDown": {
          stop();
          const next = s.nb.cells[Math.min(index + 1, s.nb.cells.length - 1)];
          if (next !== undefined) select(cellKey(next));
          return;
        }
        case "k":
        case "ArrowUp": {
          stop();
          const prev = s.nb.cells[Math.max(index - 1, 0)];
          if (prev !== undefined) select(cellKey(prev));
          return;
        }
        case "a": {
          stop();
          const key = s.insertCell(index, "code");
          if (key !== null) select(key);
          return;
        }
        case "b": {
          stop();
          const key = s.insertCell(index + 1, "code");
          if (key !== null) select(key);
          return;
        }
        case "m":
        case "y":
        case "r": {
          stop();
          const kind: CellType = event.key === "m" ? "markdown" : event.key === "y" ? "code" : "raw";
          s.setCellType(index, kind);
          const same = s.nb.cells[index];
          if (same !== undefined) setSelected(cellKey(same));
          return;
        }
        case "d":
          stop();
          if (!wasPendingD) {
            pendingD.current = true;
            // A lone `d` is not a command; forget it rather than arming a
            // delete that fires minutes later on an unrelated keystroke.
            window.setTimeout(() => {
              pendingD.current = false;
            }, 900);
            return;
          }
          select(s.deleteCell(index));
          return;
        case "z":
          stop();
          select(s.undoDelete());
          return;
        case "D":
          stop();
          select(s.duplicateCell(index));
          return;
        default:
      }
    },
    [editing, index, moveSelected, runSelected, select, selected, session, toCommandMode],
  );

  if (meta.loadError !== null) {
    return <div className="nb-empty">Could not open {name}: {meta.loadError}</div>;
  }
  if (meta.loading || session.nb === null) {
    return <div className="nb-empty">Opening {name}…</div>;
  }

  return (
    <div
      className="nb"
      data-testid="nb-notebook"
      data-notebook={name}
      // `version` is the whole re-render signal: the notebook is mutated in
      // place, so nothing below would change identity on its own.
      data-nb-version={meta.version}
      // One variable, set once on the root: the editor reads it through its own
      // theme compartment and the outputs through the stylesheet, so code and
      // the traceback it produced are never two different sizes.
      style={{ "--nb-font-size": `${prefs.fontSize}px` } as React.CSSProperties}
      onKeyDown={onKeyDown}
    >
      <Toolbar session={session} name={name} />
      <KernelFault name={name} session={session} />
      <div className="nb__cells" ref={cellsRef} tabIndex={0}>
        {session.nb.cells.map((cell, cellIndex) => {
          const key = cellKey(cell);
          return (
            <div key={key} data-cell-key={key}>
              <CellView
                cell={cell}
                index={cellIndex}
                session={session}
                running={meta.running.includes(key)}
                selected={selected === key}
                editing={selected === key && editing}
                onSelect={() => setSelected(key)}
                onEdit={() => {
                  setSelected(key);
                  setEditing(true);
                }}
                onMove={(delta) => {
                  if (session.moveCell(cellIndex, delta)) setSelected(key);
                }}
                onDelete={() => select(session.deleteCell(cellIndex))}
                commands={commands}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NotebooksPage() {
  const queryClient = useQueryClient();
  const active = usePageActive();
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const notebooks = useQuery({ queryKey: ["notebooks"], queryFn: listNotebooks });
  const example = (notebooks.data?.notebooks ?? []).find((entry) => entry.example);

  // ⌘S at the page level, not only inside a cell. The editor binds it too, but
  // focus is often on the toolbar or the notebook list when an author reaches
  // for it, and a save shortcut that depends on where the caret happens to be
  // is a save shortcut nobody trusts.
  useEffect(() => {
    if (!active) return;
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "s") return;
      if ((event.target as HTMLElement | null)?.closest(".cm-editor")) return; // the cell has it
      event.preventDefault();
      void flushAllNotebooks();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active]);

  // Leaving the page writes what is outstanding rather than asking about it.
  // Autosave runs 1.5 s after the last keystroke, so the unsaved window is
  // short — but navigating inside it used to lose the edit, and there is
  // nothing here for the author to decide.
  useEffect(() => {
    if (active) return;
    void flushAllNotebooks();
  }, [active]);

  // Closing the window: flush, then hand every kernel back. A kernel is a full
  // SimNIBS interpreter and the container allows two, so one leaked by a closed
  // window is half the budget gone until the 30-minute reaper notices.
  useEffect(() => {
    function onUnload() {
      void flushAllNotebooks();
      shutdownAllKernelsOnUnload();
    }
    window.addEventListener("pagehide", onUnload);
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("pagehide", onUnload);
      window.removeEventListener("beforeunload", onUnload);
    };
  }, []);

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["notebooks"] });
  }, [queryClient]);

  const create = useMutation({
    mutationFn: async () => {
      const existing = new Set((notebooks.data?.notebooks ?? []).map((n) => n.name));
      let n = 1;
      while (existing.has(`notebook-${n}.ipynb`)) n += 1;
      return newNotebook(`notebook-${n}`);
    },
    onSuccess: async (name) => {
      setError(null);
      setOpen(name);
      await refresh();
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
  });

  const onImport = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      const proposed = proposeName(file.name);
      if (proposed === null) {
        setError(`${file.name} is not a usable notebook name.`);
        return;
      }
      try {
        const content = JSON.parse(await file.text()) as Notebook;
        const name = await importNotebook(proposed, content);
        setError(null);
        setOpen(name);
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [refresh],
  );

  const onDelete = useCallback(
    async (name: string) => {
      try {
        await deleteNotebook(name);
        await releaseNotebook(name);
        if (open === name) setOpen(null);
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [open, refresh],
  );

  return (
    <PageLayout variant="browse" className="nb-page">
      <div className="nb-page__split">
        <aside className="nb-page__side">
          <NotebookListPane
            notebooks={notebooks.data?.notebooks ?? []}
            open={open}
            onOpen={setOpen}
            onNew={() => create.mutate()}
            onImport={(e) => void onImport(e)}
            onDelete={(name) => void onDelete(name)}
            busy={create.isPending}
          />
          {error !== null && (
            <p className="nb-page__error" data-testid="nb-error">
              {error}
            </p>
          )}
        </aside>
        <section className="nb-page__main">
          {open === null ? (
            <Stack gap={3} align="center" className="nb-page__blank">
              <EmptyState
                icon={<BookOpen size={20} />}
                message="No notebook open. Cells run on the container's SimNIBS Python, so tit, simnibs, numpy, nibabel, pandas and matplotlib are importable with nothing to install. For a worked example — a real field summarised, plotted and tabulated — open examples/getting-started."
                actionLabel={example === undefined ? "New notebook" : "Open the example"}
                onAction={() => (example === undefined ? create.mutate() : setOpen(example.name))}
              />
            </Stack>
          ) : (
            <NotebookView key={open} name={open} />
          )}
        </section>
      </div>
    </PageLayout>
  );
}

const page: PageDef = {
  id: "notebooks",
  title: "Notebooks",
  purpose: "Run Jupyter notebooks on the container's SimNIBS Python, with tit already importable.",
  navGroup: "workflow",
  order: 65,
  icon: BookOpen,
  Component: NotebooksPage,
  enabled: true,
};

export default page;
