// @vitest-environment jsdom
/**
 * Settings → Viewer engine: the loop the maintainer asked for, in the UI.
 *
 * *"a system where we do not need to release a new version every time Tetravox updates"* —
 * so the assertions here are the four states a user actually moves through: what is running and
 * where it came from, what the index offers (with the digest that will be verified), install, and
 * roll back to the copy baked into the image. Plus the state that has no network at all, which
 * must read as a sentence and not as a failure (E2: an air-gapped install is supported).
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
// Type-only, so it is erased before `vi.mock` replaces the module at runtime -- and it pins every
// fixture below to the real contract shape, which is what stops a stale fixture from hiding a
// broken page (the failure mode `settings-warm-cache.test.tsx` records).
import type { TetravoxRelease, TetravoxState, TetravoxUpdates } from "../../src/renderer/pages/settings/api";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const BAKED: TetravoxRelease = {
  version: "0.3.4",
  protocol: 1,
  source: "baked" as const,
  path: "/opt/tetravox/embed",
  name: "@tetravox/embed",
  sha: "c56c3c8",
  features: ["cursor", "layers", "meshes", "probe", "screenshot", "volumes"],
  compatible: true,
  active: true,
};
const INSTALLED_040: TetravoxRelease = {
  version: "0.4.0",
  protocol: 2,
  source: "installed" as const,
  path: "/root/.config/ti-toolbox/tetravox/embed/0.4.0",
  name: "@tetravox/embed",
  sha: "0.4.0-mock",
  features: ["camera", "cursor", "layers", "markers", "meshes", "pick", "probe", "screenshot", "volumes"],
  compatible: true,
  active: true,
};
const SUPPORTED = { min: 1, max: 2 };
const ROOT = "/root/.config/ti-toolbox/tetravox/embed";

const bakedState: TetravoxState = {
  active: BAKED,
  reason: "the version baked into the image",
  installed: [],
  baked: BAKED,
  supported: SUPPORTED,
  install_root: ROOT,
  index_url: "https://example/releases.json",
  auto_update: true,
};
const installedState: TetravoxState = {
  active: INSTALLED_040,
  reason: "pinned to installed 0.4.0",
  installed: [INSTALLED_040],
  baked: { ...BAKED, active: false },
  supported: SUPPORTED,
  install_root: ROOT,
  index_url: "https://example/releases.json",
  auto_update: true,
};
const rolledBackState: TetravoxState = {
  ...installedState,
  active: BAKED,
  reason: "pinned to the version baked into the image",
  installed: [{ ...INSTALLED_040, active: false }],
  baked: BAKED,
};

const UPDATES_ONLINE: TetravoxUpdates = {
  available: true,
  message: null,
  index_url: "https://example/releases.json",
  auto_update: true,
  checked_at: Date.now() / 1000 - 120,
  from_cache: true,
  releases: [
    { version: "0.4.0", protocol: 2, url: "https://github.com/x/0.4.0.tgz", sha256: "b".repeat(64), notes: "Protocol 2: markers, pick, camera.", published: "2026-09-04", compatible: true, installed: false },
    { version: "9.0.0", protocol: 99, url: "https://github.com/x/9.0.0.tgz", sha256: "c".repeat(64), notes: null, published: null, compatible: false, installed: false },
  ],
};
const UPDATES_OFFLINE: TetravoxUpdates = {
  available: false,
  auto_update: true,
  checked_at: Date.now() / 1000 - 60,
  from_cache: true,
  message: "Could not reach the release index (https://example/releases.json): [Errno -3] Temporary failure in name resolution",
  index_url: "https://example/releases.json",
  releases: [],
};

// Typed with `vi.fn<signature>` rather than an inline `async (arg) => …`: it keeps `.mock.calls`
// typed (the assertions below read `calls[0][0]`) without declaring parameters the bodies never
// use, which lint rejects.
const getTetravox = vi.fn<() => Promise<TetravoxState>>(async () => bakedState);
const getTetravoxUpdates = vi.fn<(refresh?: boolean) => Promise<TetravoxUpdates>>(async () => UPDATES_ONLINE);
const setTetravoxPolicy = vi.fn<(autoUpdate: boolean) => Promise<TetravoxState>>(async () => ({ ...bakedState, auto_update: false }));
const installTetravox = vi.fn<(body: { url?: string; sha256?: string; version?: string }) => Promise<TetravoxState>>(async () => installedState);
const activateTetravox = vi.fn<(version: string) => Promise<TetravoxState>>(async () => rolledBackState);
const removeTetravox = vi.fn<(version: string) => Promise<TetravoxState>>(async () => bakedState);

vi.mock("../../src/renderer/pages/settings/api", () => ({
  getTetravox: () => getTetravox(),
  getTetravoxUpdates: (refresh?: boolean) => getTetravoxUpdates(refresh),
  setTetravoxPolicy: (autoUpdate: boolean) => setTetravoxPolicy(autoUpdate),
  installTetravox: (body: { version?: string }) => installTetravox(body),
  activateTetravox: (version: string) => activateTetravox(version),
  removeTetravox: (version: string) => removeTetravox(version),
}));
vi.mock("../../src/renderer/ui/Toast", () => ({ notify: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

let root: Root;
let container: HTMLDivElement;

async function mountCard() {
  const { TetravoxCard } = await import("../../src/renderer/pages/settings/TetravoxCard");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <TetravoxCard />
      </QueryClientProvider>,
    );
  });
  await settle();
}

async function settle() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

async function click(testid: string) {
  const el = container.querySelector<HTMLElement>(`[data-testid="${testid}"]`);
  if (!el) throw new Error(`no [data-testid="${testid}"] in\n${container.textContent}`);
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await settle();
}

const text = () => container.textContent ?? "";

beforeEach(() => {
  vi.clearAllMocks();
  getTetravox.mockResolvedValue(bakedState);
  getTetravoxUpdates.mockResolvedValue(UPDATES_ONLINE);
});

afterEach(() => {
  act(() => root?.unmount());
  document.body.innerHTML = "";
});

describe("Viewer engine card", () => {
  it("says what is running, where it came from, and what this app supports", async () => {
    await mountCard();
    expect(container.querySelector('[data-testid="tetravox-active-version"]')?.textContent).toBe("v0.3.4 · protocol 1");
    expect(text()).toContain("Baked into the image");
    expect(text()).toContain("protocol 1–2");
    expect(text()).toContain("the version baked into the image");
    expect(text()).toContain("Nothing installed yet");
  });

  it("reads the server's cached answer on mount and only asks the index when told to", async () => {
    // Rendering this page must never spend one of GitHub's 60 requests/hour, and must never tell
    // a remote host that this install exists; the cached read is served entirely by the server.
    await mountCard();
    expect(getTetravoxUpdates.mock.calls[0]?.[0]).toBe(false);
    await click("tetravox-check");
    expect(getTetravoxUpdates.mock.calls.at(-1)?.[0]).toBe(true);
  });

  it("says when the server last looked", async () => {
    await mountCard();
    expect(container.querySelector('[data-testid="tetravox-last-checked"]')?.textContent).toContain("Last checked: 2 min ago");
  });

  it("shows what the last automatic check decided, in the server's own words", async () => {
    getTetravoxUpdates.mockResolvedValue({
      ...UPDATES_ONLINE,
      last_outcome: {
        action: "unsupported",
        message: "Tetravox 9.0.0 speaks embed protocol 99, which this TI-Toolbox cannot host. Update TI-Toolbox to use it.",
        version: "9.0.0",
        protocol: 99,
        at: Date.now() / 1000,
      },
    });
    await mountCard();
    // A1: a release past the range is *reported*, never installed.
    expect(container.querySelector('[data-testid="tetravox-last-outcome"]')?.textContent).toContain("cannot host");
    expect(container.querySelector('[data-testid="tetravox-install-9.0.0"]')).toBeNull();
  });

  it("turns automatic updates off without turning the checking off", async () => {
    getTetravoxUpdates.mockResolvedValue({ ...UPDATES_ONLINE, auto_update: false });
    getTetravox.mockResolvedValue({ ...bakedState, auto_update: false });
    await mountCard();
    expect(container.querySelector<HTMLElement>("#tetravox-auto-update")?.getAttribute("data-state")).toBe("unchecked");
    // The list of what was found is still there, with an explicit Install for the compatible one.
    expect(container.querySelector('[data-testid="tetravox-install-0.4.0"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="tetravox-last-checked"]')?.textContent).toContain("Automatic installs are off");
  });

  it("shows each release with the digest that will be verified, and refuses the ones it cannot drive", async () => {
    await mountCard();
    expect(text()).toContain("Protocol 2: markers, pick, camera.");
    expect(text()).toContain(`sha256 ${"b".repeat(12)}…`);
    // A bundle needing a protocol past the supported range is listed but not installable.
    expect(container.querySelector('[data-testid="tetravox-install-9.0.0"]')).toBeNull();
    expect(text()).toContain("needs a newer app");
  });

  it("installs by version and shows the new bundle as active", async () => {
    await mountCard();
    await click("tetravox-install-0.4.0");
    // TanStack Query v5 passes a second (context) argument to `mutationFn`, so assert the
    // variables only — `toHaveBeenCalledWith` would be comparing its QueryClient too.
    expect(installTetravox.mock.calls[0]?.[0]).toEqual({ version: "0.4.0" });
    expect(container.querySelector('[data-testid="tetravox-active-version"]')?.textContent).toBe("v0.4.0 · protocol 2");
    expect(text()).toContain("Installed");
    expect(text()).toContain("pinned to installed 0.4.0");
  });

  it("rolls back to the baked bundle without deleting the installed one", async () => {
    getTetravox.mockResolvedValue(installedState);
    await mountCard();
    await click("tetravox-activate-baked");
    expect(activateTetravox.mock.calls[0]?.[0]).toBe("baked");
    expect(container.querySelector('[data-testid="tetravox-active-version"]')?.textContent).toBe("v0.3.4 · protocol 1");
    // Still installed, so going forward again is one click — the reason rollback is a pin and
    // not a delete.
    expect(container.querySelector('[data-testid="tetravox-activate-0.4.0"]')).not.toBeNull();
  });

  it("states plainly that there is no network, rather than showing an error", async () => {
    getTetravoxUpdates.mockResolvedValue(UPDATES_OFFLINE);
    await mountCard();
    const offline = container.querySelector('[data-testid="tetravox-offline"]');
    expect(offline?.textContent).toContain("Could not reach the release index");
    expect(offline?.textContent).toContain("The viewer keeps working");
    expect(container.querySelector(".callout-danger")).toBeNull();
  });

  it("warns when the active bundle is outside the supported protocol range", async () => {
    getTetravox.mockResolvedValue({
      ...bakedState,
      active: { ...BAKED, version: "9.0.0", protocol: 99, compatible: false, source: "installed" },
    });
    await mountCard();
    expect(container.querySelector(".callout-danger")?.textContent).toContain("outside the supported range");
  });
});
