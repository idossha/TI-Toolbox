/**
 * Ported from SUNA (github.com/idossha/SUNA,
 * `apps/desktop/src/renderer/src/notebook/Outputs.tsx`), GPL-3.0, by the same
 * author. Two changes: markdown goes through this page's own small renderer
 * rather than SciMark, and an interactive plot falls back to the static image
 * the kernel sent beside it rather than loading a plotting library into a
 * privileged frame (see `mime.ts`).
 *
 * Rendering the outputs a kernel produced.
 *
 * Nothing here transforms the output on its way to the screen: the object being
 * rendered is the same object that gets written into the .ipynb, so what the
 * author sees and what the file says can never drift apart.
 */
import type { JSX } from "react";
import { ansiToSpans } from "./ansi";
import { renderMarkdown } from "./markdown";
import { INTERACTIVE_MIMES, dataUri, pickRepresentation } from "./mime";
import { sanitizeOutputHtml, svgImageSource } from "./sanitize";
import { joinText, type DisplayOutput, type ErrorOutput, type Output, type StreamOutput } from "./notebook";

/** Text with a kernel's ANSI colours preserved. */
function AnsiText({ text, className }: { text: string; className?: string }): JSX.Element {
  return (
    <pre className={className ?? "nb-output__text"}>
      {ansiToSpans(text).map((span, index) => (
        <span key={index} className={span.className === "" ? undefined : span.className}>
          {span.text}
        </span>
      ))}
    </pre>
  );
}

function StreamView({ output }: { output: StreamOutput }): JSX.Element {
  // stderr is a warning, not a failure: `print(..., file=sys.stderr)` and every
  // logging call land here, and painting them as errors would cry wolf.
  return (
    <AnsiText
      text={joinText(output.text)}
      className={
        output.name === "stderr" ? "nb-output__text nb-output__text--stderr" : "nb-output__text"
      }
    />
  );
}

function ErrorView({ output }: { output: ErrorOutput }): JSX.Element {
  const traceback = output.traceback.join("\n");
  return (
    <div className="nb-output__error" data-testid="nb-output-error">
      <AnsiText
        text={traceback === "" ? `${output.ename}: ${output.evalue}` : traceback}
        className="nb-output__text nb-output__text--error"
      />
    </div>
  );
}

/** The bundle minus its interactive types: what to draw when none renders. */
function staticFallback(data: Record<string, unknown>): Record<string, unknown> {
  const rest: Record<string, unknown> = {};
  for (const [mime, value] of Object.entries(data)) {
    if (!INTERACTIVE_MIMES.has(mime)) rest[mime] = value;
  }
  return rest;
}

function DisplayView({ output }: { output: DisplayOutput }): JSX.Element | null {
  const picked = pickRepresentation(output.data);
  // A live plot this app cannot draw is not a dead output: the kernel sends a
  // static png beside it, and that is what a reader gets.
  const rep = picked.kind === "interactive" ? pickRepresentation(staticFallback(output.data)) : picked;
  switch (rep.kind) {
    case "image":
      return <img className="nb-output__image" src={dataUri(rep.mime, rep.data)} alt="" />;
    case "svg":
      // A vector figure stays a vector figure, but as an IMAGE: an inline <svg>
      // is a document that can carry <style>, <script> and handlers of its own,
      // and the app's chrome is within their reach. In image context the
      // browser runs none of it (see `sanitize.ts`).
      return <img className="nb-output__image" src={svgImageSource(rep.svg)} alt="" />;
    case "script-html":
    case "html":
      // DataFrame tables, and plotting libraries' static snippets. Scripts have
      // never run here (innerHTML does not execute what it inserts), but
      // everything else did: a <style> rule inside an output restyled the app
      // around it. Sanitised to an allowlist first — `sanitize.ts` says why an
      // allowlist and not a sandboxed frame.
      return (
        <div className="nb-output__html" dangerouslySetInnerHTML={{ __html: sanitizeOutputHtml(rep.html) }} />
      );
    case "markdown":
      return (
        <div className="nb-output__html" dangerouslySetInnerHTML={{ __html: renderMarkdown(rep.text) }} />
      );
    case "json":
      return <AnsiText text={JSON.stringify(rep.value, null, 2)} />;
    case "text":
      return <AnsiText text={rep.text} />;
    case "interactive":
    case "none":
      return (
        <div className="nb-output__unsupported">
          {"application/vnd.jupyter.widget-view+json" in output.data
            ? "This output is an ipywidget. TI-Toolbox runs the kernel but not the widget front end — for a figure, use matplotlib, which renders here as an image."
            : `Nothing here can render ${Object.keys(output.data).join(", ") || "this output"}.`}
        </div>
      );
  }
}

export function OutputView({ output }: { output: Output }): JSX.Element | null {
  if (output.output_type === "stream") return <StreamView output={output as StreamOutput} />;
  if (output.output_type === "error") return <ErrorView output={output as ErrorOutput} />;
  return <DisplayView output={output as DisplayOutput} />;
}

export function OutputList({ outputs }: { outputs: readonly Output[] }): JSX.Element | null {
  if (outputs.length === 0) return null;
  return (
    <div className="nb-output" data-testid="nb-output">
      {outputs.map((output, index) => (
        <OutputView key={index} output={output} />
      ))}
    </div>
  );
}
