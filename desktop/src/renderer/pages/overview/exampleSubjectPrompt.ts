/**
 * The once-per-project "Add the example subject?" decision, kept pure so it is testable without
 * a DOM. The answer lives server-side in `project_status.json` (`GET/PATCH /api/project/status`),
 * never in localStorage: a project opened from another machine must not be asked twice, and a
 * cleared browser profile must not ask again either.
 */
import type { components } from "../../api/schema";

export type ProjectStatus = components["schemas"]["ProjectStatus"];

export const EXAMPLE_SUBJECT_PROMPT = {
  title: "Add the example subject?",
  body:
    "Download the SimNIBS example subject ernie (≈1.1 GB, GPL-3.0) with a ready head model so you " +
    "can learn TI-Toolbox and test every page before using your own data.",
  download: "Download",
  later: "Not now",
} as const;

/** True until the project has recorded an answer, or already holds the example subject. */
export function shouldPromptForExampleSubject(status: ProjectStatus | undefined): boolean {
  if (!status) return false; // not loaded yet — never flash a dialog on a guess
  if (status.example_subject_prompted === true) return false;
  return !(status.example_subjects ?? []).includes("ernie");
}

export type PromptAnswer = "download" | "later";

/**
 * Persist the answer first, then act on it. The record is written for both answers so the dialog
 * is shown exactly once; a failed download does not re-arm it — the Overview button remains.
 */
export async function answerExampleSubjectPrompt(
  answer: PromptAnswer,
  deps: {
    persist: (patch: ProjectStatus) => Promise<unknown>;
    startDownload: () => Promise<unknown>;
  },
): Promise<void> {
  await deps.persist({ example_subject_prompted: true });
  if (answer === "download") await deps.startDownload();
}
