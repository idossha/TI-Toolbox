// @vitest-environment jsdom
/**
 * The EEG caps panel's "Add MNI cap…" flow when the name is taken (`pages/panels/caps/index.tsx`,
 * `onUpload`, p14, 2026-10-22).
 *
 * The route answers 409 for a name the project's caps already use (`tit/server/routes/caps.py`,
 * `upload`): the panel must ask, through the one existing-outputs dialog, rather than end on an
 * error toast. Replace resends the same file with `overwrite=true`; Skip and Cancel send nothing.
 * The route's other 409 — a cap the image ships, which overwrite never replaces — stays an error,
 * and the panel's caps list (`source`) is what tells the two apart.
 *
 * The page's api module is mocked at its network calls (`canReplaceUpload` is the real one);
 * every refusal below carries the route's own wording.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../src/renderer/api/client";
import type { CapStatus } from "../../src/renderer/pages/panels/caps/api";

const api = vi.hoisted(() => ({
  uploadCap: vi.fn(),
  getAvailableCaps: vi.fn(),
  inspectNet: vi.fn(),
  warpCaps: vi.fn(),
}));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), blocked: vi.fn() }));

vi.mock("../../src/renderer/api/client", async (original) => ({
  ...(await original<object>()),
  getSubjects: vi.fn(async () => [{ id: "ernie", has_raw: true, has_fastsurfer: false, has_freesurfer: false, has_m2m: true }]),
}));
vi.mock("../../src/renderer/pages/panels/caps/api", async (original) => ({ ...(await original<object>()), ...api }));
vi.mock("../../src/renderer/ui/Toast", async (original) => ({
  ...(await original<object>()),
  notify: toast,
  notifySubmitError: (message: string, error: unknown) => toast.error(message, error instanceof Error ? error.message : undefined),
}));
// The 3-D pane and scroll memory have their own tests; this file tests the upload flow.
vi.mock("../../src/renderer/pages/_shared/scene", () => ({ ScenePane: () => null }));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

const { default: page } = await import("../../src/renderer/pages/panels/caps/index");
const { clearPageSession } = await import("../../src/renderer/app/pageSession");

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

/** The route's 409 for a name the project's own caps already use. */
const PROJECT_TAKEN = new ApiError(409, "/api/caps/upload", "The project already has a cap named Mine.csv");
/** The route's 409 for a cap the image ships. */
const IMAGE_CAP = new ApiError(409, "/api/caps/upload", "EEG10-10.csv is a cap the image already ships; rename the file");

const cap = (name: string, source: CapStatus["source"]): CapStatus => ({ name, source, on_subject: false, subject_mtime: null });
const csv = (name: string) => new File(["Electrode,10,0,80,Fz\n"], name, { type: "text/csv" });

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

beforeEach(async () => {
  for (const fn of [...Object.values(api), ...Object.values(toast)]) fn.mockReset();
  api.getAvailableCaps.mockResolvedValue([cap("Mine.csv", "project"), cap("EEG10-10.csv", "simnibs")]);
  clearPageSession();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = page.Component;
  act(() => root.render(<QueryClientProvider client={client}><Panel /></QueryClientProvider>));
  await settle();
  // The caps list is what tells a project name from an image one: it must have loaded.
  expect(api.getAvailableCaps).toHaveBeenCalledWith("ernie");
  expect(container.querySelector('[data-testid="caps-table"]')?.textContent).toContain("EEG10-10");
});

afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
});

async function settle() {
  for (let i = 0; i < 5; i++) await act(async () => await new Promise((resolve) => setTimeout(resolve, 0)));
}

/** Pick *file* in the panel's hidden file input, as the "Add MNI cap…" button's chooser does. */
async function choose(file: File) {
  const input = container.querySelector<HTMLInputElement>('[data-testid="caps-upload-input"]')!;
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  await settle();
}

const button = (id: string) => document.querySelector<HTMLButtonElement>(`[data-testid="existing-outputs-${id}"]`);

