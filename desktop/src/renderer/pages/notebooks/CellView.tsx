/**
 * Ported from SUNA (github.com/idossha/SUNA,
 * `apps/desktop/src/renderer/src/notebook/CellView.tsx`), GPL-3.0, by the same
 * author, including the editor: a code cell is a **CodeMirror 6** with Python
 * highlighting and kernel-backed completion (`editor.ts`).
 *
 * It was a `<textarea>` first, to avoid the dependency. That was the wrong
 * trade and the maintainer said so: a textarea cannot colour Python, cannot
 * indent a block and has nowhere to put a completion popup, and "easier for
 * users to develop" is the whole point of the page. A markdown cell is still a
 * textarea — there is nothing to highlight in prose, and its rendered form is
 * where the reading happens.
 *
 * Selection and the modal edit/command distinction belong to the notebook, not
 * to a cell: every keystroke that acts on the cell LIST (insert, delete, move,
 * change type) has to be able to see its neighbours. So a cell is told whether
 * it is selected and whether it is being edited, and reports back gestures — it
 * decides neither.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, type JSX, type KeyboardEvent } from "react";
import { ChevronDown, ChevronUp, Play, X } from "lucide-react";
import { Compartment, EditorState, EditorView, baseExtensions, completionExtensions, keymap, prefExtensions, type CompletionSource } from "./editor";
import { Prec } from "@codemirror/state";
import { dismissSignature, requestSignature, signatureExtensions } from "./signature";
import { renderMarkdown } from "./markdown";
import { cellText, type Cell, type CodeCell } from "./notebook";
import { OutputList } from "./Outputs";
import type { Session } from "./session";
import { useNotebookPrefs } from "./settings";

export interface CellCommands {
  /** Run the selected cell; then stay on it, step to the next, or insert. */
  run: (after: "stay" | "next" | "insert") => void;
  move: (delta: number) => void;
  /** Leave the editor: the cell stays selected, the keyboard acts on it. */
  toCommandMode: () => void;
  save: () => void;
}

export interface CellProps {
  cell: Cell;
  index: number;
  session: Session;
  running: boolean;
  selected: boolean;
  /** Selected AND in edit mode: the editor is live and holds focus. */
  editing: boolean;
  onSelect: () => void;
  onEdit: () => void;
  commands: CellCommands;
  onMove: (delta: number) => void;
  onDelete: () => void;
}

/** `[ ]` while never run, `[*]` while running, `[7]` once it has. */
function executionLabel(cell: CodeCell, running: boolean): string {
  if (running) return "[*]";
  return cell.execution_count === null ? "[ ]" : `[${cell.execution_count}]`;
}

/** The per-cell controls: the mouse path to what the keyboard also does. */
function CellActions({ onMove, onDelete }: Pick<CellProps, "onMove" | "onDelete">): JSX.Element {
  return (
    <div className="nb-cell__actions">
      <button className="nb-cell__action" title="Move up (⌘⇧↑)" aria-label="Move cell up" onClick={() => onMove(-1)}>
        <ChevronUp size={12} />
      </button>
      <button
        className="nb-cell__action"
        title="Move down (⌘⇧↓)"
        aria-label="Move cell down"
        onClick={() => onMove(1)}
      >
        <ChevronDown size={12} />
      </button>
      <button
        className="nb-cell__action nb-cell__action--delete"
        title="Delete this cell (dd)"
        aria-label="Delete cell"
        onClick={onDelete}
      >
        <X size={12} />
      </button>
    </div>
  );
}

/**
 * The cell keys, installed INTO the editor at the highest precedence.
 *
 * A notebook shortcut has to work both while the author is typing in a cell and
 * while they are not. SUNA solves that with one keymap installed in two places;
 * here the textarea's own handler is that second place, and the page's handler
 * covers command mode. The list is the same either way.
 */
