/**
 * A PDF page drawn as a bitmap — the toolbox's plots, treated as the images they are.
 *
 * The maintainer, on the first version of this pane: *"the PDFs should either be visualized better
 * or they should be treated as an image. It needs to be cleaner and simpler."* An `<embed>` or an
 * `<iframe>` pointed at a PDF hands the file to Chromium's built-in viewer, which brings a
 * thumbnail sidebar, a page box, zoom, rotate, draw, download and print — a whole application
 * around a single-page matplotlib histogram.
 *
 * Every PDF this pane meets is a plot: the analyzer's ROI histogram, a stats run's permutation null
 * distribution and its cluster size/mass scatter. So it is rasterised here, with pdf.js's rendering
 * core and none of its viewer, into the same `<canvas>`-shaped box a PNG gets. The result goes in
 * the Figures grid beside the PNGs and opens in the same lightbox; a multi-page document gets a
 * plain prev/next and nothing else.
 *
 * Rendered client-side because the runtime cannot do it server-side: the container image carries
 * no `pdftoppm`, no ghostscript, no `pymupdf` and no `pypdfium2` (checked on
 * `ti-toolbox-…-tit-1`), and PIL and matplotlib both write PDFs without being able to read one.
 * Adding a rasteriser to the image would be a rebuild for a thumbnail.
 */
import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
// `?worker`, not `?url`: Vite bundles the worker as its own chunk and constructs it for us. With
// `?url` the worker is emitted as a `.mjs` asset and loaded by the browser as a module script, and
// the app's own static file server answers `.mjs` with `application/octet-stream` — which Chromium
// refuses under strict MIME checking for module scripts ("Failed to load module script"). pdf.js
// then falls back to its fake worker and the render fails anyway.
import PdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?worker";

/** One worker for the page: pdf.js multiplexes every document over a shared `workerPort`. */
let workerPort: Worker | undefined;
function ensureWorker(): Worker {
  workerPort ??= new PdfWorker();
  return workerPort;
}

/** One `getDocument` per URL for the life of the page: the grid tile and the lightbox share it. */
const documents = new Map<string, Promise<PDFDocumentProxy>>();

function load(url: string): Promise<PDFDocumentProxy> {
  const existing = documents.get(url);
  if (existing) return existing;
  const task = pdfjs.getDocument({ url, withCredentials: true, worker: pdfjs.PDFWorker.fromPort({ port: ensureWorker() }) }).promise;
  documents.set(url, task);
  return task;
}

export function PdfCanvas({
  url,
  page = 1,
  className,
  label,
  onPageCount,
}: {
  url: string;
  /** 1-based. Out-of-range pages clamp rather than throw. */
  page?: number;
  className?: string;
  label?: string;
  /** Reports the document's page count once, so a caller can decide to show prev/next. */
  onPageCount?: (pages: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Keyed by what is being drawn, so a new url or page reads as "loading" without an effect
  // writing that state synchronously on every change.
  const key = `${url}#${page}`;
  const [status, setStatus] = useState<{ key: string; state: "ready" | "error" }>({
    key: "",
    state: "ready",
  });
  const state = status.key === key ? status.state : "loading";

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const doc = await load(url);
        if (cancelled) return;
        onPageCount?.(doc.numPages);
        const pdfPage = await doc.getPage(Math.min(Math.max(1, page), doc.numPages));
        const canvas = canvasRef.current;
        if (cancelled || !canvas) return;
        // Render at the box the layout gave the canvas, times the device ratio, so a 140px
        // thumbnail costs a 140px raster and the lightbox's full-width one is sharp.
        const box = canvas.getBoundingClientRect();
        const base = pdfPage.getViewport({ scale: 1 });
        const ratio = window.devicePixelRatio || 1;
        const scale = ((box.width || 240) / base.width) * ratio;
        const viewport = pdfPage.getViewport({ scale: Math.max(scale, 0.1) });
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        const context = canvas.getContext("2d");
        if (!context) return;
        await pdfPage.render({ canvasContext: context, viewport }).promise;
        if (!cancelled) setStatus({ key, state: "ready" });
      } catch {
        if (!cancelled) setStatus({ key, state: "error" });
      }
    })();
    return () => {
      cancelled = true;
    };
    // `onPageCount` is a reporting callback; re-running on its identity would re-render the page
    // on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, page, key]);

  return (
    <div className={className} data-testid="results-pdf-page" data-state={state}>
      <canvas ref={canvasRef} aria-label={label ?? "PDF page"} />
      {state === "error" && <p className="field-help">Could not render this PDF.</p>}
    </div>
  );
}

/** True for a path this module can draw. */
export function isPdf(path: string): boolean {
  return /\.pdf$/i.test(path);
}
