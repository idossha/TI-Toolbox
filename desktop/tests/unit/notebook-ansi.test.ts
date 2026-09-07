/**
 * Ported from SUNA (github.com/idossha/SUNA,
 * `apps/desktop/src/renderer/src/notebook/ansi.test.ts`), GPL-3.0, by the same author.
 * Unchanged but for this header and the import path.
 */
import { describe, expect, it } from 'vitest'
import { ansiToSpans } from "../../src/renderer/pages/notebooks/ansi"

const ESC = '\u001b'

describe('ansiToSpans', () => {
  it('leaves plain text as one unstyled span', () => {
    expect(ansiToSpans('hello\n')).toEqual([{ text: 'hello\n', className: '' }])
    expect(ansiToSpans('')).toEqual([])
  })

  it('colours the run between a set and a reset', () => {
    expect(ansiToSpans(`a${ESC}[31mred${ESC}[0mb`)).toEqual([
      { text: 'a', className: '' },
      { text: 'red', className: 'ansi-red' },
      { text: 'b', className: '' }
    ])
  })

  it('combines bold with a colour and drops bold on 22', () => {
    expect(ansiToSpans(`${ESC}[1;32mx${ESC}[22my`)).toEqual([
      { text: 'x', className: 'ansi-green ansi-bold' },
      { text: 'y', className: 'ansi-green' }
    ])
  })

  it('treats a bare m as a reset', () => {
    expect(ansiToSpans(`${ESC}[31ma${ESC}[mb`)).toEqual([
      { text: 'a', className: 'ansi-red' },
      { text: 'b', className: '' }
    ])
  })

  it('drops escapes it does not interpret, keeping the text', () => {
    // cursor movement, an erase, and an OSC title
    expect(ansiToSpans(`${ESC}[2Ka${ESC}[1;1Hb${ESC}]0;title\u0007c`)).toEqual([
      { text: 'a', className: '' },
      { text: 'b', className: '' },
      { text: 'c', className: '' }
    ])
  })

  it('ignores codes it has no rule for rather than guessing', () => {
    // 3 is italic, 41 a background colour: neither is styled, both are eaten
    expect(ansiToSpans(`${ESC}[3;41mx`)).toEqual([{ text: 'x', className: '' }])
  })

  // What this exists for: an IPython traceback arrives pre-coloured.
  it('keeps a traceback readable, colours and all', () => {
    const spans = ansiToSpans(
      `${ESC}[31m---------${ESC}[0m\n${ESC}[31mZeroDivisionError${ESC}[0m: division by zero`
    )
    expect(spans.map((s) => s.className)).toEqual(['ansi-red', '', 'ansi-red', ''])
    expect(spans.map((s) => s.text).join('')).toBe(
      '---------\nZeroDivisionError: division by zero'
    )
  })

  it('is a state machine across spans, not per-escape', () => {
    const spans = ansiToSpans(`${ESC}[34mone\ntwo${ESC}[0m`)
    expect(spans).toEqual([{ text: 'one\ntwo', className: 'ansi-blue' }])
  })
})
