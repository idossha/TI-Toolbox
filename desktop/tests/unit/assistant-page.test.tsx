// @vitest-environment jsdom
/**
 * The Assistant page's states (ARCHITECTURE §6): browser (no bridge), not installed, not signed in,
 * running and exited, plus the example prompt being typed (not submitted) into the session.
 * xterm.js is replaced by a recording stand-in: jsdom has no canvas, and what is under test is the
 * page's wiring to the bridge, not xterm's rendering. Expected copy is the page's own exported
 * constants, so a wording change is a single edit.
 */
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { TitAssistantBridge, TitAssistantEvent, TitAssistantStatus, TitBridge } from "../../src/shared/tit-bridge";

const written: string[] = [];
vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    cols = 90;
    rows = 20;
    options: Record<string, unknown> = {};
    loadAddon() {}
    open() {}
    onData() { return { dispose() {} }; }
    write(data: string) { written.push(data); }
    reset() {}
    focus() {}
    dispose() {}
  },
}));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: class { fit() {} } }));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

const { AssistantPanel, CLI_INFO, EXAMPLE_PROMPTS } = await import("../../src/renderer/pages/assistant/index");
const page = (await import("../../src/renderer/pages/assistant/index")).default;

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} disconnect() {} };

let container: HTMLDivElement;
let root: Root;
let listeners: ((event: TitAssistantEvent) => void)[];
let bridge: TitAssistantBridge & { [K in keyof TitAssistantBridge]: ReturnType<typeof vi.fn> };

function makeBridge(status: TitAssistantStatus) {
  listeners = [];
  bridge = {
    detect: vi.fn().mockResolvedValue(status),
    start: vi.fn().mockResolvedValue({ ok: true }),
    write: vi.fn(),
    resize: vi.fn(),
    kill: vi.fn().mockResolvedValue(undefined),
    onEvent: vi.fn((listener: (event: TitAssistantEvent) => void) => { listeners.push(listener); return () => {}; }),
    openInTerminal: vi.fn().mockResolvedValue({ ok: true }),
  } as never;
  return bridge;
}

beforeEach(() => {
  written.length = 0;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  delete window.tit;
});

async function settle() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
}
async function render(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  act(() => root.render(<QueryClientProvider client={client}>{node}</QueryClientProvider>));
  await settle();
}
const button = (text: string) => [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(text))!;

it("explains itself in a browser, where there is no host terminal", async () => {
  await render(<page.Component />);
  expect(container.textContent).toContain("Open TI-Toolbox in the desktop app");
});

it("offers installation when the CLI is missing, and cannot start", async () => {
  makeBridge({ cli: "claude", installed: false, running: false });
  window.tit = { openExternal: vi.fn() } as unknown as TitBridge;
  await render(<AssistantPanel bridge={bridge} />);
  expect(container.textContent).toContain(`${CLI_INFO.claude.name} is not installed`);
  expect(container.textContent).toContain(CLI_INFO.claude.install);
  expect(button("Start Claude Code").disabled).toBe(true);
  act(() => button("Installation guide").click());
  expect(window.tit!.openExternal).toHaveBeenCalledWith(CLI_INFO.claude.docs);
  act(() => button("check again").click());
  await settle();
  expect(bridge.detect).toHaveBeenCalledTimes(2);
});

it("tells a signed-out user how to sign in, and still lets them start", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: false, running: false });
  await render(<AssistantPanel bridge={bridge} />);
  expect(container.textContent).toContain(CLI_INFO.claude.login);
  expect(container.textContent).toContain("TI-Toolbox never sees your credentials");
  expect(button("Start Claude Code").disabled).toBe(false);
});

it("shows why a session cannot start here", async () => {
  makeBridge({ cli: "codex", installed: true, loggedIn: true, running: false, unavailable: "Open a project first." });
  await render(<AssistantPanel bridge={bridge} />);
  act(() => [...container.querySelectorAll<HTMLButtonElement>("[role=radio]")].find((b) => b.textContent === "Codex")!.click());
  await settle();
  expect(bridge.detect).toHaveBeenCalledWith("codex");
  expect(container.textContent).toContain("Open a project first.");
  expect(button("Start Codex").disabled).toBe(true);
});

it("runs a session: start with the terminal's size, output, an example prompt typed but not sent, exit", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  await render(<AssistantPanel bridge={bridge} />);
  const chip = button(EXAMPLE_PROMPTS[0]!.label);
  expect(chip.disabled).toBe(true);
  await act(async () => button("Start Claude Code").click());
  await settle();
  expect(bridge.start).toHaveBeenCalledWith("claude", 90, 20);
  expect(button("Restart")).toBeTruthy();
  act(() => listeners.forEach((l) => l({ cli: "claude", type: "data", data: "Welcome to Claude Code" })));
  act(() => listeners.forEach((l) => l({ cli: "codex", type: "data", data: "not mine" })));
  expect(written.filter((w) => w === "Welcome to Claude Code")).toHaveLength(1);
  act(() => button(EXAMPLE_PROMPTS[0]!.label).click());
  expect(bridge.write).toHaveBeenCalledWith("claude", EXAMPLE_PROMPTS[0]!.text);
  expect(EXAMPLE_PROMPTS[0]!.text).not.toMatch(/[\r\n]/);
  act(() => listeners.forEach((l) => l({ cli: "claude", type: "exit", code: 0 })));
  expect(written.some((w) => w.includes("exited with code 0"))).toBe(true);
  expect(button("Start Claude Code")).toBeTruthy();
});

it("reports a failed start", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  bridge.start.mockResolvedValue({ ok: false, error: "The Assistant runs only with a TI-Toolbox on this computer." });
  await render(<AssistantPanel bridge={bridge} />);
  await act(async () => button("Start Claude Code").click());
  await settle();
  expect(container.textContent).toContain("only with a TI-Toolbox on this computer");
});
