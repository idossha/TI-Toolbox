/** The "Add the example subject?" dialog: shown once per project, both answers persisted server-side. */
import { describe, expect, it, vi } from "vitest";
import {
  answerExampleSubjectPrompt,
  shouldPromptForExampleSubject,
  type ProjectStatus,
} from "../../src/renderer/pages/overview/exampleSubjectPrompt";

describe("shouldPromptForExampleSubject", () => {
  it("waits for the status to load, then asks a fresh project", () => {
    expect(shouldPromptForExampleSubject(undefined)).toBe(false);
    expect(shouldPromptForExampleSubject({})).toBe(true);
    expect(shouldPromptForExampleSubject({ example_subject_prompted: null })).toBe(true);
  });

  it("never asks twice, and never asks a project that already has ernie", () => {
    expect(shouldPromptForExampleSubject({ example_subject_prompted: true })).toBe(false);
    expect(shouldPromptForExampleSubject({ example_subjects: ["ernie"] })).toBe(false);
  });
});

describe("answerExampleSubjectPrompt", () => {
  function fakeServer() {
    let status: ProjectStatus = {};
    const startDownload = vi.fn(async () => undefined);
    const persist = vi.fn(async (patch: ProjectStatus) => {
      status = { ...status, ...patch };
      return status;
    });
    return { persist, startDownload, read: () => status };
  }

  it("Download persists the answer and starts the job — once", async () => {
    const server = fakeServer();
    await answerExampleSubjectPrompt("download", server);
    expect(server.read().example_subject_prompted).toBe(true);
    expect(server.startDownload).toHaveBeenCalledTimes(1);
    expect(shouldPromptForExampleSubject(server.read())).toBe(false);
  });

  it("Not now persists the answer without downloading", async () => {
    const server = fakeServer();
    await answerExampleSubjectPrompt("later", server);
    expect(server.read().example_subject_prompted).toBe(true);
    expect(server.startDownload).not.toHaveBeenCalled();
    expect(shouldPromptForExampleSubject(server.read())).toBe(false);
  });

  it("persists before starting, so a failed download still counts as answered", async () => {
    const server = fakeServer();
    server.startDownload.mockRejectedValueOnce(new Error("offline"));
    await expect(answerExampleSubjectPrompt("download", server)).rejects.toThrow("offline");
    expect(server.read().example_subject_prompted).toBe(true);
  });
});
