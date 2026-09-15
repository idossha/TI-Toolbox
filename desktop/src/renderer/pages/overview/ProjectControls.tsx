import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Layers, Target, Waves, ChartNoAxesCombined, Box, Download } from "lucide-react";
import { Button } from "../../ui/Button";
import { Callout } from "../../ui/Feedback";
import { Dialog } from "../../ui/Overlay";
import { isElectron } from "../../env";
import { api, unwrap } from "../../api/client";
import { subscribeJob, useJobsStream } from "../../app/jobs/useJobsStream";
import { TERMINAL_STATES } from "../../app/jobs-rail/api";
import {
  EXAMPLE_SUBJECT_PROMPT,
  answerExampleSubjectPrompt,
  shouldPromptForExampleSubject,
  type ProjectStatus,
  type PromptAnswer,
} from "./exampleSubjectPrompt";

function ProjectDirectoryForm({ switching = false, onCancel }: { switching?: boolean; onCancel?: () => void }) {
  const inputId = switching ? "switch-project-dir" : "project-dir";
  const [directory, setDirectory] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState(() => switching ? "" : new URLSearchParams(window.location.search).get("error") ?? "");
  const edited = useRef(false);

  useEffect(() => {
    let mounted = true;
    void window.tit!.getSettings().then((settings) => {
      if (mounted && !edited.current) setDirectory(settings.lastProjectDir ?? "");
    }).catch(() => { /* A missing saved path does not prevent opening a project. */ });
    const unsubscribe = window.tit!.stack.onEvent((event) => {
      if (event.type === "progress") setProgress(event.message);
      if (event.type === "error") setError(event.message);
    });
    return () => { mounted = false; unsubscribe(); };
  }, []);

  async function browse() {
    setError("");
    try {
      const path = await window.tit!.selectDirectory();
      if (path) { edited.current = true; setDirectory(path); }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not open the directory picker.");
    }
  }

  async function open(event: FormEvent) {
    event.preventDefault();
    if (busy || !directory.trim()) return;
    setBusy(true);
    setError("");
    setProgress("Opening project…");
    try {
      const result = switching
        ? await window.tit!.stack.switchProject(directory.trim())
        : await window.tit!.stack.start(directory.trim());
      if (!result.ok) { setError(result.error); setProgress(""); }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not open the project.");
      setProgress("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="overview-project-form" onSubmit={(event) => void open(event)}>
      <label htmlFor={inputId}>Project directory</label>
      <div className="overview-project-path">
        <input id={inputId} value={directory} placeholder="/path/to/project" disabled={busy}
          aria-describedby={`${inputId}-hint`}
          onChange={(event) => { edited.current = true; setDirectory(event.target.value); }} />
        <Button id={switching ? "switch-project-browse" : "browse"} disabled={busy} onClick={() => void browse()}>Browse…</Button>
      </div>
      <p id={`${inputId}-hint`} className="overview-project-hint">
        {switching
          ? "Choose the next project first. Your current project stays open until you confirm the switch."
          : "Select the folder containing your project's data. Docker must be running to open it."}
      </p>
      <div className="overview-project-actions">
        <Button id={switching ? "switch-project-open" : "start-stack"} type="submit" variant="primary" disabled={busy || !directory.trim()}>
          {busy ? "Opening project…" : switching ? "Switch to project" : "Open project"}
        </Button>
        {onCancel && <Button disabled={busy} onClick={onCancel}>Cancel</Button>}
      </div>
      {progress && <p role="status" className="overview-project-progress">{progress}</p>}
      {error && <Callout kind="danger">{error}</Callout>}
    </form>
  );
}

const workflows = [
  { title: "Prepare", description: "Build head models from your imaging data.", icon: Layers },
  { title: "Optimize", description: "Find electrode configurations for your target.", icon: Target },
  { title: "Simulate", description: "Compute temporal interference electric fields.", icon: Waves },
  { title: "Analyze", description: "Measure field strength and focality.", icon: ChartNoAxesCombined },
  { title: "Visualize", description: "Explore anatomy and results in the 3D viewer.", icon: Box },
];

/** The desktop's Overview before a project is open; no server reads are needed. */
export function OpenProject() {
  return (
    <div className="overview-welcome">
      <header className="overview-welcome-heading">
        <span className="overview-eyebrow">Temporal interference research</span>
        <h1>Welcome to TI-Toolbox</h1>
        <p>From imaging data to stimulation insights, your project brings every step together.</p>
      </header>
      <section className="overview-open-project" aria-labelledby="open-project-heading">
        <div className="overview-open-heading">
          <FolderOpen size={22} aria-hidden />
          <div><h2 id="open-project-heading">Open a project</h2><p>Start with a project directory on your computer.</p></div>
        </div>
        <ProjectDirectoryForm />
      </section>
      <section className="overview-workflows" aria-labelledby="overview-workflows-heading">
        <h2 id="overview-workflows-heading">Your research workflow</h2>
        <div className="overview-workflow-list">
          {workflows.map(({ title, description, icon: Icon }) => (
            <div className="overview-workflow" key={title}>
              <Icon size={19} aria-hidden />
              <h3>{title}</h3>
              <p>{description}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

/**
 * `POST /api/project/example-subject`: a `project_init` job that runs `tit.examples.fetch_ernie`
 * (the notebook's cell 1 and `python -m tit.examples` are the same call). Progress is the job's
 * own stream — the same `/ws/jobs` store the rail reads — so nothing here polls. Shared by the
 * toolbar button and the once-per-project dialog so both report on the same job.
 */
function useExampleSubjectJob() {
  const queryClient = useQueryClient();
  const { jobs, eventsByJob } = useJobsStream();
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const job = jobId ? jobs[jobId] : undefined;
  const running = !!job && !TERMINAL_STATES.includes(job.state);
  const lastLog = jobId ? [...(eventsByJob[jobId] ?? [])].reverse().find((e) => e.type === "log")?.msg : undefined;

  useEffect(() => {
    if (job && TERMINAL_STATES.includes(job.state)) void queryClient.invalidateQueries({ queryKey: ["overview"] });
  }, [job, queryClient]);

  async function start() {
    setError("");
    try {
      const status = unwrap(await api.POST("/api/project/example-subject", { body: {} }), "/api/project/example-subject");
      setJobId(status.id);
      subscribeJob(status.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start the download.");
      throw cause;
    }
  }

  return { start, running, job, lastLog, error };
}

export function AddExampleSubject() {
  const { start, running, job, lastLog, error } = useExampleSubjectJob();
  return (
    <div className="overview-example-subject">
      <Button data-testid="add-example-subject" disabled={running} onClick={() => start().catch(() => undefined)}>
        <Download size={14} aria-hidden /> {running ? "Adding example subject…" : "Add example subject (ernie, ~1.1 GB download)"}
      </Button>
      {job && <p role="status" className="overview-project-progress">{job.state}{job.progress ? ` · ${Math.round(job.progress.pct)}%` : ""}{lastLog ? ` · ${lastLog}` : ""}</p>}
      {error && <Callout kind="danger">{error}</Callout>}
    </div>
  );
}

async function getProjectStatus(): Promise<ProjectStatus> {
  return unwrap(await api.GET("/api/project/status"), "/api/project/status");
}

async function patchProjectStatus(patch: ProjectStatus): Promise<ProjectStatus> {
  return unwrap(await api.PATCH("/api/project/status", { body: patch }), "/api/project/status");
}

/**
 * Asked once per project, the first time its Overview loads: the answer is recorded in the
 * project's own `project_status.json` (`example_subject_prompted`), so it follows the project,
 * not the browser. Closing the dialog any other way counts as "Not now".
 */
export function ExampleSubjectPrompt() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({ queryKey: ["project-status"], queryFn: getProjectStatus });
  const { start } = useExampleSubjectJob();
  const [answered, setAnswered] = useState(false);
  const open = !answered && shouldPromptForExampleSubject(statusQuery.data);

  function answer(choice: PromptAnswer) {
    setAnswered(true);
    void answerExampleSubjectPrompt(choice, { persist: patchProjectStatus, startDownload: start })
      .catch(() => undefined)
      .finally(() => queryClient.invalidateQueries({ queryKey: ["project-status"] }));
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => { if (!next) answer("later"); }}
      title={EXAMPLE_SUBJECT_PROMPT.title}
      description={EXAMPLE_SUBJECT_PROMPT.body}
      footer={
        <>
          <Button variant="secondary" data-testid="example-subject-later" onClick={() => answer("later")}>
            {EXAMPLE_SUBJECT_PROMPT.later}
          </Button>
          <Button data-testid="example-subject-download" onClick={() => answer("download")}>
            <Download size={14} aria-hidden /> {EXAMPLE_SUBJECT_PROMPT.download}
          </Button>
        </>
      }
    />
  );
}

/** Selecting a destination is reversible; main confirms before stopping the current project. */
export function SwitchProject() {
  const [expanded, setExpanded] = useState(false);
  if (!isElectron) return null;
  return (
    <div className="overview-project-controls">
      {expanded ? (
        <section className="overview-switch-project" aria-labelledby="switch-project-heading">
          <h2 id="switch-project-heading">Switch project</h2>
          <ProjectDirectoryForm switching onCancel={() => setExpanded(false)} />
        </section>
      ) : (
        <Button data-testid="switch-project" onClick={() => setExpanded(true)}>Switch project</Button>
      )}
    </div>
  );
}
