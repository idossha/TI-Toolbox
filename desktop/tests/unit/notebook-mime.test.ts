/**
 * Ported from SUNA (github.com/idossha/SUNA,
 * `apps/desktop/src/renderer/src/notebook/mime.test.ts`), GPL-3.0, by the same author.
 * The `interactiveHtml` block is dropped: TI-Toolbox does not render live plots (see mime.ts).
 */
import { describe, expect, it } from 'vitest'
import { dataUri, pickRepresentation } from "../../src/renderer/pages/notebooks/mime"

describe('pickRepresentation', () => {
  // The case this exists for: matplotlib sends both, and the plot wins.
  it('prefers the figure over its repr', () => {
    expect(
      pickRepresentation({ 'image/png': 'AAAA', 'text/plain': '<Figure size 640x480>' })
    ).toEqual({ kind: 'image', mime: 'image/png', data: 'AAAA' })
  })

  it('prefers a vector figure over a raster one', () => {
    expect(pickRepresentation({ 'image/svg+xml': '<svg/>', 'image/png': 'AAAA' })).toEqual({
      kind: 'svg',
      svg: '<svg/>'
    })
  })

  it('prefers a DataFrame table over its text repr', () => {
    expect(pickRepresentation({ 'text/html': '<table></table>', 'text/plain': 'a b' })).toEqual({
      kind: 'html',
      html: '<table></table>'
    })
  })

  it('accepts a line list as readily as a string', () => {
    expect(pickRepresentation({ 'text/plain': ['one\n', 'two'] })).toEqual({
      kind: 'text',
      text: 'one\ntwo'
    })
  })

  it('keeps application/json as a value, never as text', () => {
    expect(pickRepresentation({ 'application/json': { a: 1 } })).toEqual({
      kind: 'json',
      value: { a: 1 }
    })
  })

  it('falls past a type it cannot read down to one it can', () => {
    // an image whose payload is an object, not base64
    expect(pickRepresentation({ 'image/png': { oops: true }, 'text/plain': 'x' })).toEqual({
      kind: 'text',
      text: 'x'
    })
  })

  it('reports nothing renderable rather than guessing', () => {
    expect(pickRepresentation({})).toEqual({ kind: 'none' })
    expect(pickRepresentation({ 'application/vnd.custom': 'x' })).toEqual({ kind: 'none' })
  })
})

describe('dataUri', () => {
  it('strips the line wrapping kernels put in base64', () => {
    expect(dataUri('image/png', 'AAAA\nBBBB\n')).toBe('data:image/png;base64,AAAABBBB')
  })
})

describe('interactive output', () => {
  it('recognises a live plotly figure rather than mistaking it for its png', () => {
    // The representation is reported honestly; Outputs.tsx is what decides to
    // draw the static fallback instead, and it can only do that if the pick
    // says "interactive" here.
    const rep = pickRepresentation({
      'application/vnd.plotly.v1+json': { data: [], layout: {} },
      'image/png': 'iVBOR',
      'text/plain': '<plotly.Figure>'
    })
    expect(rep.kind).toBe('interactive')
  })

  it('sends html that carries a script to the sandboxed frame, and plain html not', () => {
    expect(pickRepresentation({ 'text/html': '<div id="p"></div><script>go()</script>' }).kind).toBe(
      'script-html'
    )
    expect(pickRepresentation({ 'text/html': '<table><tr><td>1</td></tr></table>' }).kind).toBe(
      'html'
    )
  })
})
