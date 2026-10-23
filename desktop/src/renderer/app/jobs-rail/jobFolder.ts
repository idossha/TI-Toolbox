/**
 * Which folder a job's folder button opens, and what it says it opens.
 *
 * The button used to open `code/ti-toolbox/jobs/<id>/` — the job's own bookkeeping record, where
 * its log and spec live — for any job that had not yet reported an artifact (every simulation and
 * search while it runs), and the *parent* of a finished simulation's or search's folder. A person
 * pressing the folder icon next to a run wants the folder the run writes its results into, so the
 * server now names it (`output_dir` on `GET /api/jobs/{id}`, `tit/server/job_outputs.py`: the
 * folder the runner registered, else the one the plan route resolves for the job's spec, else the
 * directory of its first registered file) and this module only chooses between that and the job's
 * own folder:
 *
 *   - the server named an output folder  → open it, "Open output folder";
 *   - it named none (a pre-processing stage with no folder of its own, a several-montage
 *     simulation, a folder the run has not created yet) → the job's own folder, "Open job folder",
 *     which always exists and is the one place its log and spec can be read.
 *
 * The renderer never builds a path convention: the job's folder is the directory of the `log_path`
 * the server gave. Nothing here maps container paths to host paths; the main process does, and
 * refuses a path outside the project (`src/shared/paths.ts`).
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { hasDotSegment } from "../../../shared/paths";
import { getJobOutputDir, TERMINAL_STATES, type JobStatus } from "./api";

export interface FolderTarget {
  /** Container path handed to the main process. */
  path: string;
  /** Which folder it is, so the label can say so. */
  kind: "output" | "job";
  /** The button's aria-label and tooltip. */
  label: string;
}

const OUTPUT_LABEL = "Open output folder";
const JOB_LABEL = "Open job folder";

/** An absolute container path with no `.`/`..` segment — the only shape worth handing to the shell. */
function isOpenable(path: string | null | undefined): path is string {
  return !!path && path.startsWith("/") && !hasDotSegment(path);
}

/** `code/ti-toolbox/jobs/<id>` — the directory of the job's log, or null when the server gave none. */
function jobRecordFolder(logPath: string | null | undefined): string | null {
  if (!logPath) return null;
  const cut = logPath.lastIndexOf("/");
  const folder = cut > 0 ? logPath.slice(0, cut) : null;
  return isOpenable(folder) ? folder : null;
}

/**
 * The folder the button opens for `job`, given the server's `output_dir` (null when it named none
 * or has not been asked yet), or null when there is nothing to open.
 */
export function folderTarget(job: Pick<JobStatus, "log_path">, outputDir: string | null | undefined): FolderTarget | null {
  if (isOpenable(outputDir)) return { path: outputDir, kind: "output", label: OUTPUT_LABEL };
  const folder = jobRecordFolder(job.log_path);
  return folder ? { path: folder, kind: "job", label: JOB_LABEL } : null;
}

/**
 * `folderTarget` for a live job. The server's answer changes while a job runs (the folder appears
 * when the run creates it, the runner registers it when it finishes), so it is asked again every
 * few seconds until the job is over and whenever its state or registered artifacts change; the
 * previous answer stays on screen meanwhile rather than flickering back to the job's own folder.
 */
export function useJobFolder(job: JobStatus | undefined): FolderTarget | null {
  const jobId = job?.id;
  const running = !!job && !TERMINAL_STATES.includes(job.state);
  const { data } = useQuery({
    queryKey: ["job-output-dir", jobId, job?.state, job?.artifacts.length ?? 0],
    queryFn: () => getJobOutputDir(jobId as string),
    enabled: !!jobId,
    staleTime: 5_000,
    refetchInterval: running ? 5_000 : false,
    placeholderData: (previous, query) => (query?.queryKey[1] === jobId ? previous : undefined),
  });
  return useMemo(() => (job ? folderTarget(job, data) : null), [job, data]);
}
