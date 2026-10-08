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
import "@xterm/xterm/css/xterm.css";
import type { PageDef } from "../../app/registry";
import { useThemeStore } from "../../app/theme/store";
import { PageLayout } from "../../ui/Layout";
import { Button } from "../../ui/Button";
import { Callout, EmptyState } from "../../ui/Feedback";
import { SegmentedControl } from "../../ui/SegmentedControl";
import type { TitAssistantBridge, TitAssistantCli, TitAssistantStatus } from "../../../shared/tit-bridge";
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

export const EXAMPLE_PROMPTS: { label: string; text: string }[] = [
  {
    label: "Bilateral thalamus pipeline",
    text: "Organise the raw scans in ~/Downloads/scan as sub-101, preprocess them, run a flex-search on the bilateral thalamus for maximum intensity, then simulate the best montage.",
  },
  { label: "Summarise this project", text: "Connect to TI-Toolbox and summarise this project: the subjects, what each one has, and any queued or running jobs." },
];

/** The app's own tokens, read when a terminal is made and again on a theme change. */
function terminalTheme(): ITheme {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    background: token("--surface", "#ffffff"),
    foreground: token("--ink", "#161d26"),
    cursor: token("--accent", "#1f5bd7"),
    cursorAccent: token("--surface", "#ffffff"),
    selectionBackground: token("--accent-soft", "#e6eefc"),
  };
}

/** One xterm per CLI, kept for the page's life so switching CLIs keeps each scrollback. */
function AssistantTerminal({ bridge, cli, visible, onReady }: { bridge: TitAssistantBridge; cli: TitAssistantCli; visible: boolean; onReady: (term: Terminal) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const theme = useThemeStore((state) => state.theme);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const term = new Terminal({
      fontFamily: getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim() || "monospace",
      fontSize: 12,
      cursorBlink: true,
      scrollback: 5000,
      theme: terminalTheme(),
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(element);
    termRef.current = term;
    fitRef.current = fit;
    const input = term.onData((data) => bridge.write(cli, data));
    const off = bridge.onEvent((event) => {
      if (event.cli !== cli) return;
      if (event.type === "data") term.write(event.data);
      else term.write(`\r\n\x1b[2m[${CLI_INFO[cli].name} exited with code ${event.code}]\x1b[0m\r\n`);
    });
    const observer = new ResizeObserver(() => {
      if (!element.offsetWidth || !element.offsetHeight) return;
      fit.fit();
      bridge.resize(cli, term.cols, term.rows);
    });
    observer.observe(element);
    onReady(term);
    return () => {
      observer.disconnect();
      off();
      input.dispose();
      term.dispose();
      termRef.current = null;
    };
    // The terminal lives as long as the page; the bridge and CLI never change for one instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // The stamped theme lands on <html> first; read the tokens on the next frame.
    const frame = requestAnimationFrame(() => {
      if (termRef.current) termRef.current.options.theme = terminalTheme();
    });
    return () => cancelAnimationFrame(frame);
  }, [theme]);

  return <div ref={host} className="assistant-terminal" hidden={!visible} data-testid={`assistant-terminal-${cli}`} aria-label={`${CLI_INFO[cli].name} terminal`} />;
}

export function AssistantPanel({ bridge }: { bridge: TitAssistantBridge }) {
  const [cli, setCli] = useState<TitAssistantCli>("claude");
  const [running, setRunning] = useState<Partial<Record<TitAssistantCli, boolean>>>({});
  const [error, setError] = useState<string | undefined>();
  const [starting, setStarting] = useState(false);
  const terms = useRef<Partial<Record<TitAssistantCli, Terminal>>>({});

  // Detection runs the CLI's own status command; "check again" re-asks.
  const detection = useQuery({
    queryKey: ["assistant-detect", cli],
    queryFn: async (): Promise<TitAssistantStatus | null> => (await bridge.detect(cli)) ?? null,
    staleTime: Infinity,
  });

  useEffect(() => bridge.onEvent((event) => {
    if (event.type === "exit") setRunning((prev) => ({ ...prev, [event.cli]: false }));
  }), [bridge]);

  // Leaving the project unmounts this page: its terminals go with it (main also ends them).
  useEffect(() => () => {
    for (const which of ["claude", "codex"] as const) void bridge.kill(which);
  }, [bridge]);

  const start = async () => {
    setError(undefined);
    setStarting(true);
    try {
      const term = terms.current[cli];
      term?.reset();
      const result = await bridge.start(cli, term?.cols ?? 100, term?.rows ?? 30);
      if (!result.ok) setError(result.error);
      else {
        setRunning((prev) => ({ ...prev, [cli]: true }));
        term?.focus();
      }
    } finally {
      setStarting(false);
    }
  };

  const stop = async () => {
    await bridge.kill(cli);
    setRunning((prev) => ({ ...prev, [cli]: false }));
  };

  const openInTerminal = async () => {
    setError(undefined);
    const result = await bridge.openInTerminal(cli);
    if (!result.ok) setError(result.error);
  };

  const sendPrompt = (text: string) => {
    // Typed into the CLI's input, not submitted: the user reads it and presses Enter.
    bridge.write(cli, text);
    terms.current[cli]?.focus();
  };

  const current = detection.data ?? undefined;
  const info = CLI_INFO[cli];
  const isRunning = !!running[cli];

  return (
    <div className="assistant" data-testid="assistant-page">
      <div className="assistant-bar">
        <SegmentedControl<TitAssistantCli>
          aria-label="Agent"
          value={cli}
          onValueChange={setCli}
          size="sm"
          options={[{ value: "claude", label: "Claude Code" }, { value: "codex", label: "Codex" }]}
        />
        <span className="assistant-note">Your own {info.name} login — TI-Toolbox never sees your credentials.</span>
        <span className="assistant-actions">
          {isRunning ? (
            <>
              <Button size="sm" icon={<RotateCcw size={12} />} onClick={() => void start()} loading={starting}>Restart</Button>
              <Button size="sm" icon={<Square size={12} />} onClick={() => void stop()}>Stop</Button>
            </>
          ) : (
            <Button size="sm" variant="primary" icon={<TerminalSquare size={12} />} onClick={() => void start()} loading={starting} disabled={!current?.installed || !!current?.unavailable}>
              Start {info.name}
            </Button>
          )}
          <Button size="sm" variant="ghost" icon={<ExternalLink size={12} />} onClick={() => void openInTerminal()} disabled={!current?.installed || !!current?.unavailable}>
            Open in system terminal
          </Button>
        </span>
      </div>

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

      <div className="assistant-prompts" aria-label="Example prompts">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button key={prompt.label} type="button" className="chip chip-neutral assistant-chip" title={prompt.text} disabled={!isRunning} onClick={() => sendPrompt(prompt.text)}>
            {prompt.label}
          </button>
        ))}
        <span className="assistant-note">By default it proposes the jobs as a plan; nothing runs until you approve it on the Jobs page.</span>
      </div>

      <div className="assistant-terminals">
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
    <PageLayout variant="bleed">
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
