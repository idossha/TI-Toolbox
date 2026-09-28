"""Report design system: page shell, components, SVG charts and the QC-check record.

One module and one stylesheet (``report.css``) for every TI-Toolbox report built on it
(ARCHITECTURE.md §14). A page makes no network request: CSS, the widget script below, the IBM
Plex fonts (``fonts/``, embedded once) and every image are inline, which is what the in-app
iframe CSP (``tit/server/routes/files.py::REPORT_CSP``) allows. No template engine, no library.

A pipeline reports QC as :class:`Check` rows whose ``role`` comes from ``tit.reporting.qc_rules``:
``gate`` and ``internal`` rows block the output, ``advisory`` rows warn, ``report`` rows show a value
against a reference. A blocking row's status must come from the pipeline's own failure list
(:func:`gate_status`), so a table can never disagree with the verdict.
"""

from __future__ import annotations

import base64
import html
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent

esc = html.escape

STATUSES = ("pass", "warn", "fail", "info")
STATUS_WORD = {"pass": "Pass", "warn": "Review", "fail": "Fail", "info": "Info"}

_ICON = {
    "pass": '<svg width="{s}" height="{s}" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity=".16"/><path d="M4.6 8.3l2.2 2.2 4.6-4.9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "warn": '<svg width="{s}" height="{s}" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.6l6.6 11.6H1.4z" fill="currentColor" opacity=".16"/><path d="M8 1.6l6.6 11.6H1.4z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M8 6v3.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="11.4" r=".95" fill="currentColor"/></svg>',
    "fail": '<svg width="{s}" height="{s}" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity=".16"/><path d="M5.4 5.4l5.2 5.2M10.6 5.4l-5.2 5.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    "info": '<svg width="{s}" height="{s}" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" opacity=".14"/><path d="M8 7.2v4.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="4.9" r=".95" fill="currentColor"/></svg>',
}

_FONTS = (
    ("TIT Sans", "ibm-plex-sans-latin-400-normal.woff2", 400, "normal"),
    ("TIT Sans", "ibm-plex-sans-latin-600-normal.woff2", 600, "normal"),
    ("TIT Sans", "ibm-plex-sans-latin-400-italic.woff2", 400, "italic"),
    ("TIT Mono", "ibm-plex-mono-latin-400-normal.woff2", 400, "normal"),
)

