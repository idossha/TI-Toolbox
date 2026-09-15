/** The "Add example data?" chooser: shown once per project, both answers persisted server-side. */
import { describe, expect, it, vi } from "vitest";
import {
  answerExampleDataPrompt,
  shouldPromptForExampleData,
  statusForPrompt,
  type ProjectStatus,
} from "../../src/renderer/app/exampleData/prompt";

describe("statusForPrompt", () => {
  it("waits while the read is in flight", () => {
    expect(statusForPrompt({ state: "loading" })).toBeUndefined();
    expect(shouldPromptForExampleData(statusForPrompt({ state: "loading" }))).toBe(false);
  });

  /**
   * The defect: a brand-new project has no `project_status.json`, so `GET /api/project/status` can
   * 404 — and the old prompt read that as "do not ask", which silently skipped the one project
   * that most needs asking. "Read finished, found nothing" must prompt.
   */
  it("asks a project whose status file does not exist yet", () => {
    expect(statusForPrompt({ state: "missing" })).toEqual({});
    expect(shouldPromptForExampleData(statusForPrompt({ state: "missing" }))).toBe(true);
  });

  it("asks a project whose status file exists but records no answer", () => {
    expect(shouldPromptForExampleData(statusForPrompt({ state: "ready", status: {} }))).toBe(true);
    expect(
      shouldPromptForExampleData(
        statusForPrompt({ state: "ready", status: { example_subject_prompted: null } }),
      ),
    ).toBe(true);
  });
});

describe("shouldPromptForExampleData", () => {
  it("never asks twice, and never asks a project that already has example data", () => {
    expect(shouldPromptForExampleData({ example_subject_prompted: true })).toBe(false);
    expect(shouldPromptForExampleData({ example_subjects: ["ernie"] })).toBe(false);
    expect(shouldPromptForExampleData({ example_samples: ["mni152-t1"] })).toBe(false);
  });

  it("empty lists are not an answer — that project is still asked", () => {
    expect(shouldPromptForExampleData({ example_subjects: [], example_samples: [] })).toBe(true);
  });
});

describe("answerExampleDataPrompt", () => {
  function fakeServer() {
    let status: ProjectStatus = {};
    const startDownload = vi.fn(async (id: string) => void id);
    const persist = vi.fn(async (patch: ProjectStatus) => {
      status = { ...status, ...patch };
      return status;
    });
    return { persist, startDownload, read: () => status };
  }

  it("Download selected persists the answer and starts one job per ticked sample", async () => {
    const server = fakeServer();
    await answerExampleDataPrompt("download", ["ernie-headmodel", "mni152-t1"], server);
    expect(server.read().example_subject_prompted).toBe(true);
    expect(server.startDownload.mock.calls.map((c) => c[0])).toEqual([
      "ernie-headmodel",
      "mni152-t1",
    ]);
    expect(shouldPromptForExampleData(server.read())).toBe(false);
  });

  it("Not now persists the answer without downloading", async () => {
    const server = fakeServer();
    await answerExampleDataPrompt("later", ["ernie-headmodel"], server);
    expect(server.read().example_subject_prompted).toBe(true);
    expect(server.startDownload).not.toHaveBeenCalled();
    expect(shouldPromptForExampleData(server.read())).toBe(false);
  });

  it("persists before starting, so a failed download still counts as answered", async () => {
    const server = fakeServer();
    server.startDownload.mockRejectedValueOnce(new Error("offline"));
    await expect(
      answerExampleDataPrompt("download", ["ernie-headmodel"], server),
    ).rejects.toThrow("offline");
    expect(server.read().example_subject_prompted).toBe(true);
  });
});
