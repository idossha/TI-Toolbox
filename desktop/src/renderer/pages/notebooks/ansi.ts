/**
 * Ported from SUNA (github.com/idossha/SUNA,
 * `apps/desktop/src/renderer/src/notebook/ansi.ts`), GPL-3.0, by the same author.
 * Unchanged but for this header; the ANSI classes map to this app's tokens in notebooks.css.
 */
/**
 * The small slice of ANSI a kernel actually emits, turned into spans.
 *
 * IPython tracebacks are coloured — the offending line, the caret, the
 * exception name — and stripping the escapes would throw away the one thing
 * that makes a long traceback readable. This is not a terminal emulator: no
 * cursor movement, no erase, no alternate screen. Only SGR (ESC-[-…-m) is
 * interpreted; every other escape sequence is dropped, and the text itself is
 * never interpreted as markup.
 */

export interface AnsiSpan {
  text: string
  /** CSS class names, or '' for unstyled text. */
  className: string
}

/**
 * The 16 terminal colours as class suffixes. The classes map to the theme's
 * own palette in notebook.css, so a traceback belongs to the app's colour
 * scheme rather than importing a terminal's.
 */
const FG: Record<number, string> = {
  30: 'black',
  31: 'red',
  32: 'green',
  33: 'yellow',
  34: 'blue',
  35: 'magenta',
  36: 'cyan',
  37: 'white',
  90: 'bright-black',
  91: 'bright-red',
  92: 'bright-green',
  93: 'bright-yellow',
  94: 'bright-blue',
  95: 'bright-magenta',
  96: 'bright-cyan',
  97: 'bright-white'
}

// The escape characters are written as unicode escapes rather than as raw
// bytes: a literal escape character is invisible in a diff and trivially
// deleted by accident, and this pattern is the one place it matters.
/** SGR (captured, interpreted), OSC (dropped), any other CSI (dropped). */
// eslint-disable-next-line no-control-regex -- matching ESC and BEL is this file's whole job
const ESCAPE = /\u001b\[([0-9;]*)m|\u001b\][^\u0007]*\u0007|\u001b\[[0-9;?]*[A-Za-z]/g

interface Style {
  fg: string | null
  bold: boolean
}

function classNameFor(style: Style): string {
  const parts: string[] = []
  if (style.fg !== null) parts.push(`ansi-${style.fg}`)
  if (style.bold) parts.push('ansi-bold')
  return parts.join(' ')
}

function applySgr(style: Style, params: string): Style {
  // A bare ESC-[-m is ESC-[-0-m: reset.
  const codes = params === '' ? [0] : params.split(';').map((part) => Number(part) || 0)
  let next = style
  for (const code of codes) {
    if (code === 0) next = { fg: null, bold: false }
    else if (code === 1) next = { ...next, bold: true }
    else if (code === 22) next = { ...next, bold: false }
    else if (code === 39) next = { ...next, fg: null }
    else if (FG[code] !== undefined) next = { ...next, fg: FG[code] as string }
    // Anything else (background colours, 256-colour selectors, italics) is
    // ignored rather than guessed at.
  }
  return next
}

/** Split ANSI-coloured text into styled spans, in order. */
export function ansiToSpans(text: string): AnsiSpan[] {
  const spans: AnsiSpan[] = []
  let style: Style = { fg: null, bold: false }
  let index = 0

  ESCAPE.lastIndex = 0
  let match = ESCAPE.exec(text)
  while (match !== null) {
    if (match.index > index) {
      spans.push({ text: text.slice(index, match.index), className: classNameFor(style) })
    }
    // Only SGR carries a capture group; other escapes just vanish.
    if (match[1] !== undefined) style = applySgr(style, match[1])
    index = match.index + match[0].length
    match = ESCAPE.exec(text)
  }
  if (index < text.length) {
    spans.push({ text: text.slice(index), className: classNameFor(style) })
  }
  return spans
}
