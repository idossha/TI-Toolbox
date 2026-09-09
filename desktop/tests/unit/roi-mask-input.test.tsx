// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RoiPicker } from "../../src/renderer/pages/_shared/roi/RoiPicker";
import type { RoiValue } from "../../src/renderer/pages/_shared/roi/types";

const upload = vi.hoisted(() => vi.fn());
vi.mock("../../src/renderer/pages/_shared/roi/api", async (original) => ({
  ...await original<object>(), uploadMask: upload,
}));
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
let container: HTMLDivElement;
const change = vi.fn();
const mask: RoiValue = { mode: "mask", path: "/existing.nii", space: "mni", tissues: "GM" };
beforeEach(() => {
  upload.mockReset(); change.mockReset();
  container = document.createElement("div"); document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });
function render(disabled = false, subject: string | undefined = "101") {
  act(() => root.render(<RoiPicker value={mask} onChange={change} modes={["mask"]} subject={subject} disabled={disabled} />));
}
function pathInput() { return container.querySelector<HTMLInputElement>('input[aria-label="Imported mask"]')!; }
async function drop(files: File[]) {
  const event = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", { value: { files } });
  await act(async () => pathInput().dispatchEvent(event));
  expect(event.defaultPrevented).toBe(true);
}
it("accepts typed server paths without uploading, retaining mask space and tissues", () => {
  render();
  const input = pathInput();
  expect(input.readOnly).toBe(false);
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "/mnt/project/new mask.nii.gz");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(change).toHaveBeenCalledWith({ ...mask, path: "/mnt/project/new mask.nii.gz" });
  expect(upload).not.toHaveBeenCalled();
});
it.each(["target.nii", "target.nii.gz"])("uploads a dropped %s and uses the server path", async (name) => {
  upload.mockResolvedValue("/mnt/project/imported.nii.gz"); render();
  const file = new File(["mask bytes"], name);
  await drop([file]);
  expect(upload).toHaveBeenCalledWith(file, "101", expect.any(AbortSignal));
  expect(change).toHaveBeenCalledWith({ ...mask, path: "/mnt/project/imported.nii.gz" });
});
it("rejects unrelated gzip and multi-file drops without replacing the mask", async () => {
  render();
  await drop([new File(["not nifti"], "archive.gz")]);
  expect(container.textContent).toContain("Choose a .nii or .nii.gz NIfTI mask.");
  await drop([new File([], "one.nii"), new File([], "two.nii")]);
  expect(container.textContent).toContain("Drop one .nii or .nii.gz NIfTI mask.");
  expect(upload).not.toHaveBeenCalled(); expect(change).not.toHaveBeenCalled();
});
it("blocks drops and editing when disabled and blocks duplicate uploads", async () => {
  render(true);
  expect(pathInput().disabled).toBe(true);
  await drop([new File([], "target.nii")]);
  expect(upload).not.toHaveBeenCalled();
  let resolve!: (path: string) => void;
  upload.mockImplementation(() => new Promise<string>((done) => { resolve = done; }));
  render(); await drop([new File([], "target.nii")]);
  expect(pathInput().disabled).toBe(true);
  await drop([new File([], "other.nii")]);
  expect(upload).toHaveBeenCalledTimes(1);
  await act(async () => resolve("/mnt/imported.nii"));
  expect(pathInput().disabled).toBe(false);
});
it("shows upload failures and preserves the prior path", async () => {
  upload.mockRejectedValue(new Error("Mask contains no positive voxels")); render();
  await drop([new File([], "empty.nii")]);
  expect(container.textContent).toContain("Mask contains no positive voxels");
  expect(pathInput().value).toBe(mask.path);
  expect(change).not.toHaveBeenCalled(); expect(pathInput().disabled).toBe(false);
});
