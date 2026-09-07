/**
 * Ported from SUNA (github.com/idossha/SUNA,
 * `apps/desktop/src/renderer/src/notebook/CellView.tsx`), GPL-3.0, by the same
 * author. The structure, the modal edit/command split and the reasoning are
 * SUNA's; the editor is not. SUNA puts a full CodeMirror in every cell because
 * the rest of that app already ships one. TI-Toolbox ships no editor, and five
 * CodeMirror packages for cell text is a dependency the rest of this app has no
 * use for — so a cell is an auto-sizing `<textarea>` in the mono token face.
 * Syntax highlighting is on the roadmap and would be that dependency's job.
 *
 * Selection and the modal edit/command distinction belong to the notebook, not
 * to a cell: every keystroke that acts on the cell LIST (insert, delete, move,
 * change type) has to be able to see its neighbours. So a cell is told whether
 * it is selected and whether it is being edited, and reports back gestures — it
 * decides neither.
 */
import { useEffect, useLayoutEffect, useRef, type JSX, type KeyboardEvent } from "react";
import { ChevronDown, ChevronUp, Play, X } from "lucide-react";
import { renderMarkdown } from "./markdown";
import { cellText, type Cell, type CodeCell } from "./notebook";
import { OutputList } from "./Outputs";
import type { Session } from "./session";

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

function CellEditor({
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

  // Edit mode IS "the editor has focus": Escape leaves it, Enter comes back.
  useEffect(() => {
    const node = ref.current;
    if (node === null) return;
    if (editing && document.activeElement !== node) node.focus();
    else if (!editing && document.activeElement === node) node.blur();
  }, [editing]);

  return (
    <textarea
      ref={ref}
      className="nb-cell__editor"
      spellCheck={false}
      aria-label={label}
      value={text}
      // The cell object is mutated, not replaced: it is the same object that
      // gets sent back to the server as this notebook's document. The write
      // goes through the session rather than straight onto the prop, so the
      // one place that owns the document is the one place that changes it.
      onChange={(event) => session.setCellSource(cell, event.target.value)}
      onKeyDown={(event) => editorKeys(event, commands)}
    />
  );
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
        <CellEditor
          cell={cell}
          session={session}
          editing={editing}
          commands={commands}
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
          <CellEditor
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