# Widgets: theme toggle (system/light/dark; storage may throw in the sandboxed iframe), contents
# scroll-spy, flicker, plane tabs, slice scrubber, chart tooltips, copy button, and
# opening every <details> for print.
_JS = r"""(()=>{
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const tb=$('#theme-btn');
if(tb){const order=['system','light','dark'];let i=0;
  const apply=()=>{const m=order[i];if(m==='system')document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme',m);tb.querySelector('span').textContent='Theme: '+m;};
  try{const s=localStorage.getItem('tit-report-theme');if(s)i=Math.max(0,order.indexOf(s));}catch(e){}
  apply();tb.addEventListener('click',()=>{i=(i+1)%3;apply();try{localStorage.setItem('tit-report-theme',order[i])}catch(e){}});}
const links=$$('.toc a'),secs=links.map(a=>document.getElementById(a.hash.slice(1))).filter(Boolean);
if('IntersectionObserver' in window&&secs.length){const seen=new Map();
  const io=new IntersectionObserver(es=>{es.forEach(e=>seen.set(e.target.id,e.isIntersecting));
    const cur=secs.find(s=>seen.get(s.id));if(!cur)return;
    links.forEach(a=>a.setAttribute('aria-current',a.hash.slice(1)===cur.id?'true':'false'));},{rootMargin:'-10% 0px -70% 0px'});
  secs.forEach(s=>io.observe(s));}
$$('.flick-fig').forEach(f=>{const boxes=$$('.flick',f),bs=$$('button[data-mode]',f);
  const set=mode=>{bs.forEach(b=>b.setAttribute('aria-pressed',b.dataset.mode===mode?'true':'false'));
    boxes.forEach(box=>{box.dataset.auto=mode==='auto'?'1':'0';box.dataset.show=mode==='b'?'b':'a';const tag=$('.tag',box);
      if(tag)tag.textContent=mode==='auto'?'Flickering':(mode==='b'?bs[1].textContent:bs[0].textContent);});};
  bs.forEach(b=>b.addEventListener('click',()=>set(b.dataset.mode)));
  boxes.forEach(box=>box.addEventListener('keydown',e=>{if(e.key===' '){e.preventDefault();set(box.dataset.show==='b'?'a':'b');}}));
  set(matchMedia('(prefers-reduced-motion: reduce)').matches?'a':(f.dataset.default||'a'));});
$$('[data-tabs]').forEach(g=>{const bs=$$('button[data-tab]',g),root=g.closest('figure')||document;
  const set=t=>{bs.forEach(b=>b.setAttribute('aria-pressed',b.dataset.tab===t?'true':'false'));
    $$('[data-panel]',root).forEach(p=>p.hidden=p.dataset.panel!==t);};
  bs.forEach(b=>b.addEventListener('click',()=>set(b.dataset.tab)));set(bs[0].dataset.tab);});
$$('.scrub').forEach(s=>{const d=JSON.parse($('script[type="application/json"]',s).textContent);
  const im=$('img',s),r=$('input',s),o=$('output',s);
  r.addEventListener('input',()=>{const i=+r.value;im.src=d.frames[i];im.alt=d.alt+' '+d.labels[i];o.textContent=d.labels[i];});});
const tip=document.createElement('div');tip.className='tip';tip.setAttribute('role','tooltip');document.body.appendChild(tip);
const show=t=>{tip.textContent='';t.dataset.tip.split('\n').forEach((l,i)=>{if(i)tip.appendChild(document.createElement('br'));tip.appendChild(document.createTextNode(l));});tip.classList.add('on');};
const place=(x,y)=>{tip.style.left=Math.min(x+14,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=(y+16+tip.offsetHeight>innerHeight?y-tip.offsetHeight-12:y+16)+'px';};
document.addEventListener('pointerover',e=>{const t=e.target.closest('[data-tip]');if(t)show(t);});
document.addEventListener('pointermove',e=>{if(tip.classList.contains('on'))place(e.clientX,e.clientY);});
document.addEventListener('pointerout',e=>{if(e.target.closest('[data-tip]'))tip.classList.remove('on');});
$$('[data-copy]').forEach(b=>b.addEventListener('click',()=>{const txt=document.getElementById(b.dataset.copy).innerText.trim();
  const done=()=>{const o=b.textContent;b.textContent='Copied';setTimeout(()=>b.textContent=o,1400);};
  if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(txt).then(done,()=>{});}));
addEventListener('beforeprint',()=>$$('details').forEach(d=>{d.dataset.wasOpen=d.open;d.open=true;}));
addEventListener('afterprint',()=>$$('details').forEach(d=>{d.open=d.dataset.wasOpen==='true';}));
})();"""


# ── text, assets, status ───────────────────────────────────────────────────


def inline(text: str) -> str:
    """Escape plain text for HTML; `backticks` become ``<code>``. For text stored in QC records."""
    parts = esc(text).split("`")
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


@lru_cache(maxsize=1)
def _head_assets() -> str:
    fonts = "\n".join(
        f"@font-face{{font-family:'{family}';src:url({data_uri((_HERE / 'fonts' / name).read_bytes(), 'font/woff2')}) "
        f"format('woff2');font-weight:{weight};font-style:{style};font-display:swap}}"
        for family, name, weight, style in _FONTS
    )
    return fonts + "\n" + (_HERE / "report.css").read_text(encoding="utf-8")


def img(raw: bytes, alt: str, mime: str = "image/webp") -> str:
    """An inline image. *alt* is required: every report image says what it shows."""
    if not alt:
        raise ValueError("report images need alt text")
    return f'<img src="{data_uri(raw, mime)}" alt="{esc(alt)}" decoding="async">'


def icon(kind: str, size: int = 14) -> str:
    return _ICON[kind].format(s=size)


def status(kind: str, label: str | None = None, pill: bool = False) -> str:
    """Status as icon + word, never colour alone."""
    label = STATUS_WORD[kind] if label is None else label
    return f'<span class="st {kind}{f" pill {kind}" if pill else ""}">{icon(kind)}{esc(label)}</span>'


def _mark() -> str:
    """The TI-Toolbox mark: two carriers whose sum beats inside an envelope."""
    xs = [i / 119 for i in range(120)]
    env = [abs(math.cos(math.pi * x)) for x in xs]
    carrier = [math.cos(2 * math.pi * 9.5 * x) * e for x, e in zip(xs, env)]

    def pts(ys: list[float]) -> str:
        return " ".join(f"{3 + 26 * x:.2f},{15 - 9.5 * y:.2f}" for x, y in zip(xs, ys))

    return (
        '<svg width="30" height="30" viewBox="0 0 32 30" aria-hidden="true"><rect width="32" height="30" rx="7" fill="var(--ink)"/>'
        f'<polyline points="{pts(env)}" fill="none" stroke="var(--field)" stroke-width="1.3" opacity=".9"/>'
        f'<polyline points="{pts([-e for e in env])}" fill="none" stroke="var(--field)" stroke-width="1.3" opacity=".9"/>'
        f'<polyline points="{pts(carrier)}" fill="none" stroke="var(--paper)" stroke-width="1.1" stroke-linejoin="round"/></svg>'
    )


