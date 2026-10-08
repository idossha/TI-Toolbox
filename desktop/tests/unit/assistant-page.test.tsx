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
    onResize() { return { dispose() {} }; }
    write(data: string) { written.push(data); }
    reset() {}
    focus() {}
    dispose() {}
  },
}));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: class { fit() {} } }));
vi.mock("@xterm/addon-webgl", () => ({ WebglAddon: class { onContextLoss() {} dispose() {} } }));
const linkHandlers: ((event: MouseEvent, uri: string) => void)[] = [];
vi.mock("@xterm/addon-web-links", () => ({ WebLinksAddon: class { constructor(handler: (event: MouseEvent, uri: string) => void) { linkHandlers.push(handler); } } }));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

const { AssistantPanel, CLI_INFO, EXAMPLE_PROMPTS, OPTIONS_KEY, EFFORT_TIP } = await import("../../src/renderer/pages/assistant/index");
const page = (await import("../../src/renderer/pages/assistant/index")).default;

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} disconnect() {} };
// Radix's select reads pointer capture, which jsdom lacks (same shim as help-popover.test.tsx).
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};
Element.prototype.scrollIntoView ??= () => {};

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
  const store = new Map<string, string>(); // this jsdom's localStorage has no clear()
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  });
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
  expect(container.textContent).toContain("nothing runs until you approve it on the Jobs page");
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
  expect(container.textContent).toContain("Not started");
  await act(async () => button("Start Claude Code").click());
  await settle();
  expect(bridge.start).toHaveBeenCalledWith("claude", 90, 20, { effort: "low", model: "sonnet" });
  expect(button("Restart")).toBeTruthy();
  expect(container.textContent).toContain("Running");
  act(() => listeners.forEach((l) => l({ cli: "claude", type: "data", data: "Welcome to Claude Code" })));
  act(() => listeners.forEach((l) => l({ cli: "codex", type: "data", data: "not mine" })));
  expect(written.filter((w) => w === "Welcome to Claude Code")).toHaveLength(1);
  act(() => button(EXAMPLE_PROMPTS[0]!.label).click());
  expect(bridge.write).toHaveBeenCalledWith("claude", EXAMPLE_PROMPTS[0]!.text);
  expect(EXAMPLE_PROMPTS[0]!.text).not.toMatch(/[\r\n]/);
  act(() => listeners.forEach((l) => l({ cli: "claude", type: "exit", code: 0 })));
  expect(written.some((w) => w.includes("exited with code 0"))).toBe(true);
  expect(container.textContent).toContain("Exited (code 0)");
  expect(button("Start Claude Code")).toBeTruthy();
});

it("says a session it stopped is stopped, not exited", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  await render(<AssistantPanel bridge={bridge} />);
  await act(async () => button("Start Claude Code").click());
  await settle();
  await act(async () => button("Stop").click());
  await settle();
  expect(bridge.kill).toHaveBeenCalledWith("claude");
  expect(container.textContent).toContain("Stopped");
  expect(button("Start Claude Code")).toBeTruthy();
});

it("opens a link the CLI printed through the app's http(s)-only openExternal", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  window.tit = { openExternal: vi.fn() } as unknown as TitBridge;
  linkHandlers.length = 0;
  await render(<AssistantPanel bridge={bridge} />);
  expect(linkHandlers).toHaveLength(2);
  linkHandlers[0]!(new MouseEvent("click"), "https://example.org/docs");
  expect(window.tit!.openExternal).toHaveBeenCalledWith("https://example.org/docs");
});

it("reports a failed start", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  bridge.start.mockResolvedValue({ ok: false, error: "The Assistant runs only with a TI-Toolbox on this computer." });
  await render(<AssistantPanel bridge={bridge} />);
  await act(async () => button("Start Claude Code").click());
  await settle();
  expect(container.textContent).toContain("only with a TI-Toolbox on this computer");
});

/** Radix's select opens on pointerdown and lists its options in a portal. */
async function choose(label: string, option: string) {
  const trigger = container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;
  await act(async () => {
    trigger.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, pointerType: "mouse" }));
  });
  const item = [...document.querySelectorAll<HTMLElement>("[role=option]")].find((el) => el.textContent === option)!;
  await act(async () => {
    item.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, button: 0, pointerType: "mouse" }));
    item.click();
  });
  await settle();
}
const trigger = (label: string) => container.querySelector(`button[aria-label="${label}"]`)?.textContent;

it("starts Claude Code on Low effort and Sonnet, and explains the effort choice", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  await render(<AssistantPanel bridge={bridge} />);
  expect(trigger("Effort")).toBe("Low (default)");
  expect(trigger("Model")).toBe("Sonnet (default)");
  expect(container.querySelector(`[title="${EFFORT_TIP}"]`)).toBeTruthy();
  expect(container.textContent).not.toContain("Applies on restart");
});

it("sends the chosen options on start, remembers them per CLI across mounts, and gives Codex no model menu", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  await render(<AssistantPanel bridge={bridge} />);
  await choose("Effort", "High");
  await choose("Model", "Opus");
  expect(JSON.parse(window.localStorage.getItem(OPTIONS_KEY)!).claude).toEqual({ effort: "high", model: "opus" });
  await act(async () => button("Start Claude Code").click());
  await settle();
  expect(bridge.start).toHaveBeenCalledWith("claude", 90, 20, { effort: "high", model: "opus" });
  await act(async () => button("Open in system terminal").click());
  expect(bridge.openInTerminal).toHaveBeenCalledWith("claude", { effort: "high", model: "opus" });

  act(() => [...container.querySelectorAll<HTMLButtonElement>("[role=radio]")].find((b) => b.textContent === "Codex")!.click());
  await settle();
  expect(trigger("Effort")).toBe("Low (default)");
  expect(trigger("Model")).toBeUndefined();
  await choose("Effort", "Medium");
  expect(JSON.parse(window.localStorage.getItem(OPTIONS_KEY)!)).toMatchObject({ claude: { effort: "high", model: "opus" }, codex: { effort: "medium", model: "default" } });

  act(() => root.unmount());
  root = createRoot(container);
  await render(<AssistantPanel bridge={bridge} />);
  expect(trigger("Effort")).toBe("High");
  expect(trigger("Model")).toBe("Opus");
});

it("ignores a stored value that is no longer on the menu", async () => {
  window.localStorage.setItem(OPTIONS_KEY, JSON.stringify({ claude: { effort: "bogus", model: "gpt" }, codex: { model: "opus" } }));
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  await render(<AssistantPanel bridge={bridge} />);
  expect(trigger("Effort")).toBe("Low (default)");
  expect(trigger("Model")).toBe("Sonnet (default)");
});

it("says a change applies on restart while a session runs, and not after the restart", async () => {
  makeBridge({ cli: "claude", installed: true, loggedIn: true, running: false });
  await render(<AssistantPanel bridge={bridge} />);
  await choose("Effort", "Low (default)");
  expect(container.textContent).not.toContain("Applies on restart");
  await act(async () => button("Start Claude Code").click());
  await settle();
  expect(container.textContent).not.toContain("Applies on restart");
  await choose("Effort", "High");
  expect(container.textContent).toContain("Applies on restart");
  await choose("Effort", "Low (default)");
  expect(container.textContent).not.toContain("Applies on restart");
  await choose("Model", "Haiku");
  expect(container.textContent).toContain("Applies on restart");
  await act(async () => button("Restart").click());
  await settle();
  expect(bridge.start).toHaveBeenLastCalledWith("claude", 90, 20, { effort: "low", model: "haiku" });
  expect(container.textContent).not.toContain("Applies on restart");
});
