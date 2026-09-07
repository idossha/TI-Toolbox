/**
 * The one help affordance in the app: an (i) icon that **opens on click**.
 *
 * It used to be a `Tooltip` in some places and a `Popover` in others, so the same glyph behaved
 * two different ways — hover here, click there. An icon that looks clickable must be clickable
 * (maintainer, Sep 2026), so every (i) in the app now routes through `HelpIcon`/`HelpBody` and
 * nothing help-shaped opens on hover. Hover shows at most the native `title` the browser draws.
 *
 * `HelpBody` renders the help text with a deliberately tiny markdown subset — `**bold**`,
 * `` `code` ``, `- ` list items, blank-line paragraphs. No markdown library: help strings are
 * ours, short, and a parser we can read in one screen is the right size for them.
 */
import { Info } from "lucide-react";
import type { ReactNode } from "react";
import { IconButton } from "./Button";
import { Popover } from "./Overlay";
import { cn } from "./utils";

/** One inline run of the mini-markdown: plain, bold or code. */
type Inline = { kind: "text" | "bold" | "code"; value: string };

/** `**bold**` and `` `code` `` — everything else is literal. */
export function parseInline(text: string): Inline[] {
  const runs: Inline[] = [];
  const re = /\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) {
    if (match.index > last) runs.push({ kind: "text", value: text.slice(last, match.index) });
    if (match[1] !== undefined) runs.push({ kind: "bold", value: match[1] });
    else runs.push({ kind: "code", value: match[2] ?? "" });
    last = match.index + match[0].length;
  }
  if (last < text.length) runs.push({ kind: "text", value: text.slice(last) });
  return runs;
}

/** A paragraph of inline runs, or a bullet list of them. */
export type HelpBlock = { kind: "p"; lines: string[] } | { kind: "ul"; items: string[] };

/** Blank line = paragraph break; a run of `- ` lines = one list. */
export function parseHelp(text: string): HelpBlock[] {
  const blocks: HelpBlock[] = [];
  for (const chunk of text.split(/\n\s*\n/)) {
    const lines = chunk.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length) continue;
    let buffer: string[] = [];
    let items: string[] = [];
    const flushP = () => {
      if (buffer.length) blocks.push({ kind: "p", lines: buffer });
      buffer = [];
    };
    const flushUl = () => {
      if (items.length) blocks.push({ kind: "ul", items });
      items = [];
    };
    for (const line of lines) {
      if (line.startsWith("- ")) {
        flushP();
        items.push(line.slice(2));
      } else {
        flushUl();
        buffer.push(line);
      }
    }
    flushP();
    flushUl();
  }
  return blocks;
}

function Runs({ text }: { text: string }) {
  return (
    <>
      {parseInline(text).map((run, i) =>
        run.kind === "bold" ? (
          <strong key={i}>{run.value}</strong>
        ) : run.kind === "code" ? (
          <code key={i} className="help-code">
            {run.value}
          </code>
        ) : (
          <span key={i}>{run.value}</span>
        ),
      )}
    </>
  );
}

/** The help text itself, mini-markdown rendered. Exported so a page can put it in its own popover. */
export function HelpBody({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn("help-body", className)}>
      {parseHelp(text).map((block, i) =>
        block.kind === "ul" ? (
          <ul key={i} className="help-list">
            {block.items.map((item, j) => (
              <li key={j}>
                <Runs text={item} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <Runs text={block.lines.join(" ")} />
          </p>
        ),
      )}
    </div>
  );
}

export interface HelpIconProps {
  /** Heading inside the popover — the thing being explained. */
  title?: string;
  /** Mini-markdown body. Optional when `children` carries the whole content. */
  text?: string;
  /** Anything richer than prose (a diagram, a "Read more" link) under the text. */
  children?: ReactNode;
  /** Accessible name of the trigger. Keep it distinct from any field label — see `Field`. */
  label?: string;
  /** 13 matches a section header, 12 a field label row. */
  size?: number;
  /** `plain` is the bare 14px glyph used inside `Field`'s label row. */
  variant?: "button" | "plain";
  /** For tests and e2e sweeps. */
  testId?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/**
 * The (i) trigger plus its click popover. Radix's Popover gives us `aria-expanded`, Esc,
 * outside-click dismiss, second-click toggle and focus return for free — the point of this
 * wrapper is that every call site gets exactly those, and no call site gets a hover tooltip.
 */
export function HelpIcon({
  title,
  text,
  children,
  label = "Help",
  size = 13,
  variant = "button",
  testId,
  open,
  onOpenChange,
}: HelpIconProps) {
  const trigger =
    variant === "plain" ? (
      <button type="button" className="field-help-trigger" aria-label={label} data-help-icon data-testid={testId}>
        <Info size={size} aria-hidden />
      </button>
    ) : (
      <IconButton
        icon={<Info size={size} aria-hidden />}
        aria-label={label}
        variant="ghost"
        size="sm"
        data-help-icon
        data-testid={testId}
      />
    );
  return (
    <Popover trigger={trigger} open={open} onOpenChange={onOpenChange}>
      <div className="help-popover" data-testid={testId ? `${testId}-content` : undefined}>
        {title && <div className="help-popover-title">{title}</div>}
        {text && <HelpBody text={text} />}
        {children}
      </div>
    </Popover>
  );
}
