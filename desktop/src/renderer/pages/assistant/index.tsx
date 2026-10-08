/**
 * Assistant — the user's own Claude Code or Codex, in a real terminal on this computer
 * (ARCHITECTURE §6). Main runs the CLI with the bundled agent plugin attached and the session's
 * server URL/token in its environment; this page only picks the CLI, shows its state and hosts
 * xterm.js. The page is retained across navigation (§2); a project switch ends its sessions.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, ExternalLink, RotateCcw, Square, TerminalSquare } from "lucide-react";
import { Terminal, type ITheme } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import type { PageDef } from "../../app/registry";
import { PageLayout } from "../../ui/Layout";
import { Button } from "../../ui/Button";
import { Callout, EmptyState } from "../../ui/Feedback";
import { Select } from "../../ui/Select";
import { SegmentedControl } from "../../ui/SegmentedControl";
import { Chip } from "../../ui/Status";
import type { TitAssistantBridge, TitAssistantCli, TitAssistantEffort, TitAssistantModel, TitAssistantOptions, TitAssistantStatus } from "../../../shared/tit-bridge";
import "./assistant.css";

export const CLI_INFO: Record<TitAssistantCli, { name: string; install: string; docs: string; login: string }> = {
  claude: {
    name: "Claude Code",
    install: "curl -fsSL https://claude.ai/install.sh | bash",
    docs: "https://code.claude.com/docs/en/setup",
    login: "Start it here and type /login to sign in with your Claude account.",
  },
  codex: {
    name: "Codex",
    install: "npm install -g @openai/codex",
    docs: "https://learn.chatgpt.com/docs/codex/cli",
    login: "Start it here and choose Sign in with ChatGPT (or run codex login in a terminal).",
  },
};

export const EFFORT_OPTIONS: { value: TitAssistantEffort; label: string }[] = [
  { value: "medium", label: "Medium (recommended)" },
  { value: "low", label: "Low" },
  { value: "high", label: "High" },
  { value: "default", label: "My CLI default" },
];
export const MODEL_OPTIONS: { value: TitAssistantModel; label: string }[] = [
  { value: "default", label: "My CLI default" },
  { value: "opus", label: "Opus" },
  { value: "sonnet", label: "Sonnet" },
  { value: "haiku", label: "Haiku" },
  { value: "fable", label: "Fable" },
];
export const EFFORT_TIP = "Medium is the best balance for planning jobs; higher is slower and uses more of your plan's limits.";

/** Per CLI, kept in this app only; main re-validates every value it is sent. */
type SessionOptions = Required<TitAssistantOptions>;
export const OPTIONS_KEY = "tit-assistant-options";
const DEFAULT_OPTIONS: SessionOptions = { effort: "medium", model: "default" };

export function readOptions(): Record<TitAssistantCli, SessionOptions> {
  const stored: Partial<Record<TitAssistantCli, Partial<SessionOptions>>> = (() => {
    try {
      return JSON.parse(window.localStorage.getItem(OPTIONS_KEY) ?? "{}") ?? {};
    } catch {
      return {};
    }
  })();
  const pick = (cli: TitAssistantCli): SessionOptions => ({
    effort: EFFORT_OPTIONS.find((o) => o.value === stored[cli]?.effort)?.value ?? DEFAULT_OPTIONS.effort,
    // Codex has no model menu: its model is always the CLI's own.
    model: cli === "claude" ? MODEL_OPTIONS.find((o) => o.value === stored[cli]?.model)?.value ?? DEFAULT_OPTIONS.model : "default",
  });
  return { claude: pick("claude"), codex: pick("codex") };
}

export const EXAMPLE_PROMPTS: { label: string; text: string }[] = [
  {
    label: "Bilateral thalamus pipeline",
    text: "Organise the raw scans in ~/Downloads/scan as sub-101, preprocess them, run a flex-search on the bilateral thalamus for maximum intensity, then simulate the best montage.",
  },
  { label: "Summarise this project", text: "Connect to TI-Toolbox and summarise this project: the subjects, what each one has, and any queued or running jobs." },
];

/**
 * The 16 ANSI colours, per palette. xterm's defaults are made for a black ground: its white and
 * yellow vanish on the light theme's white. These are GitHub's light and dark terminal palettes,
 * which are built for exactly these two grounds.
 */
