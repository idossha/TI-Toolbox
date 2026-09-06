// @vitest-environment jsdom
import React, { act, useEffect, useMemo, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation, useNavigate, type NavigateFunction } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Circle } from "lucide-react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RetainedPages } from "../../src/renderer/app/RetainedPages";
import { Shell } from "../../src/renderer/app/Shell";
import { clearPageSession, usePageId, usePageSession } from "../../src/renderer/app/pageSession";
import { clearSubjectPages, useSubjectContext } from "../../src/renderer/app/subjectContext";
import { useSubjectSpine } from "../../src/renderer/app/subjectSpine";
import { usePageCommands, usePageCommandStore } from "../../src/renderer/app/commands";
import { useStatusCells, useStatusCellStore } from "../../src/renderer/app/statusCells";
import { useRunShortcut } from "../../src/renderer/pages/_shared/run/useRunShortcut";
import type { ResolvedPage } from "../../src/renderer/app/registry";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../../src/renderer/api/client", () => ({
  getProject: vi.fn(async () => ({ name: "retained", container_path: "/mnt/retained", host_path: null })),
  onUnauthorized: () => () => undefined,
}));
// The project-boundary test exercises Shell's real lifecycle with neutral chrome: launcher,
// telemetry and websocket widgets are outside this page-navigation boundary.
vi.mock("../../src/renderer/app/NavRail", () => ({ NavRail: () => null }));
vi.mock("../../src/renderer/app/AppContextBar", () => ({ AppContextBar: () => null }));
vi.mock("../../src/renderer/app/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("../../src/renderer/app/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("../../src/renderer/app/KeyboardSheet", () => ({ KeyboardSheet: () => null }));
vi.mock("../../src/renderer/app/QuickNotesHost", () => ({ QuickNotesHost: () => null }));
vi.mock("../../src/renderer/app/jobs-rail/JobsRail", () => ({ JobsRail: () => null, RUNNING_STATES: ["running"] }));
vi.mock("../../src/renderer/app/jobs/useJobsStream", () => ({ useJobsStream: () => ({ jobs: {} }) }));
vi.mock("../../src/renderer/app/connection", () => ({ useConnection: () => ({ degraded: false, reason: null }) }));
vi.mock("../../src/renderer/app/keyboard", () => ({ useGlobalShortcuts: () => undefined }));

const mounts: string[] = [];
const disposals: string[] = [];
const runs: string[] = [];
let navigate: NavigateFunction;

function PageProbe() {
  const id = usePageId();
  const location = useLocation();
  const subject = useSubjectContext((state) => state.subjectId);
  const setSubject = useSubjectContext((state) => state.setSubject);
  const [count, setCount] = useState(0);
  const [draft, setDraft] = usePageSession("draft", "empty");
  useEffect(() => {
    mounts.push(id);
    return () => { disposals.push(id); };
  }, [id]);
  useRunShortcut(() => runs.push(id));
  useStatusCells([{ id, value: count, priority: 10 }]);
  usePageCommands(useMemo(() => [{ id, label: `Run ${id}`, section: "Page" as const, run: () => runs.push(id) }], [id]));
  if (count < 0) throw new Error(`Invalid ${id} draft`);
  return <>
    <output data-subject={subject} data-search={location.search}>{count}:{draft}</output>
    <input aria-label={`${id} uncontrolled draft`} defaultValue="" />
    <button data-edit onClick={() => { setCount((value) => value + 1); setDraft("edited"); }}>Edit draft</button>
    <button data-subject-change onClick={() => setSubject("bert")}>Choose bert</button>
    <button data-error onClick={() => setCount(-1)}>Invalid draft</button>
    <iframe title={`${id} scene`} src="about:blank" />
  </>;
}

const pages: ResolvedPage[] = ["preprocess", "simulator", "viewer", "results"].map((id) => ({
  id, title: id, purpose: id, navGroup: "workflow", order: 0, icon: Circle, Component: PageProbe, enabled: true,
  section: "workflow", slot: id, hidden: false, subjectScoped: true, viewer: id === "viewer",
}));

function RouteControls() {
  navigate = useNavigate();
  useSubjectSpine();
  return null;
}

function NavigateProbe() {
  navigate = useNavigate();
  return null;
}

describe("retained workflow tabs", () => {
  let container: HTMLDivElement;
  let root: Root;
  let queryClient: QueryClient;

  beforeEach(() => {
    mounts.length = 0;
    disposals.length = 0;
    runs.length = 0;
    clearPageSession();
    clearSubjectPages();
    usePageCommandStore.setState({ byOwner: {} });
    useStatusCellStore.setState({ byOwner: {} });
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    queryClient.setQueryData(["project"], { name: "retained", container_path: "/mnt/retained", host_path: null });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    queryClient.clear();
    container.remove();
    vi.restoreAllMocks();
  });

  const panel = (id: string) => container.querySelector<HTMLElement>(`[data-page-panel="${id}"]`)!;
  const click = (id: string, selector: string) => act(() => panel(id).querySelector<HTMLButtonElement>(selector)!.click());
  const go = async (route: string, state?: Record<string, string>) => { await act(async () => { navigate(route, { state }); }); };
  const render = (epoch = 0) => act(() => root.render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/preprocess?subject=ernie"]}>
        <RouteControls />
        <RetainedPages key={epoch} pages={pages} />
      </MemoryRouter>
    </QueryClientProvider>,
  ));

  it("visits lazily and preserves local state, DOM nodes and the iframe browsing context", async () => {
    render();
    expect(mounts).toEqual(["preprocess"]);
    expect(panel("simulator")).toBeNull();
    click("preprocess", "[data-edit]");
    const input = panel("preprocess").querySelector("input")!;
    input.value = "unsaved input";
    const frame = panel("preprocess").querySelector("iframe")!;
    const frameWindow = frame.contentWindow;

    await go("/simulator");
    expect(panel("preprocess").hidden).toBe(true);
    expect(panel("preprocess").getAttribute("aria-hidden")).toBe("true");
    expect(panel("preprocess").hasAttribute("inert")).toBe(true);
    click("simulator", "[data-edit]");
    await go("/preprocess");

    expect(panel("preprocess").hidden).toBe(false);
    expect(panel("preprocess").hasAttribute("inert")).toBe(false);
    expect(panel("preprocess").querySelector("output")?.textContent).toBe("1:edited");
    expect(panel("preprocess").querySelector("input")).toBe(input);
    expect(input.value).toBe("unsaved input");
    expect(panel("preprocess").querySelector("iframe")).toBe(frame);
    expect(frame.contentWindow).toBe(frameWindow);
    expect(mounts).toEqual(["preprocess", "simulator"]);
    expect(disposals).toEqual([]);
  });

  it("gives only the active page keyboard, command and status ownership", async () => {
    render();
    await go("/simulator");
    await go("/viewer");
    act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true })));
    expect(runs).toEqual(["viewer"]);
    const commands = Object.values(usePageCommandStore.getState().byOwner).flat();
    expect(commands.map((command) => command.id)).toEqual(["viewer"]);
    expect(Object.values(useStatusCellStore.getState().byOwner).flat().map((cell) => cell.id)).toEqual(["viewer"]);
    commands[0]!.run();
    expect(runs).toEqual(["viewer", "viewer"]);
    await go("/preprocess");
    act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", metaKey: true, bubbles: true })));
    expect(runs).toEqual(["viewer", "viewer", "preprocess"]);
  });

  it("isolates subjects and route effects, and deliberately applies a destination deep link", async () => {
    render();
    await go("/viewer?subject=ernie&kind=simulation&simulation=Thalamus");
    const viewerSearch = panel("viewer").querySelector("output")!.dataset.search;
    await go("/simulator");
    click("simulator", "[data-subject-change]");
    expect(useSubjectContext.getState().subjectId).toBe("bert");
    expect(panel("preprocess").querySelector("output")!.dataset.subject).toBe("ernie");
    expect(panel("viewer").querySelector("output")!.dataset.subject).toBe("ernie");
    expect(panel("viewer").querySelector("output")!.dataset.search).toBe(viewerSearch);

    await go("/preprocess");
    expect(useSubjectContext.getState().subjectId).toBe("ernie");
    await go("/simulator");
    expect(useSubjectContext.getState().subjectId).toBe("bert");
    await go("/results");
    expect(panel("results").querySelector("output")!.dataset.subject).toBe("bert");
    await go("/viewer?subject=carl&kind=subject");
    expect(panel("viewer").querySelector("output")!.dataset.subject).toBe("carl");
    expect(panel("preprocess").querySelector("output")!.dataset.subject).toBe("ernie");
    expect(mounts.filter((id) => id === "viewer")).toHaveLength(1);
    await go("/results", { subject: "carl" });
    expect(panel("results").querySelector("output")!.dataset.subject).toBe("carl");
    expect(panel("preprocess").querySelector("output")!.dataset.subject).toBe("ernie");
  });

  it("keeps a page's error visible on return until the user retries", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const suppressExpected = (event: ErrorEvent) => {
      if (event.message === "Invalid preprocess draft") event.preventDefault();
    };
    window.addEventListener("error", suppressExpected);
    render();
    click("preprocess", "[data-error]");
    expect(panel("preprocess").textContent).toContain("Invalid preprocess draft");
    await go("/simulator");
    click("simulator", "[data-edit]");
    await go("/preprocess");
    expect(panel("preprocess").textContent).toContain("Invalid preprocess draft");
    expect(panel("simulator").querySelector("output")?.textContent).toBe("1:edited");
    window.removeEventListener("error", suppressExpected);
  });

  it("disposes every visited page and clears session drafts at a project boundary", async () => {
    act(() => root.render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/preprocess?subject=ernie"]}>
          <NavigateProbe />
          <Routes>
            <Route element={<Shell pages={pages} />}>
              {pages.map((page) => <Route key={page.id} path={`/${page.id}`} element={null} />)}
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ));
    click("preprocess", "[data-edit]");
    await go("/viewer");
    click("viewer", "[data-edit]");
    const oldFrame = panel("viewer").querySelector("iframe");
    await act(async () => {
      queryClient.setQueryData(["project"], { name: "another-project", container_path: "/mnt/another", host_path: null });
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
    expect(disposals).toEqual(["preprocess", "viewer"]);
    expect(panel("preprocess")).toBeNull();
    expect(panel("viewer").querySelector("output")?.textContent).toBe("0:empty");
    expect(panel("viewer").querySelector("iframe")).not.toBe(oldFrame);
    expect(useSubjectContext.getState().subjectId).toBeNull();
  });
});