function editorKeys(event: KeyboardEvent<HTMLTextAreaElement>, commands: CellCommands): void {
  const mod = event.metaKey || event.ctrlKey;
  if (event.key === "Enter" && (event.shiftKey || mod || event.altKey)) {
    event.preventDefault();
    event.stopPropagation();
    commands.run(event.altKey ? "insert" : event.shiftKey ? "next" : "stay");
    return;
  }
  if (mod && event.shiftKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
    event.preventDefault();
    event.stopPropagation();
    commands.move(event.key === "ArrowUp" ? -1 : 1);
    return;
  }
  if (mod && event.key.toLowerCase() === "s") {
    event.preventDefault();
    event.stopPropagation();
    commands.save();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    commands.toCommandMode();
  }
}

/** A textarea that is exactly as tall as its text, so no cell scrolls inside. */
function useAutoSize(ref: React.RefObject<HTMLTextAreaElement | null>, text: string): void {
  useLayoutEffect(() => {
    const node = ref.current;
    if (node === null) return;
    node.style.height = "auto";
    node.style.height = `${node.scrollHeight}px`;
  }, [ref, text]);
}

/** Markdown source while a prose cell is being edited. Nothing to highlight. */
function MarkdownEditor({
  cell,
  session,
  editing,
  commands,
  label,
}: {
  cell: Cell;
  session: Session;
  editing: boolean;
  commands: CellCommands;
  label: string;
}): JSX.Element {
  const ref = useRef<HTMLTextAreaElement>(null);
  const text = cellText(cell);
  useAutoSize(ref, text);

  useEffect(() => {
    const node = ref.current;
    if (node === null) return;
    if (editing && document.activeElement !== node) node.focus();
    else if (!editing && document.activeElement === node) node.blur();
  }, [editing]);

  return (
    <textarea
      ref={ref}
      className="nb-cell__editor nb-cell__editor--plain"
      spellCheck={false}
      aria-label={label}
      value={text}
      onChange={(event) => session.setCellSource(cell, event.target.value)}
      onKeyDown={(event) => editorKeys(event, commands)}
    />
  );
}

/**
 * A code cell's CodeMirror.
 *
 * Built ONCE per cell and then reconfigured. Rebuilding it on a re-render would
 * throw away the author's cursor, selection and undo history on every keystroke
 * — the notebook re-renders on every kernel output, so that is not a rare case.
 * Preferences reach it through compartments, and the notebook's commands
 * through a ref the keymap reads at keystroke time.
 */
