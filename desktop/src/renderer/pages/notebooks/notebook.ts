/**
 * The nbformat v4 document, as this renderer holds it.
 *
 * Adapted from SUNA's `@suna/notebook` (github.com/idossha/SUNA), but only the
 * *model* half. SUNA reimplements nbformat's serializer in TypeScript because
 * there its renderer writes the file; here the file never leaves the container
 * and `nbformat` itself does the reading and writing (`tit/server/notebooks.py`),
 * so what crosses the wire is plain JSON and this module only has to not damage
 * it on the way through.
 *
 * That is the one rule everything below serves: **unknown keys are never
 * dropped**. Every interface carries an index signature and objects are mutated
 * rather than rebuilt. A notebook opened and saved untouched must come back
 * unchanged, or every notebook in a project becomes a merge conflict the moment
 * two tools disagree about it.
 */

export type CellType = "code" | "markdown" | "raw";

export interface Output {
  output_type: string;
  [key: string]: unknown;
}

export interface StreamOutput extends Output {
  output_type: "stream";
  name: string;
  text: string | string[];
}

export interface ErrorOutput extends Output {
  output_type: "error";
  ename: string;
  evalue: string;
  traceback: string[];
}

export interface DisplayOutput extends Output {
  data: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface Cell {
  cell_type: CellType;
  source: string | string[];
  metadata: Record<string, unknown>;
  id?: string;
  [key: string]: unknown;
}

export interface CodeCell extends Cell {
  cell_type: "code";
  outputs: Output[];
  execution_count: number | null;
}

export interface Notebook {
  cells: Cell[];
  metadata: Record<string, unknown>;
  nbformat: number;
  nbformat_minor: number;
  [key: string]: unknown;
}

/** A cell's source as one string; the wire form may be a list of lines. */
export function cellText(cell: Cell): string {
  return typeof cell.source === "string" ? cell.source : cell.source.join("");
}

/** A stream/text payload as one string, same rule. */
export function joinText(value: string | string[]): string {
  return typeof value === "string" ? value : value.join("");
}

/**
 * Cell ids are minted only when the format version actually has them
 * (`nbformat > 4 || nbformat_minor >= 5`) — SUNA's rule, for SUNA's reason: a
 * v4.4 file that gains ids on save is a file every other tool then re-diffs.
 */
function mintsIds(notebook: Notebook): boolean {
  return notebook.nbformat > 4 || notebook.nbformat_minor >= 5;
}

let idSeq = 0;

export function newCell(cellType: CellType, notebook: Notebook): Cell {
  const cell: Cell = { cell_type: cellType, source: "", metadata: {} };
  if (cellType === "code") {
    (cell as CodeCell).outputs = [];
    (cell as CodeCell).execution_count = null;
  }
  if (mintsIds(notebook)) cell.id = `c${Date.now().toString(36)}${(idSeq += 1).toString(36)}`;
  return cell;
}

/**
 * Change a cell's type in place. The same object survives, because the
 * notebook array holds it and the caller's selection points at it; what
 * changes is which nbformat keys are present.
 */
export function convertCell(cell: Cell, cellType: CellType): void {
  cell.cell_type = cellType;
  if (cellType === "code") {
    if (!Array.isArray((cell as CodeCell).outputs)) (cell as CodeCell).outputs = [];
    if (!("execution_count" in cell)) (cell as CodeCell).execution_count = null;
  } else {
    delete cell.outputs;
    delete cell.execution_count;
  }
}

/**
 * React keys for cells, tracked out-of-band.
 *
 * nbformat 4.5 gives cells an `id`, but older files do not, and MINTING one
 * for a file the author only opened would rewrite it. So identity lives in a
 * WeakMap here rather than in the document.
 */
const cellKeys = new WeakMap<object, string>();
let keySeq = 0;

export function cellKey(cell: Cell): string {
  const existing = cellKeys.get(cell);
  if (existing !== undefined) return existing;
  const key = typeof cell.id === "string" && cell.id !== "" ? `id:${cell.id}` : `k${(keySeq += 1)}`;
  cellKeys.set(cell, key);
  return key;
}

/**
 * Forget a cell's key so it remounts. Used when a cell changes type: a cell
 * carrying an nbformat id would otherwise be handed the SAME key and React
 * would keep the editor built for the old type.
 */
export function retireCellKey(cell: Cell): void {
  cellKeys.set(cell, `k${(keySeq += 1)}`);
}

export function isCodeCell(cell: Cell): cell is CodeCell {
  return cell.cell_type === "code";
}
