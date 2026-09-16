/**
 * The once-per-project "Add example data?" decision, kept pure so it is testable without a DOM.
 *
 * The answer lives server-side in `project_status.json` (`GET/PATCH /api/project/status`), never in
 * localStorage: a project opened from another machine must not be asked twice, and a cleared
 * browser profile must not ask again either.
 *
 * **A fresh project has no `project_status.json` at all**, so `GET /api/project/status` can fail
 * (404 on some servers, an empty object on others) — which is exactly the project that most needs
 * asking. `statusForPrompt` turns "the read finished and found nothing" into `{}` so that case
 * prompts, and leaves only "still loading" as the reason not to.
 */
import type { components } from "../../api/schema";

export type ProjectStatus = components["schemas"]["ProjectStatus"];

export const EXAMPLE_DATA_PROMPT = {
  title: "Add example data?",
  body: "Learn TI-Toolbox and test every page before using your own data.",
  download: "Download selected",
  later: "Not now",
  /** Pre-ticked: the only part that runs the optimizer, simulator and analyzer immediately. */
  defaultPart: "ernie/headmodel",
} as const;

/** Result of the project-status read, as the prompt needs to see it. */
export type StatusRead =
  | { state: "loading" }
  | { state: "ready"; status: ProjectStatus }
  /** The project has no status file yet — a brand-new project, which is a project to ask. */
  | { state: "missing" };

export function statusForPrompt(read: StatusRead): ProjectStatus | undefined {
  if (read.state === "loading") return undefined;
  return read.state === "missing" ? {} : read.status;
}

/** True until the project has recorded an answer, or already holds example data. */
export function shouldPromptForExampleData(status: ProjectStatus | undefined): boolean {
  if (!status) return false; // not loaded yet — never flash a dialog on a guess
  if (status.example_subject_prompted === true) return false;
  return (status.example_subjects ?? []).length === 0 && (status.example_samples ?? []).length === 0;
}

export type PromptAnswer = "download" | "later";

/**
 * Persist the answer first, then act on it. The record is written for both answers so the chooser
 * is shown exactly once; a failed download does not re-arm it — Help ▸ Example data remains.
 *
 * The ticked parts are POSTed **one after another, in order**: the server runs one download at a
 * time and appends the rest to its worker queue, so the sequence here is the order they land in.
 */
export async function answerExampleDataPrompt(
  answer: PromptAnswer,
  partIds: readonly string[],
  deps: {
    persist: (patch: ProjectStatus) => Promise<unknown>;
    startDownload: (partId: string) => Promise<unknown>;
  },
): Promise<void> {
  await deps.persist({ example_subject_prompted: true });
  if (answer !== "download") return;
  for (const id of partIds) await deps.startDownload(id);
}