function CodeEditor({
  cell,
  session,
  editing,
  commands,
  label,
  onFocus,
}: {
  cell: Cell;
  session: Session;
  editing: boolean;
  commands: CellCommands;
  label: string;
  /** The editor took focus: the notebook is now in edit mode on this cell. */
  onFocus: () => void;
}): JSX.Element {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const compartments = useRef({
    prefs: new Compartment(),
    completion: new Compartment(),
    signature: new Compartment(),
  });
  const prefs = useNotebookPrefs((state) => state.prefs);

  // Read at keystroke time: the keymap is installed once, and would otherwise
  // close over the first render's callbacks forever. Written in an effect
  // rather than during render — the keymap only fires after a commit, so it
  // never needs a value the current render has not finished producing.
  const latest = useRef({ commands, session, cell, onFocus });
  useEffect(() => {
    latest.current = { commands, session, cell, onFocus };
  }, [commands, session, cell, onFocus]);

  const completionSource = useCallback(
    (): CompletionSource => ({
      connected: latest.current.session.connected,
      complete: (code, pos) => latest.current.session.complete(code, pos),
      inspect: (code, pos) => latest.current.session.inspect(code, pos),
    }),
    [],
  );
  const signatureSource = useCallback(
    () => ({
      connected: latest.current.session.connected,
      inspect: (code: string, pos: number) => latest.current.session.inspect(code, pos),
    }),
    [],
  );

  useEffect(() => {
    const parent = host.current;
    if (parent === null) return;
    const {
      prefs: prefsSlot,
      completion: completionSlot,
      signature: signatureSlot,
    } = compartments.current;

    const editor = new EditorView({
      parent,
      state: EditorState.create({
        doc: cellText(latest.current.cell),
        extensions: [
          // Escape is bound ABOVE the notebook's own Escape, and it is the one
          // key here that has to be: a visible signature tooltip is dismissed
          // first, and only an Escape with nothing to dismiss leaves edit mode.
          // Otherwise the first Escape would do both at once, and the author
          // would lose the cell they were typing in to close a tooltip.
          Prec.highest(
            keymap.of([
              { key: "Escape", run: dismissSignature },
              {
                key: "Shift-Tab",
                run: (view) => requestSignature(view, signatureSource),
              },
            ]),
          ),
          // The notebook's own keys come next, at the highest precedence
          // CodeMirror binds ⇧↵ and ⌘↵ itself, and a cell that inserts a
          // newline instead of running is the whole gesture broken.
          keymap.of([
            { key: "Shift-Enter", run: () => (latest.current.commands.run("next"), true) },
            { key: "Mod-Enter", run: () => (latest.current.commands.run("stay"), true) },
            { key: "Alt-Enter", run: () => (latest.current.commands.run("insert"), true) },
            { key: "Mod-Shift-ArrowUp", run: () => (latest.current.commands.move(-1), true) },
            { key: "Mod-Shift-ArrowDown", run: () => (latest.current.commands.move(1), true) },
            { key: "Mod-s", run: () => (latest.current.commands.save(), true), preventDefault: true },
            { key: "Escape", run: () => (latest.current.commands.toCommandMode(), true) },
          ]),
          prefsSlot.of(prefExtensions(prefs)),
          completionSlot.of(completionExtensions(prefs.autocomplete, completionSource)),
          signatureSlot.of(signatureExtensions(prefs.signatureHelp, signatureSource)),
          baseExtensions(),
          // THE defect this exists for. Edit mode is notebook state, and the
          // editor is what actually holds focus — so the editor is what must
          // report it. Relying on React's `onFocus` bubbling out of
          // CodeMirror's contenteditable left `editing` false, and the next
          // re-render (which every keystroke causes, because a keystroke
          // changes the document) then BLURRED the editor mid-word. The rest
          // of the word fell through to command mode, where `r` re-typed the
          // cell as raw and the editor vanished under the author's cursor.
          EditorView.domEventHandlers({
            focus: () => {
              latest.current.onFocus();
              return false;
            },
          }),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return;
            latest.current.session.setCellSource(
              latest.current.cell,
              update.state.doc.toString(),
            );
          }),
          EditorView.contentAttributes.of({ "aria-label": label }),
        ],
      }),
    });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
    // Mounted once per cell. `prefs` is applied through the compartment below,
    // not by rebuilding — see the note above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const editor = view.current;
    if (editor === null) return;
    editor.dispatch({
      effects: [
        compartments.current.prefs.reconfigure(prefExtensions(prefs)),
        compartments.current.completion.reconfigure(
          completionExtensions(prefs.autocomplete, completionSource),
        ),
        compartments.current.signature.reconfigure(
          signatureExtensions(prefs.signatureHelp, signatureSource),
        ),
      ],
    });
  }, [prefs, completionSource, signatureSource]);

  // The document can change from outside the editor — a notebook reload, or a
  // cell restored by `z`. Only push when it actually differs, or every
  // keystroke would round-trip through here and reset the cursor.
  const source = cellText(cell);
  useEffect(() => {
    const editor = view.current;
    if (editor === null) return;
    const current = editor.state.doc.toString();
    if (current === source) return;
    editor.dispatch({ changes: { from: 0, to: current.length, insert: source } });
  }, [source]);

  // Edit mode IS "the editor has focus": Escape leaves it, Enter comes back.
  // The blur half only runs when the notebook deliberately left edit mode —
  // with the focus handler above, `editing` is true whenever the editor holds
  // focus, so this can no longer fire on an ordinary keystroke re-render.
  useEffect(() => {
    const editor = view.current;
    if (editor === null) return;
    if (editing && !editor.hasFocus) editor.focus();
    else if (!editing && editor.hasFocus) editor.contentDOM.blur();
  }, [editing]);

  return <div ref={host} className="nb-cell__editor" data-testid="nb-code-editor" />;
}

