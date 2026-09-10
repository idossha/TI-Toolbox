// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OpenProject, SwitchProject } from "../../src/renderer/pages/overview/ProjectControls";

vi.mock("../../src/renderer/env", () => ({ isElectron: true }));
const start = vi.fn();
const switchProject = vi.fn();
const selectDirectory = vi.fn();
const unsubscribe = vi.fn();
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
let container: HTMLDivElement;
const input = () => container.querySelector<HTMLInputElement>("#project-dir")!;
const button = () => container.querySelector<HTMLButtonElement>("#start-stack")!;
const submit = () => { input().closest("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); };
function change(value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input(), value);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

beforeEach(() => {
  container = document.createElement("div"); document.body.appendChild(container);
  root = createRoot(container);
  start.mockReset().mockResolvedValue({ ok: true });
  switchProject.mockReset().mockResolvedValue({ ok: true });
  selectDirectory.mockReset();
  unsubscribe.mockReset();
  Object.defineProperty(window, "tit", { configurable: true, value: {
    getSettings: async () => ({ lastProjectDir: "/previous", theme: "dark" }),
    selectDirectory,
    stack: { start, switchProject, onEvent: () => unsubscribe },
  } });
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function showProjectForm() {
  await act(async () => root.render(createElement(OpenProject)));
  expect(input().value).toBe("/previous");
}

describe("Overview project selection", () => {
  it("opens a typed project path through form submission", async () => {
    await showProjectForm();
    expect(input().readOnly).toBe(false);
    change("  /different project  ");
    await act(async () => submit());
    expect(start).toHaveBeenCalledWith("/different project");
  });

  it("opens a picked folder and leaves the path editable", async () => {
    await showProjectForm();
    selectDirectory.mockResolvedValue("/picked");
    await act(async () => container.querySelector<HTMLButtonElement>("#browse")!.click());
    expect(input().value).toBe("/picked");
    await act(async () => button().click());
    expect(start).toHaveBeenCalledWith("/picked");
  });

  it("prevents empty paths and duplicate starts while opening", async () => {
    await showProjectForm();
    change("   ");
    expect(button().disabled).toBe(true);
    await act(async () => submit());
    expect(start).not.toHaveBeenCalled();
    change("/valid");
    start.mockReturnValue(new Promise(() => {}));
    await act(async () => submit());
    await act(async () => submit());
    expect(start).toHaveBeenCalledTimes(1);
    expect(input().disabled).toBe(true);
  });

  it("shows a failed start and restores controls for another attempt", async () => {
    await showProjectForm();
    start.mockResolvedValue({ ok: false, error: "Project folder does not exist" });
    await act(async () => button().click());
    expect(container.textContent).toContain("Project folder does not exist");
    expect(input().disabled).toBe(false);
    expect(button().disabled).toBe(false);
  });

  it("unsubscribes from stack progress when leaving Overview", async () => {
    await showProjectForm();
    act(() => root.render(null));
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });
});


describe("inline project switching", () => {
  async function expand() {
    await act(async () => root.render(createElement(SwitchProject)));
    await act(async () => container.querySelector<HTMLButtonElement>('[data-testid="switch-project"]')!.click());
  }

  it("lets users choose and cancel a destination without stopping the current project", async () => {
    await expand();
    expect(container.querySelector("#switch-project-dir")).not.toBeNull();
    const cancel = [...container.querySelectorAll("button")].find((el) => el.textContent === "Cancel")!;
    await act(async () => cancel.click());
    expect(container.querySelector("#switch-project-dir")).toBeNull();
    expect(switchProject).not.toHaveBeenCalled();
    expect(start).not.toHaveBeenCalled();
  });

  it("submits the picked destination to the guarded switch operation", async () => {
    await expand();
    selectDirectory.mockResolvedValue("/next project");
    await act(async () => container.querySelector<HTMLButtonElement>("#switch-project-browse")!.click());
    expect(container.querySelector<HTMLInputElement>("#switch-project-dir")!.value).toBe("/next project");
    expect(switchProject).not.toHaveBeenCalled();
    await act(async () => container.querySelector<HTMLButtonElement>("#switch-project-open")!.click());
    expect(switchProject).toHaveBeenCalledWith("/next project");
    expect(start).not.toHaveBeenCalled();
  });

  it("leaves the destination editable after a cancelled native confirmation", async () => {
    switchProject.mockResolvedValue({ ok: false, error: "Project switch cancelled." });
    await expand();
    await act(async () => container.querySelector<HTMLButtonElement>("#switch-project-open")!.click());
    expect(container.textContent).toContain("Project switch cancelled.");
    expect(container.querySelector<HTMLInputElement>("#switch-project-dir")!.disabled).toBe(false);
  });
});
