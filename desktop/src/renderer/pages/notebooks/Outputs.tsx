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
import { useLayoutEffect, useRef, useState, type JSX } from "react";
import { ansiToSpans } from "./ansi";
import { renderMarkdown } from "./markdown";
import { INTERACTIVE_MIMES, dataUri, pickRepresentation } from "./mime";
import { sanitizeOutputHtml, svgImageSource } from "./sanitize";
import {
  joinText,
  type DisplayOutput,
  type ErrorOutput,
  type Output,
  type StreamOutput,
} from "./notebook";

/** Text with a kernel's ANSI colours preserved. */
function AnsiText({
  text,
  className,
}: {
  text: string;
  className?: string;
}): JSX.Element {
  return (
    <pre className={className ?? "nb-output__text"}>
      {ansiToSpans(text).map((span, index) => (
        <span
          key={index}
          className={span.className === "" ? undefined : span.className}
        >
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
        output.name === "stderr"
          ? "nb-output__text nb-output__text--stderr"
          : "nb-output__text"
      }
    />
  );
}

function ErrorView({ output }: { output: ErrorOutput }): JSX.Element {
  const traceback = output.traceback.join("\n");
  return (
    <div className="nb-output__error" data-testid="nb-output-error">
      <AnsiText
        text={
          traceback === "" ? `${output.ename}: ${output.evalue}` : traceback
        }
        className="nb-output__text nb-output__text--error"
      />
    </div>
  );
}

/** The bundle minus its interactive types: what to draw when none renders. */
function staticFallback(
  data: Record<string, unknown>,
): Record<string, unknown> {
  const rest: Record<string, unknown> = {};
  for (const [mime, value] of Object.entries(data)) {
    if (!INTERACTIVE_MIMES.has(mime)) rest[mime] = value;
  }
  return rest;
}

function DisplayView({
  output,
}: {
  output: DisplayOutput;
}): JSX.Element | null {
  const picked = pickRepresentation(output.data);
  // A live plot this app cannot draw is not a dead output: the kernel sends a
  // static png beside it, and that is what a reader gets.
  const rep =
    picked.kind === "interactive"
      ? pickRepresentation(staticFallback(output.data))
      : picked;
  switch (rep.kind) {
    case "image":
      return (
        <img
          className="nb-output__image"
          src={dataUri(rep.mime, rep.data)}
          alt=""
        />
      );
    case "svg":
      // A vector figure stays a vector figure, but as an IMAGE: an inline <svg>
      // is a document that can carry <style>, <script> and handlers of its own,
      // and the app's chrome is within their reach. In image context the
      // browser runs none of it (see `sanitize.ts`).
      return (
        <img
          className="nb-output__image"
          src={svgImageSource(rep.svg)}
          alt=""
        />
      );
    case "script-html":
    case "html":
      // DataFrame tables, and plotting libraries' static snippets. Scripts have
      // never run here (innerHTML does not execute what it inserts), but
      // everything else did: a <style> rule inside an output restyled the app
      // around it. Sanitised to an allowlist first — `sanitize.ts` says why an
      // allowlist and not a sandboxed frame.
      return (
        <div
          className="nb-output__html"
          dangerouslySetInnerHTML={{ __html: sanitizeOutputHtml(rep.html) }}
        />
      );
    case "markdown":
      return (
        <div
          className="nb-output__html"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(rep.text) }}
        />
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
  if (output.output_type === "stream")
    return <StreamView output={output as StreamOutput} />;
  if (output.output_type === "error")
    return <ErrorView output={output as ErrorOutput} />;
  return <DisplayView output={output as DisplayOutput} />;
}

/**
 * Text rows of stream and error output past which a cell's output area is
 * condensed: a fixed-height box that scrolls, following its tail while the
 * kernel is still writing. A FEM run or a flex-search is tens of thousands of
 * SimNIBS log lines, and unconstrained they pushed every later cell off the
 * page. The rows shown are still the whole output; nothing is dropped.
 */
export const CONDENSED_AFTER_LINES = 40;

/** Rows a condensed output shows before it scrolls. */
const CONDENSED_ROWS = 24;

function lineCount(text: string): number {
  if (text === "") return 0;
  let count = 1;
  for (let i = 0; i < text.length; i += 1)
    if (text.charCodeAt(i) === 10) count += 1;
  return text.endsWith("\n") ? count - 1 : count;
}

/**
 * The kernel sends one stream message per write, and the notebook keeps each
 * one (the file is the kernel's word verbatim). On screen, consecutive writes
 * to the same stream are one block of text: the line-by-line objects were an
 * artefact of transport, not of what the author printed.
 */
export function coalesceStreams(outputs: readonly Output[]): Output[] {
  const merged: Output[] = [];
  for (const output of outputs) {
    const last = merged[merged.length - 1];
    if (
      output.output_type === "stream" &&
      last !== undefined &&
      last.output_type === "stream" &&
      (last as StreamOutput).name === (output as StreamOutput).name
    ) {
      merged[merged.length - 1] = {
        ...(last as StreamOutput),
        text:
          joinText((last as StreamOutput).text) +
          joinText((output as StreamOutput).text),
      };
    } else {
      merged.push(output);
    }
  }
  return merged;
}

/** Rows of plain text (stream and error) the cell's outputs add up to. */
export function textLineCount(outputs: readonly Output[]): number {
  let lines = 0;
  for (const output of outputs) {
    if (output.output_type === "stream")
      lines += lineCount(joinText((output as StreamOutput).text));
    else if (output.output_type === "error")
      lines += (output as ErrorOutput).traceback.length;
  }
  return lines;
}

export function OutputList({
  outputs,
}: {
  outputs: readonly Output[];
}): JSX.Element | null {
  const [expanded, setExpanded] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const lines = textLineCount(outputs);
  const long = lines > CONDENSED_AFTER_LINES;
  const condensed = long && !expanded;

  // A condensed box follows its tail, the way a terminal does: while the
  // kernel writes, the newest progress line is the one in view.
  useLayoutEffect(() => {
    const element = box.current;
    if (condensed && element !== null) element.scrollTop = element.scrollHeight;
  }, [condensed, outputs.length, lines]);

  // A cell cleared and re-run starts condensed again (state adjusted during
  // render, the React-sanctioned form of "reset when a prop changes").
  const [seenCount, setSeenCount] = useState(outputs.length);
  if (outputs.length !== seenCount) {
    setSeenCount(outputs.length);
    if (outputs.length === 0) setExpanded(false);
  }

  if (outputs.length === 0) return null;
  const shown = coalesceStreams(outputs);
  return (
    <div className="nb-output" data-testid="nb-output">
      {long && (
        <div className="nb-output__bar">
          <span className="nb-output__count">
            {lines.toLocaleString()} lines
          </span>
          <button
            type="button"
            className="nb-output__toggle"
            data-testid="nb-output-toggle"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "Condense" : "Show all"}
          </button>
        </div>
      )}
      <div
        ref={box}
        className={
          condensed
            ? "nb-output__body nb-output__body--condensed"
            : "nb-output__body"
        }
        data-testid="nb-output-body"
        style={
          condensed
            ? {
                maxHeight: `calc(var(--nb-font-size, 12px) * 1.45 * ${CONDENSED_ROWS})`,
              }
            : undefined
        }
      >
        {shown.map((output, index) => (
          <OutputView key={index} output={output} />
        ))}
      </div>
    </div>
  );
}