function CodeCellView(props: CellProps): JSX.Element {
  const { cell, session, running, selected, editing, onSelect, onEdit, onMove, onDelete, commands } = props;
  const code = cell as CodeCell;
  return (
    <div
      className={`nb-cell nb-cell--code${selected ? " nb-cell--selected" : ""}`}
      data-testid="nb-cell"
      data-cell-type="code"
      onMouseDown={onSelect}
      onFocus={onEdit}
    >
      <div className="nb-cell__gutter">
        <button
          className="nb-cell__run"
          title="Run this cell (⇧↵)"
          aria-label="Run this cell"
          data-testid="nb-run-cell"
          onClick={() => void session.runCell(code)}
        >
          <Play size={11} />
        </button>
        <span className={`nb-cell__count${running ? " nb-cell__count--running" : ""}`}>
          {executionLabel(code, running)}
        </span>
      </div>
      <div className="nb-cell__body">
        <CodeEditor
          cell={cell}
          session={session}
          editing={editing}
          commands={commands}
          onFocus={onEdit}
          label={`Code cell ${props.index + 1}`}
        />
        <OutputList outputs={code.outputs} />
      </div>
      <CellActions onMove={onMove} onDelete={onDelete} />
    </div>
  );
}

function MarkdownCellView(props: CellProps): JSX.Element {
  const { cell, session, selected, editing, onSelect, onEdit, onMove, onDelete, commands } = props;
  const source = cellText(cell);

  if (editing) {
    return (
      <div
        className={`nb-cell nb-cell--markdown nb-cell--editing${selected ? " nb-cell--selected" : ""}`}
        data-testid="nb-cell"
        data-cell-type="markdown"
        onMouseDown={onSelect}
      >
        <div className="nb-cell__gutter" />
        <div className="nb-cell__body">
          <MarkdownEditor
            cell={cell}
            session={session}
            editing={editing}
            commands={commands}
            label={`Markdown cell ${props.index + 1}`}
          />
        </div>
        <CellActions onMove={onMove} onDelete={onDelete} />
      </div>
    );
  }

  return (
    <div
      className={`nb-cell nb-cell--markdown${selected ? " nb-cell--selected" : ""}`}
      data-testid="nb-cell"
      data-cell-type="markdown"
      onMouseDown={onSelect}
      // Double-click to edit, Shift-Enter to render again: Jupyter's gesture,
      // because that is the one every notebook author already has.
      onDoubleClick={onEdit}
    >
      <div className="nb-cell__gutter" />
      <div className="nb-cell__body">
        {source.trim() === "" ? (
          <p className="nb-cell__empty">Empty markdown cell — double-click to write in it.</p>
        ) : (
          <div
            className="nb-cell__prose"
            data-testid="nb-markdown"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(source) }}
          />
        )}
      </div>
      <CellActions onMove={onMove} onDelete={onDelete} />
    </div>
  );
}

export function CellView(props: CellProps): JSX.Element {
  if (props.cell.cell_type === "code") return <CodeCellView {...props} />;
  if (props.cell.cell_type === "markdown") return <MarkdownCellView {...props} />;
  return (
    <div
      className={`nb-cell nb-cell--raw${props.selected ? " nb-cell--selected" : ""}`}
      data-testid="nb-cell"
      data-cell-type="raw"
      onMouseDown={props.onSelect}
    >
      <div className="nb-cell__gutter" />
      <div className="nb-cell__body">
        <pre className="nb-output__text">{cellText(props.cell)}</pre>
      </div>
      <CellActions onMove={props.onMove} onDelete={props.onDelete} />
    </div>
  );
}