async function press(id: string) {
  await act(async () => button(id)!.click());
  await settle();
}

describe("Add MNI cap with a name the project already uses", () => {
  it("adds a new name without overwrite", async () => {
    const file = csv("New.csv");
    api.uploadCap.mockResolvedValueOnce({ name: "New.csv", electrodes: 3 });
    await choose(file);
    expect(api.uploadCap.mock.calls).toEqual([[file, false]]);
    expect(toast.success).toHaveBeenCalledWith("Added New (3 electrodes) in this project's caps");
    expect(button("replace")).toBeNull();
  });

  it("asks, and Replace resends the same file with overwrite", async () => {
    const file = csv("Mine.csv");
    api.uploadCap.mockRejectedValueOnce(PROJECT_TAKEN).mockResolvedValueOnce({ name: "Mine.csv", electrodes: 4 });
    await choose(file);
    expect(api.uploadCap.mock.calls).toEqual([[file, false]]);
    expect(toast.error).not.toHaveBeenCalled();
    expect(button("replace")).not.toBeNull();
    expect(document.body.textContent).toContain("1 of 1 planned job already has EEG cap on disk.");

    const listed = api.getAvailableCaps.mock.calls.length;
    await press("replace");
    expect(api.uploadCap.mock.calls).toEqual([
      [file, false],
      [file, true],
    ]);
    expect(toast.success).toHaveBeenCalledWith("Replaced Mine (4 electrodes) in this project's caps");
    expect(toast.error).not.toHaveBeenCalled();
    expect(button("replace")).toBeNull();
    // The list is re-read, so the replaced cap's row is the server's.
    expect(api.getAvailableCaps.mock.calls.length).toBeGreaterThan(listed);
  });

  it("Skip sends nothing more and closes the dialog", async () => {
    api.uploadCap.mockRejectedValueOnce(PROJECT_TAKEN);
    await choose(csv("Mine.csv"));
    await press("skip");
    expect(api.uploadCap).toHaveBeenCalledTimes(1);
    expect(button("replace")).toBeNull();
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("Cancel sends nothing more and closes the dialog", async () => {
    api.uploadCap.mockRejectedValueOnce(PROJECT_TAKEN);
    await choose(csv("Mine.csv"));
    await press("cancel");
    expect(api.uploadCap).toHaveBeenCalledTimes(1);
    expect(button("replace")).toBeNull();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("a Replace the server refuses again ends on its reason, not on a second dialog", async () => {
    api.uploadCap.mockRejectedValueOnce(PROJECT_TAKEN).mockRejectedValueOnce(new ApiError(409, "/api/caps/upload", "Mine.csv is a cap the image already ships; rename the file"));
    await choose(csv("Mine.csv"));
    await press("replace");
    expect(api.uploadCap).toHaveBeenCalledTimes(2);
    expect(toast.error).toHaveBeenCalledWith("Could not add the cap.", "Mine.csv is a cap the image already ships; rename the file");
    expect(button("replace")).toBeNull();
  });

  it("a cap the image ships is an error with the server's reason, never a Replace", async () => {
    api.uploadCap.mockRejectedValueOnce(IMAGE_CAP);
    await choose(csv("EEG10-10.csv"));
    expect(api.uploadCap).toHaveBeenCalledTimes(1);
    expect(button("replace")).toBeNull();
    expect(toast.error).toHaveBeenCalledWith("Could not add the cap.", "EEG10-10.csv is a cap the image already ships; rename the file");
  });

  it("a refused file is an error with the validator's sentence", async () => {
    const reason = "Row 2: write the type exactly as Electrode; SimNIBS skips a row typed 'electrode'.";
    api.uploadCap.mockRejectedValueOnce(new ApiError(422, "/api/caps/upload", reason));
    await choose(csv("Mine.csv"));
    expect(button("replace")).toBeNull();
    expect(toast.error).toHaveBeenCalledWith("Could not add the cap.", reason);
  });
});