# ── page shell ─────────────────────────────────────────────────────────────


def page(
    *,
    title: str,
    kind: str,
    subject: str,
    toc: list[tuple[str, str, str | None]],
    body: str,
    footer: str = "",
    description: str = "",
    generator: str = "TI-Toolbox",
    extra_css: str = "",
) -> str:
    """The whole document. *toc* rows are ``(anchor, label, status kind or None)``."""
    toc_html = "".join(
        f'<li><a href="#{a}" aria-current="false">{esc(text)}'
        + (
            f'<span class="st {s}" title="{STATUS_WORD[s]}">{icon(s, 13)}<span class="sr">{STATUS_WORD[s]}</span></span>'
            if s
            else ""
        )
        + "</a></li>"
        for a, text, s in toc
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{esc(description)}">
<meta name="generator" content="{esc(generator)}">
<title>{esc(title)}</title>
<style>{_head_assets()}{extra_css}</style>
</head>
<body>
<div class="shell">
<nav class="rail" aria-label="Report contents">
  <a class="brand" href="#top">{_mark()}<div><b>TI-Toolbox</b><span>{esc(kind)}</span></div></a>
  <ol class="toc">{toc_html}</ol>
  <div class="rail-foot">
    <div class="meta">{esc(subject)}</div>
    <button class="tbtn no-print" id="theme-btn" type="button" aria-label="Switch colour theme"><span>Theme: system</span></button>
  </div>
</nav>
<main class="sheet" id="top">
<div class="sheet-inner">
{body}
<footer class="foot">{footer}</footer>
</div>
</main>
</div>
<script>{_JS}</script>
</body>
</html>"""


def masthead(kind: str, title: str, meta: list[tuple[str, str]]) -> str:
    """Title block with a definition list of facts; *meta* values are trusted HTML."""
    dl = "".join(f"<div><dt>{esc(k)}</dt><dd>{v}</dd></div>" for k, v in meta)
    return (
        f'<header class="mast"><div><div class="kind">{esc(kind)}</div><h1>{esc(title)}</h1></div>'
        f'<dl style="--n:{min(len(meta), 4)}">{dl}</dl></header>'
    )


def section(
    anchor: str,
    title: str,
    body: str,
    lead: str = "",
    st: str | None = None,
    st_label: str | None = None,
) -> str:
    badge = status(st, st_label, pill=True) if st else ""
    lead_html = f'<p class="lead">{lead}</p>' if lead else ""
    return (
        f'<section class="sec" id="{anchor}" aria-labelledby="{anchor}-h"><div class="sec-h">'
        f'<h2 id="{anchor}-h">{esc(title)}</h2>{badge}</div>{lead_html}{body}</section>'
    )


def callout(kind: str, title: str, body: str) -> str:
    return (
        f'<div class="callout {kind}" role="note"><span class="ic">{icon(kind, 18)}</span>'
        f"<div><p><b>{title}</b></p>{body}</div></div>"
    )


def figure(
    num: int,
    title: str,
    content: str,
    caption: str,
    controls: str = "",
    cls: str = "",
    attrs: str = "",
) -> str:
    """A numbered figure; every figure has a caption that says what good looks like."""
    return (
        f'<figure class="fig {cls}" {attrs}><div class="fig-bar"><span class="ttl">Figure {num}. {esc(title)}</span>'
        f'<span class="ctl">{controls}</span></div>{content}<figcaption>{caption}</figcaption></figure>'
    )


def label(text: str, style: str) -> str:
    """A small label positioned over a lightbox image (*style* is CSS for its position)."""
    return f'<span class="lb-label" style="{style}">{esc(text)}</span>'


def tile_labels(
    labels: list[str],
    cols: int,
    tile: tuple[int, int],
    shape: tuple[int, int],
    gap: int = 4,
) -> str:
    """Labels at the top-left of each mosaic tile, placed in percent of the mosaic."""
    th, tw = tile
    height, width = shape[:2]
    return "".join(
        label(
            text,
            f"left:calc({100 * (n % cols) * (tw + gap) / width:.3f}% + 6px);top:calc({100 * (n // cols) * (th + gap) / height:.3f}% + 5px)",
        )
        for n, text in enumerate(labels)
    )


def flicker(a: bytes, b: bytes, la: str, lb: str, alt: str, labels: str = "") -> str:
    """Two stacked images of one view on the dark imaging surround; the page flickers between them."""
    return (
        f'<div class="lightbox"><div class="lb-inner flick" tabindex="0" aria-label="{esc(alt)}; press space to switch">'
        f"{img(a, f'{alt} — {la}')}{img(b, f'{alt} — {lb}')}{labels}"
        f'<span class="tag" aria-live="polite"></span></div></div>'
    )


def segmented(buttons: list[tuple[str, str]], group_label: str, attr: str) -> str:
    """A row of toggle buttons: ``attr="data-mode"`` drives a flicker, ``"data-tab"`` panel tabs."""
    inner = "".join(
        f'<button type="button" {attr}="{k}">{esc(v)}</button>' for k, v in buttons
    )
    tabs = " data-tabs" if attr == "data-tab" else ""
    return f'<span class="seg" role="group" aria-label="{esc(group_label)}"{tabs}>{inner}</span>'


def scrubber(
    num: int,
    frames: list[bytes],
    labels: list[str],
    start: int,
    alt: str,
    extra: str = "",
) -> str:
    """One image and a slider; the frames live in a JSON block and are swapped by the page script."""
    uris = [data_uri(f, "image/webp") for f in frames]
    data = json.dumps({"frames": uris, "labels": labels, "alt": alt})
    return (
        f'<div class="scrub"><div class="lightbox"><div class="lb-inner"><img src="{uris[start]}" alt="{esc(alt)} {esc(labels[start])}">{extra}</div></div>'
        f'<div class="scrub-row no-print"><label for="scrub{num}">Slice</label>'
        f'<input id="scrub{num}" type="range" min="0" max="{len(frames) - 1}" value="{start}" step="1">'
        f'<output for="scrub{num}">{esc(labels[start])}</output></div>'
        f'<script type="application/json">{data}</script></div>'
    )


def table(
    head: list[str],
    rows: list[list[str]],
    caption: str = "",
    right: set[int] = frozenset(),
    cls: str = "",
) -> str:
    """A data table; cells are trusted HTML. Columns in *right* are right-aligned and tabular."""
    th = "".join(
        f'<th scope="col" class="{"r" if i in right else ""}">{h}</th>'
        for i, h in enumerate(head)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"r num" if i in right else ""}">{c}</td>'
            for i, c in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    cap = f"<caption>{caption}</caption>" if caption else ""
    return f'<div class="tbl-wrap"><table class="tbl {cls}">{cap}<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def kv(pairs: list[tuple[str, str]]) -> str:
    """A definition list; values are trusted HTML."""
    return (
        '<dl class="kv">'
        + "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in pairs)
        + "</dl>"
    )


def details(summary: str, body: str, note: str = "", open_: bool = False) -> str:
    return (
        f'<details class="raw"{" open" if open_ else ""}><summary>{esc(summary)}<span class="muted">{esc(note)}</span>'
        f"</summary><div>{body}</div></details>"
    )


def code(text: str) -> str:
    return f'<pre class="code">{esc(text)}</pre>'


def methods(paragraphs: list[str], id_: str = "methods-text") -> str:
    ps = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        f'<div class="methods"><button class="tbtn" type="button" data-copy="{id_}">Copy text</button>'
        f'<div class="prose" id="{id_}">{ps}</div></div>'
    )


def references(refs: list[dict]) -> str:
    """Reference list from ``tit.reporting.reportlets.references`` entries (label, citation, doi)."""
    items = "".join(
        f'<li id="ref-{esc(r["label"])}"><span class="k">{esc(r["label"])}</span><span>{esc(r["citation"])}'
        + (
            f' <a href="https://doi.org/{esc(r["doi"])}">doi:{esc(r["doi"])}</a>'
            if r.get("doi")
            else ""
        )
        + "</span></li>"
        for r in refs
    )
    return f'<ol class="refs">{items}</ol>'


def cite(*labels: str) -> str:
    return "".join(
        f'<a class="cite" href="#ref-{esc(k)}">[{esc(k)}]</a>' for k in labels
    )


# ── SVG charts (themed by CSS variables, hover values via data-tip) ────────


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    span = hi - lo
    if span <= 0:
        return [lo]
    step = 10 ** math.floor(math.log10(span / n))
    step *= next(m for m in (1, 2, 2.5, 5, 10) if span / (step * m) <= n)
    out, v = [], math.ceil(lo / step - 1e-9) * step
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def hist_chart(
    series: list[dict],
    bins: list[float],
    *,
    xlabel: str,
    width: int = 490,
    height: int = 230,
    band: tuple[float, float, str] | None = None,
    xlim: tuple[float, float] | None = None,
    xfmt: Callable[[float], str] = lambda v: f"{v:.1f}",
) -> str:
    """Density outlines (step lines + 10 % wash) with one hover band per bin.

    *series*: ``{label, values (fraction per bin), var ('--s1' ...)}``; *band*: ``(lo, hi, label)``.
    """
    ml, mr, mt, mb = 40, 12, 22, 38
    pw, ph = width - ml - mr, height - mt - mb
    lo, hi = (bins[0], bins[-1]) if xlim is None else xlim
    ymax = max(max(s["values"]) for s in series) * 1.12 or 1.0

    def X(v: float) -> float:
        return ml + (v - lo) / (hi - lo) * pw

    def Y(v: float) -> float:
        return mt + ph - v / ymax * ph

    shown = [i for i in range(len(bins) - 1) if bins[i + 1] > lo and bins[i] < hi]
    p = [
        f'<svg class="chart" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(xlabel)}">'
    ]
    for t in nice_ticks(0, ymax, 4):
        p.append(
            f'<line class="grid" x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>'
            f'<text x="{ml - 6}" y="{Y(t) + 4:.1f}" text-anchor="end">{t * 100:.0f}%</text>'
        )
    if band:
        b0, b1, text = band
        p.append(
            f'<rect x="{X(b0):.1f}" y="{mt}" width="{X(b1) - X(b0):.1f}" height="{ph}" fill="var(--band)" stroke="var(--band-edge)"/>'
            f'<text x="{(X(b0) + X(b1)) / 2:.1f}" y="{mt - 4}" text-anchor="middle" style="fill:var(--pass)">{esc(text)}</text>'
        )
    for t in nice_ticks(lo, hi, 6):
        p.append(
            f'<text x="{X(t):.1f}" y="{mt + ph + 16}" text-anchor="middle">{xfmt(t)}</text>'
        )
    p.append(
        f'<line class="axis" x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}"/>'
        f'<text x="{ml + pw / 2:.1f}" y="{height - 4}" text-anchor="middle">{esc(xlabel)}</text>'
    )
    for s in series:
        pts = " ".join(
            f"{X(max(bins[i], lo)):.1f},{Y(s['values'][i]):.1f} {X(min(bins[i + 1], hi)):.1f},{Y(s['values'][i]):.1f}"
            for i in shown
        )
        area = f"{X(max(bins[shown[0]], lo)):.1f},{Y(0):.1f} {pts} {X(min(bins[shown[-1] + 1], hi)):.1f},{Y(0):.1f}"
        p.append(
            f'<polygon points="{area}" fill="var({s["var"]})" opacity=".10"/>'
            f'<polyline points="{pts}" fill="none" stroke="var({s["var"]})" stroke-width="2" stroke-linejoin="round"/>'
        )
    for i in shown:
        tip = f"{xfmt(bins[i])}–{xfmt(bins[i + 1])}" + "".join(
            f"\n{s['label']} {s['values'][i] * 100:.1f}%" for s in series
        )
        x0, x1 = X(max(bins[i], lo)), X(min(bins[i + 1], hi))
        p.append(
            f'<rect class="hit" x="{x0:.1f}" y="{mt}" width="{max(x1 - x0, 1):.1f}" height="{ph}" data-tip="{esc(tip)}"/>'
        )
    return "".join(p) + "</svg>"


def legend(items: list[tuple[str, str]], dot: bool = False) -> str:
    """Inline key: ``(label, css var)``."""
    return "".join(
        f'<span class="key"><i class="{"dot" if dot else ""}" style="background:var({v})"></i>{esc(t)}</span>'
        for t, v in items
    )


def gate_scale(
    value: float,
    lo: float,
    hi: float,
    ok: tuple[float, float],
    st: str = "pass",
    width: int = 190,
) -> str:
    """The gate rail: track, accepted range, threshold ticks and the value dot, clamped to the track."""
    pad = 6

    def X(v: float) -> float:
        return pad + (min(max(v, lo), hi) - lo) / (hi - lo) * (width - 2 * pad)

    colour = {
        "pass": "var(--pass-mark)",
        "warn": "var(--warn-mark)",
        "fail": "var(--fail-mark)",
    }.get(st, "var(--ink-2)")
    ticks = "".join(
        f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="6" y2="20" stroke="var(--ink-2)" stroke-width="1.2"/>'
        for t in ok
        if lo < t < hi
    )
    return (
        f'<svg width="{width}" height="26" viewBox="0 0 {width} 26" aria-hidden="true">'
        f'<line x1="{pad}" x2="{width - pad}" y1="13" y2="13" stroke="var(--rule-strong)" stroke-width="2" stroke-linecap="round"/>'
        f'<line x1="{X(ok[0]):.1f}" x2="{X(ok[1]):.1f}" y1="13" y2="13" stroke="var(--band-edge)" stroke-width="6"/>{ticks}'
        f'<circle cx="{X(value):.1f}" cy="13" r="5" fill="{colour}" stroke="var(--paper)" stroke-width="2"/></svg>'
    )


# ── QC checks ──────────────────────────────────────────────────────────────


ROLE_WORD = {
    "gate": "gate",
    "internal": "software check",
    "advisory": "advisory",
    "report": "reported",
}


@dataclass
class Check:
    """One QC row: what was measured, against which rule, why, and whether it passed.

    ``role`` is the rule's role (``gate``, ``internal``, ``advisory``, ``report``); ``description`` is
    its plain-text sentence (backticks mark code), ``cite`` its DOIs and ``note`` where the value is
    TI-Toolbox's own. ``rail`` is ``(lo, hi, ok_lo, ok_hi)`` for the gate rail, or ``None``.
    """

    id: str
    label: str
    description: str
    shown: str
    threshold: str
    status: str
    role: str = "gate"
    value: float | None = None
    rail: tuple[float, float, float, float] | None = None
    cite: tuple[str, ...] | list[str] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES or self.role not in ROLE_WORD:
            raise ValueError(f"unknown QC status {self.status!r} or role {self.role!r}")

    @property
    def blocking(self) -> bool:
        return self.role in ("gate", "internal")


def gate_status(check_id: str, failures: list[str]) -> str:
    """A blocking check fails if and only if the pipeline listed it in its failures."""
    return "fail" if check_id in failures else "pass"


def verdict(checks: list[Check], consequence: str = "") -> tuple[str, str]:
    """``(seal kind, headline)``: fail if a blocking check failed, else warn if an advisory needs attention."""
    blocking = [c for c in checks if c.blocking]
    n_fail = sum(c.status == "fail" for c in blocking)
    n_act = sum(c.role == "advisory" and c.status in ("warn", "fail") for c in checks)
    if n_fail:
        return "fail", f"Failed {n_fail} of {len(blocking)} blocking checks" + (
            f" — {consequence}" if consequence else ""
        )
    tail = (
        f", {n_act} {'advisory needs' if n_act == 1 else 'advisories need'} attention"
        if n_act
        else ""
    )
    return (
        "warn" if n_act else "pass"
    ), f"Passed all {len(blocking)} blocking checks{tail}"


def checks_table(
    checks: list[Check],
    caption: str,
    cite: Callable[[list[str]], str] = lambda dois: "",
) -> str:
    """Status, name with its role badge, plain-text rule and citations, value, rule and (for gates) the rail.

    *cite* turns a row's DOIs into citation links (the caller owns the reference list).
    """
    with_rail = any(c.rail for c in checks)
    rows = []
    for c in checks:
        why = (
            inline(c.description)
            + (f" {cite(list(c.cite))}" if c.cite else "")
            + (f" <i>({esc(c.note)})</i>" if c.note else "")
        )
        row = [
            status(c.status, "Reported" if c.role == "report" else None),
            f'<span class="name">{esc(c.label)}</span> <span class="role {c.role}">{ROLE_WORD[c.role]}</span><span class="desc">{why}</span>',
            esc(c.shown),
            esc(c.threshold),
        ]
        if with_rail:
            row.append(
                f'<span class="scale">{gate_scale(c.value, c.rail[0], c.rail[1], c.rail[2:], st=c.status)}</span>'
                if c.rail and c.value is not None
                else ""
            )
        rows.append(row)
    head = ["Status", "Check", "Measured", "Rule"] + (
        ['<span class="sr">Position within the rule</span>'] if with_rail else []
    )
    return table(head, rows, caption=caption, right={2, 3}, cls="gate")
