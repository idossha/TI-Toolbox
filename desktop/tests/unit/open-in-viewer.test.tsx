// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../../src/renderer/api/client";
import { useOpenInViewer, type ViewerLink } from "../../src/renderer/app/openInViewer";
import { notify } from "../../src/renderer/ui/Toast";

vi.mock("../../src/renderer/ui/Toast", () => ({ notify: { error: vi.fn() } }));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
let container: HTMLDivElement;
let open: (link: ViewerLink) => void;
const link: ViewerLink = { subject: "ernie", simulation: "motor", field: "TI_max" };
function Harness() { open = useOpenInViewer(); return null; }
beforeEach(async () => {
  container = document.createElement("div");
  root = createRoot(container);
  await act(async () => root.render(<Harness />));
});
afterEach(async () => { await act(async () => root.unmount()); vi.restoreAllMocks(); vi.clearAllMocks(); delete window.tit; });

it("launches the resolved scene directly with its exact subject, simulation and field", async () => {
  const request = vi.spyOn(api, "POST").mockResolvedValue({ data: { path: "/mnt/project/motor.tetravox.json" }, response: new Response() } as never);
  const launch = vi.fn().mockResolvedValue({ ok: true });
  window.tit = { openNativeTetravox: launch } as never;
  await act(async () => open(link));
  expect(request).toHaveBeenCalledWith("/api/view/open", { body: { kind: "simulation", subject: "ernie", simulation: "motor", field: "TI_max", path: undefined }, signal: undefined });
  expect(launch).toHaveBeenCalledWith("/mnt/project/motor.tetravox.json");
  // The action works without a router: opening a scene is not navigation.
  expect(notify.error).not.toHaveBeenCalled();
});

it("deduplicates an in-flight selection and allows retry after a visible native failure", async () => {
  vi.spyOn(api, "POST").mockResolvedValue({ data: { path: "/mnt/file.tetravox.json" }, response: new Response() } as never);
  let finish!: (value: { ok: boolean; reason: string }) => void;
  const launch = vi.fn(() => new Promise<{ ok: boolean; reason: string }>((resolve) => { finish = resolve; }));
  window.tit = { openNativeTetravox: launch } as never;
  await act(async () => { open(link); open(link); });
  expect(launch).toHaveBeenCalledTimes(1);
  await act(async () => finish({ ok: false, reason: "Install TetraVox first." }));
  expect(notify.error).toHaveBeenCalledWith("Could not open TetraVox: Install TetraVox first.");
  await act(async () => open(link));
  expect(launch).toHaveBeenCalledTimes(2);
  await act(async () => finish({ ok: true, reason: "" }));
});

it("preserves a specific artifact path and reports server errors without launching", async () => {
  const request = vi.spyOn(api, "POST").mockResolvedValue({ response: new Response(null, { status: 404 }) } as never);
  const launch = vi.fn(); window.tit = { openNativeTetravox: launch } as never;
  await act(async () => open({ subject: "101", path: "/mnt/anatomy.nii.gz" }));
  expect(request).toHaveBeenCalledWith("/api/view/open", expect.objectContaining({ body: expect.objectContaining({ kind: "custom", subject: "101", path: "/mnt/anatomy.nii.gz", files: ["/mnt/anatomy.nii.gz"] }) }));
  expect(launch).not.toHaveBeenCalled();
  expect(notify.error).toHaveBeenCalledWith(expect.stringContaining("HTTP 404"));
});