const ANSI: Record<"light" | "dark", ITheme> = {
  light: {
    black: "#24292f", red: "#cf222e", green: "#116329", yellow: "#4d2d00", blue: "#0969da", magenta: "#8250df", cyan: "#1b7c83", white: "#6e7781",
    brightBlack: "#57606a", brightRed: "#a40e26", brightGreen: "#1a7f37", brightYellow: "#633c01", brightBlue: "#218bff", brightMagenta: "#a475f9", brightCyan: "#3192aa", brightWhite: "#8c959f",
  },
  dark: {
    black: "#484f58", red: "#ff7b72", green: "#3fb950", yellow: "#d29922", blue: "#58a6ff", magenta: "#bc8cff", cyan: "#39c5cf", white: "#b1bac4",
    brightBlack: "#6e7681", brightRed: "#ffa198", brightGreen: "#56d364", brightYellow: "#e3b341", brightBlue: "#79c0ff", brightMagenta: "#d2a8ff", brightCyan: "#56d4dd", brightWhite: "#ffffff",
  },
};

/**
 * The app's mono first, then fonts that carry the symbols Claude Code and Codex draw (⏺ ⎿ ✻ ❯,
 * braille spinners) — the app bundles only Plex Mono's Latin subset. Box-drawing and block
 * characters never reach a font: the WebGL renderer draws them itself (`customGlyphs`, on by
 * default), so the logo's quadrants join cell to cell.
 */
const TERMINAL_FONT = '"IBM Plex Mono", Menlo, "SF Mono", "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace';
const FONT_SIZE = 12;

/** The app's own tokens, read when a terminal is made and again on every theme change. */
function terminalTheme(): ITheme {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    ...ANSI[css.colorScheme === "dark" ? "dark" : "light"],
    background: token("--surface", "#ffffff"),
    foreground: token("--ink", "#161d26"),
    cursor: token("--accent", "#1f5bd7"),
    cursorAccent: token("--surface", "#ffffff"),
    selectionBackground: token("--accent-soft", "#e6eefc"),
    selectionForeground: token("--ink", "#161d26"),
    scrollbarSliderBackground: token("--line", "#d8dee6"),
    scrollbarSliderHoverBackground: token("--line-strong", "#b9c3cf"),
    scrollbarSliderActiveBackground: token("--ink-3", "#6b7784"),
  };
}

/** e2e builds (`pree2e` sets VITE_SCENE_HOOKS) hang the terminal on its host element so a spec can
 * read the buffer: under the WebGL renderer the text is on a canvas, not in the DOM. */
const TEST_HOOKS = import.meta.env.DEV || import.meta.env.VITE_SCENE_HOOKS === "1";

/** One xterm per CLI, kept for the page's life so switching CLIs keeps each scrollback. */
function AssistantTerminal({ bridge, cli, visible, onReady }: { bridge: TitAssistantBridge; cli: TitAssistantCli; visible: boolean; onReady: (term: Terminal) => void }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const term = new Terminal({
      fontFamily: TERMINAL_FONT,
      fontSize: FONT_SIZE,
      lineHeight: 1.15,
      cursorBlink: true,
      scrollback: 5000,
      // The CLIs paint their own 24-bit colours for a dark or a light terminal; this keeps their
      // text (and their grey highlight rows) readable on whichever ground the app is showing.
      minimumContrastRatio: 4.5,
      theme: terminalTheme(),
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    // http(s) only: `openExternal` refuses every other scheme in main.
    term.loadAddon(new WebLinksAddon((_event, uri) => void window.tit?.openExternal(uri)));
    const input = term.onData((data) => bridge.write(cli, data));
    const resized = term.onResize(({ cols, rows }) => bridge.resize(cli, cols, rows));
    const off = bridge.onEvent((event) => {
      if (event.cli !== cli) return;
      if (event.type === "data") term.write(event.data);
      else term.write(`\r\n\x1b[2m[${CLI_INFO[cli].name} exited with code ${event.code}]\x1b[0m\r\n`);
    });
    if (TEST_HOOKS) (element as HTMLElement & { xterm?: Terminal }).xterm = term;
    onReady(term);

    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refit = () => {
      if (element.offsetWidth && element.offsetHeight) fit.fit();
    };
    // A window drag fires the observer every frame, and the CLI redraws on every size it is sent.
    const observer = new ResizeObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(refit, 50);
    });
    // xterm measures its cell once, at open: open only after the mono face has loaded, or the grid
    // is measured with a fallback font and the real glyphs then overrun it.
    void (document.fonts?.load(`${FONT_SIZE}px ${TERMINAL_FONT}`) ?? Promise.resolve())
      .catch(() => undefined)
      .then(() => {
        if (disposed) return;
        term.open(element);
        try {
          const webgl = new WebglAddon();
          // A lost GPU context falls back to xterm's DOM renderer rather than a blank pane.
          webgl.onContextLoss(() => {
            webgl.dispose();
            element.dataset.renderer = "dom";
          });
          term.loadAddon(webgl);
          element.dataset.renderer = "webgl";
        } catch {
          element.dataset.renderer = "dom";
        }
        refit();
        observer.observe(element);
      });

    // The stamped theme and, under "system", the OS scheme both land on <html> as computed tokens.
    const retheme = () => requestAnimationFrame(() => (term.options.theme = terminalTheme()));
    const themeObserver = new MutationObserver(retheme);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const scheme = window.matchMedia?.("(prefers-color-scheme: dark)");
    scheme?.addEventListener("change", retheme);

    return () => {
      disposed = true;
      clearTimeout(timer);
      observer.disconnect();
      themeObserver.disconnect();
      scheme?.removeEventListener("change", retheme);
      off();
      input.dispose();
      resized.dispose();
      term.dispose();
    };
    // The terminal lives as long as the page; the bridge and CLI never change for one instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={host} className="assistant-terminal" hidden={!visible} data-testid={`assistant-terminal-${cli}`} aria-label={`${CLI_INFO[cli].name} terminal`} />;
}

