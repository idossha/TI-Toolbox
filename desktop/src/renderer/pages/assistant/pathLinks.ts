/**
 * File paths an Assistant session prints, as terminal links (ARCHITECTURE §5 `assistant.openPath`).
 * Absolute paths count only inside the session's project folder; relative ones only when they
 * start with `./`, `../` or one of the project's own top-level folders (BIDS `derivatives/`,
 * `sourcedata/`, `code/`, `rawdata/`, `sub-<id>/`). Main re-checks every click; this only decides
 * what is underlined.
 */
import type { IBufferLine, ILink, ILinkProvider, Terminal } from "@xterm/xterm";

/** Starts at a line start or after a space, quote, bracket or `=`; never after `:`, so a URL's `//host` is no path. */
const PATH_RE = /(?<=^|[\s'"`([<=])(?:[A-Za-z]:[\\/]|\/|\.\.?\/|(?:derivatives|sourcedata|code|rawdata|sub-[A-Za-z0-9]+)\/)[^\s'"`()<>[\]{}|,;:*?]*/g;

export interface PathMatch {
  /** String index of the first character and the path text. */
  index: number;
  text: string;
}

const norm = (path: string, windows: boolean) => (windows ? path.replace(/\\/g, "/").toLowerCase() : path).replace(/\/+$/, "");

/** The linkable paths in *line*; *root* is the session's host project folder (absent: no absolute paths). */
export function findPaths(line: string, root: string | undefined, windows = false): PathMatch[] {
  const out: PathMatch[] = [];
  for (const m of line.matchAll(PATH_RE)) {
    const text = m[0].replace(/(?<=[^.])\.+$/, ""); // a sentence's full stop is not part of it
    if (!/[^\\/.]/.test(text)) continue; // "/", "./" alone
    const absolute = /^([A-Za-z]:)?[\\/]/.test(text);
    if (absolute) {
      if (!root) continue;
      const path = norm(text, windows);
      const base = norm(root, windows);
      if (path !== base && !path.startsWith(`${base}/`)) continue;
    }
    out.push({ index: m.index, text });
  }
  return out;
}

/** The row as a string plus each character's 0-based column (wide characters take two columns). */
function rowText(line: IBufferLine, term: Terminal): { text: string; columns: number[] } {
  const cell = term.buffer.active.getNullCell();
  let text = "";
  const columns: number[] = [];
  for (let x = 0; x < line.length; x++) {
    line.getCell(x, cell);
    if (cell.getWidth() === 0) continue;
    const chars = cell.getChars() || " ";
    text += chars;
    for (let i = 0; i < chars.length; i++) columns.push(x);
  }
  return { text, columns };
}

/**
 * The logical line holding 0-based row *y*: that row joined with the rows soft-wrapped onto it
 * (xterm's `isWrapped`), plus each character's 0-based cell.
 */
function logicalLine(term: Terminal, y: number): { text: string; cells: { x: number; y: number }[] } {
  const buffer = term.buffer.active;
  let start = y;
  while (start > 0 && buffer.getLine(start)?.isWrapped) start--;
  let text = "";
  const cells: { x: number; y: number }[] = [];
  for (let row = start; ; row++) {
    const line = buffer.getLine(row);
    if (!line || (row > start && !line.isWrapped)) break;
    const part = rowText(line, term);
    text += part.text;
    for (const x of part.columns) cells.push({ x, y: row });
  }
  return { text, cells };
}

/** xterm link provider: each path on the asked row's logical line, so a wrapped path is one link from any of its rows. */
export function pathLinkProvider(term: Terminal, root: () => string | undefined, windows: boolean, open: (path: string) => void): ILinkProvider {
  return {
    provideLinks(y, callback) {
      if (!term.buffer.active.getLine(y - 1)) return callback(undefined);
      const { text, cells } = logicalLine(term, y - 1);
      const links: ILink[] = findPaths(text, root(), windows)
        .map((m) => {
          const first = cells[m.index]!;
          const last = cells[m.index + m.text.length - 1]!;
          return {
            text: m.text,
            range: { start: { x: first.x + 1, y: first.y + 1 }, end: { x: last.x + 1, y: last.y + 1 } },
            activate: () => open(m.text),
          };
        })
        .filter((link) => link.range.start.y <= y && y <= link.range.end.y);
      callback(links.length ? links : undefined);
    },
  };
}