/** Running, stopped from here, ended by itself with an exit code, or not started on this page. */
type Session = "running" | "stopped" | number | undefined;

function SessionChip({ session }: { session: Session }) {
  if (session === "running") return <Chip kind="success" dot>Running</Chip>;
  if (typeof session === "number") return <Chip kind={session === 0 ? "neutral" : "danger"} dot>Exited (code {session})</Chip>;
  return <Chip kind="neutral" dot>{session === "stopped" ? "Stopped" : "Not started"}</Chip>;
}

export function AssistantPanel({ bridge }: { bridge: TitAssistantBridge }) {
  const [cli, setCli] = useState<TitAssistantCli>("claude");
  const [sessions, setSessions] = useState<Partial<Record<TitAssistantCli, Session>>>({});
  const [error, setError] = useState<string | undefined>();
  const [starting, setStarting] = useState(false);
  const [options, setOptions] = useState(readOptions);
  // What each running session was started with, to tell the user a change waits for a restart.
  const [applied, setApplied] = useState<Partial<Record<TitAssistantCli, SessionOptions>>>({});
  const terms = useRef<Partial<Record<TitAssistantCli, Terminal>>>({});

  // Detection runs the CLI's own status command; "check again" re-asks.
  const detection = useQuery({
    queryKey: ["assistant-detect", cli],
    queryFn: async (): Promise<TitAssistantStatus | null> => (await bridge.detect(cli)) ?? null,
    staleTime: Infinity,
  });

  useEffect(() => bridge.onEvent((event) => {
    if (event.type === "exit") setSessions((prev) => ({ ...prev, [event.cli]: event.code }));
  }), [bridge]);

  // Leaving the project unmounts this page: its terminals go with it (main also ends them).
  useEffect(() => () => {
    for (const which of ["claude", "codex"] as const) void bridge.kill(which);
  }, [bridge]);

  const chooseOption = (patch: Partial<SessionOptions>) => {
    const next = { ...options, [cli]: { ...options[cli], ...patch } };
    setOptions(next);
    try {
      window.localStorage.setItem(OPTIONS_KEY, JSON.stringify(next));
    } catch {
      // best-effort persistence only
    }
  };

  const start = async () => {
    setError(undefined);
    setStarting(true);
    try {
      const term = terms.current[cli];
      term?.reset();
      const result = await bridge.start(cli, term?.cols ?? 100, term?.rows ?? 30, options[cli]);
      if (!result.ok) setError(result.error);
      else {
        setApplied((prev) => ({ ...prev, [cli]: options[cli] }));
        setSessions((prev) => ({ ...prev, [cli]: "running" }));
        term?.focus();
      }
    } finally {
      setStarting(false);
    }
  };

  const stop = async () => {
    await bridge.kill(cli);
    setSessions((prev) => ({ ...prev, [cli]: "stopped" }));
  };

  const openInTerminal = async () => {
    setError(undefined);
    const result = await bridge.openInTerminal(cli, options[cli]);
    if (!result.ok) setError(result.error);
  };

  const sendPrompt = (text: string) => {
    // Typed into the CLI's input, not submitted: the user reads it and presses Enter.
    bridge.write(cli, text);
    terms.current[cli]?.focus();
  };

  const current = detection.data ?? undefined;
  const info = CLI_INFO[cli];
  const isRunning = sessions[cli] === "running";
  const waitsForRestart = isRunning && (applied[cli]?.effort !== options[cli].effort || applied[cli]?.model !== options[cli].model);
  const cannotRun = !current?.installed || !!current?.unavailable;
  const credentials = `Your own ${info.name} login — TI-Toolbox never sees your credentials.`;
  const approval = "By default it proposes the jobs as a plan; nothing runs until you approve it on the Jobs page.";

  return (
    <div className="assistant" data-testid="assistant-page">
      <header className="assistant-head">
        <div className="assistant-toolbar">
          <SegmentedControl<TitAssistantCli>
            aria-label="Agent"
            value={cli}
            onValueChange={setCli}
            size="sm"
            options={[{ value: "claude", label: "Claude Code" }, { value: "codex", label: "Codex" }]}
          />
          <SessionChip session={sessions[cli]} />
          <span className="assistant-note" title={credentials}>{credentials}</span>
          <span className="assistant-actions">
            {isRunning ? (
              <>
                <Button size="sm" icon={<RotateCcw size={12} />} onClick={() => void start()} loading={starting}>Restart</Button>
                <Button size="sm" icon={<Square size={12} />} onClick={() => void stop()}>Stop</Button>
              </>
            ) : (
              <Button size="sm" variant="primary" icon={<TerminalSquare size={12} />} onClick={() => void start()} loading={starting} disabled={cannotRun}>
                Start {info.name}
              </Button>
            )}
            <Button size="sm" variant="ghost" icon={<ExternalLink size={12} />} onClick={() => void openInTerminal()} disabled={cannotRun}>
              Open in system terminal
            </Button>
          </span>
        </div>
        <div className="assistant-hints" aria-label="Example prompts">
          <span className="assistant-hints-label">Try</span>
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button key={prompt.label} type="button" className="chip chip-neutral assistant-chip" title={prompt.text} disabled={!isRunning} onClick={() => sendPrompt(prompt.text)}>
              {prompt.label}
            </button>
          ))}
          <span className="assistant-note" title={approval}>{approval}</span>
          <span className="assistant-options" role="group" aria-label="Session options">
            {waitsForRestart && <span className="assistant-option-label" role="status">Applies on restart</span>}
            <span className="assistant-option" title={EFFORT_TIP}>
              <span className="assistant-option-label">Effort</span>
              <span className="assistant-option-select assistant-option-effort">
                <Select aria-label="Effort" value={options[cli].effort} onValueChange={(effort) => chooseOption({ effort: effort as TitAssistantEffort })} options={EFFORT_OPTIONS} />
              </span>
            </span>
            {cli === "claude" && (
              <span className="assistant-option">
                <span className="assistant-option-label">Model</span>
                <span className="assistant-option-select assistant-option-model">
                  <Select aria-label="Model" value={options[cli].model} onValueChange={(model) => chooseOption({ model: model as TitAssistantModel })} options={MODEL_OPTIONS} />
                </span>
              </span>
            )}
          </span>
        </div>
      </header>

      {error && <Callout kind="danger">{error}</Callout>}
      {current && !current.installed && (
        <Callout kind="info" title={`${info.name} is not installed`}>
          Install it in a terminal with <code className="mono">{info.install}</code>, sign in, then{" "}
          <button type="button" className="assistant-link" onClick={() => void detection.refetch()}>check again</button>.{" "}
          <button type="button" className="assistant-link" onClick={() => void window.tit?.openExternal(info.docs)}>Installation guide</button>
        </Callout>
      )}
      {current?.installed && current.unavailable && <Callout kind="warning">{current.unavailable}</Callout>}
      {current?.installed && !current.unavailable && current.loggedIn === false && !isRunning && (
        <Callout kind="info" title={`${info.name} is not signed in`}>{info.login}</Callout>
      )}

      {/* A click on the card's padding focuses the terminal too, not only a click on its grid. */}
      <div className="assistant-terminals" onClick={() => terms.current[cli]?.focus()}>
        {(["claude", "codex"] as const).map((which) => (
          <AssistantTerminal key={which} bridge={bridge} cli={which} visible={which === cli} onReady={(term) => (terms.current[which] = term)} />
        ))}
      </div>
    </div>
  );
}

function AssistantPage() {
  const bridge = window.tit?.assistant;
  return (
    <PageLayout variant="bleed" className="assistant-layout">
      {bridge ? (
        <AssistantPanel bridge={bridge} />
      ) : (
        <EmptyState icon={<Bot size={24} />} message="The Assistant runs your own Claude Code or Codex on this computer. Open TI-Toolbox in the desktop app to use it." />
      )}
    </PageLayout>
  );
}

const page: PageDef = {
  id: "assistant",
  title: "Assistant",
  purpose: "Run your own Claude Code or Codex on this project, with TI-Toolbox's job tools attached.",
  navGroup: "pinned",
  order: 0,
  icon: Bot,
  Component: AssistantPage,
  enabled: true,
};

export default page;
