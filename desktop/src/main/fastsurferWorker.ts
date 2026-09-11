import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { constants } from "node:fs";
import { access, copyFile, lstat, mkdir, mkdtemp, open, readFile, readdir, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

export interface FastSurferRuntime { sourceDir: string; pythonPath: string }
interface Request { version: number; session: string; id: string; subject_id: string; threads: number; input_path: string }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function inside(root: string, path: string): Promise<string> {
  const resolved = resolve(path);
  const rel = relative(root, resolved);
  if (rel.startsWith(`..${sep}`) || rel === ".." || isAbsolute(rel)) throw new Error("Path is outside the project");
  let cursor = root;
  for (const part of rel.split(sep).filter(Boolean)) {
    cursor = join(cursor, part);
    try {
      if ((await lstat(cursor)).isSymbolicLink()) throw new Error("Symlinks are not allowed in native worker paths");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
  return resolved;
}

async function exists(path: string): Promise<boolean> {
  try { await lstat(path); return true; } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

/** Computation may read installed libraries; writes are restricted to this job and networking is denied. */
export function fastSurferSandbox(output: string, mailbox: string, temporary: string, readRoots: string[] = []): string {
  const quote = (path: string): string => JSON.stringify(path);
  return `(version 1)\n(allow default)\n(deny network*)\n(deny file-read-data)\n(allow file-read-data (literal "/") ${["/System", "/usr", "/bin", "/sbin", "/Library", "/private/var/db", "/private/etc", "/dev", temporary, ...readRoots].map((path) => `(subpath ${quote(path)})`).join(" ")})\n(deny file-write*)\n(allow file-write* (subpath ${quote(output)}) (subpath ${quote(mailbox)}) (subpath ${quote(temporary)}) (literal "/dev/null"))\n`;
}

export class FastSurferWorker {
  private project = "";
  private mailbox = "";
  private session = "";
  private runtime: FastSurferRuntime | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private current: ChildProcess | null = null;
  private pumping: Promise<void> | null = null;
  private stopping = false;
  private error: string | null = null;
  private generation = 0;
  private lifecycle: Promise<void> = Promise.resolve();

  status(): { running: boolean; session: string | null; error: string | null } {
    return { running: this.timer !== null, session: this.session || null, error: this.error };
  }

  start(projectRoot: string, runtime: FastSurferRuntime): Promise<void> {
    const generation = ++this.generation;
    const operation = this.lifecycle.then(() => this.startInternal(projectRoot, runtime, generation));
    this.lifecycle = operation.catch(() => undefined);
    return operation;
  }

  private async startInternal(projectRoot: string, runtime: FastSurferRuntime, generation: number): Promise<void> {
    await this.halt();
    if (generation !== this.generation) throw new Error("Native FastSurfer start cancelled");
    if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("Native Metal FastSurfer requires Apple Silicon macOS");
    await access("/usr/bin/sandbox-exec", constants.X_OK);
    const sourceDir = await realpath(runtime.sourceDir);
    const pythonPath = resolve(runtime.pythonPath);
    await realpath(pythonPath);
    await access(join(sourceDir, "run_fastsurfer.sh"), constants.R_OK);
    await access(pythonPath, constants.X_OK);
    this.project = await realpath(projectRoot);
    this.mailbox = await inside(this.project, join(this.project, "code/ti-toolbox/native-fastsurfer"));
    await mkdir(join(this.mailbox, "requests"), { recursive: true });
    await inside(this.project, join(this.mailbox, "requests"));
    if (generation !== this.generation) throw new Error("Native FastSurfer start cancelled");
    this.runtime = { sourceDir, pythonPath };
    this.session = randomUUID();
    this.stopping = false;
    this.error = null;
    await this.heartbeat();
    if (generation !== this.generation) {
      await this.halt();
      throw new Error("Native FastSurfer start cancelled");
    }
    this.timer = setInterval(() => {
      if (!this.pumping) {
        this.pumping = this.tick().catch((error: unknown) => {
          this.error = error instanceof Error ? error.message : String(error);
        }).finally(() => { this.pumping = null; });
      }
    }, 1000);
  }

  private async atomic(path: string, value: unknown): Promise<void> {
    await inside(this.project, path);
    const temp = `${path}.${randomUUID()}.tmp`;
    await writeFile(temp, JSON.stringify(value), { flag: "wx", mode: 0o600 });
    await rename(temp, path);
  }

  private async heartbeat(): Promise<void> {
    await this.atomic(join(this.mailbox, "availability.json"), { version: 1, session: this.session, lastSeen: Date.now() });
  }

  private async tick(): Promise<void> {
    if (this.stopping) return;
    await this.heartbeat();
    const requests = await inside(this.project, join(this.mailbox, "requests"));
    for (const id of await readdir(requests)) {
      if (this.stopping) break;
      if (!UUID.test(id)) continue;
      let directory: string;
      let requestFile: string;
      try {
        directory = await inside(this.project, join(requests, id));
        if (!(await stat(directory)).isDirectory()) continue;
        if (await exists(join(directory, "result.json"))) continue;
        requestFile = await inside(this.project, join(directory, "request.json"));
        if (!(await exists(requestFile))) continue;
        if (!(await stat(requestFile)).isFile()) continue;
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error);
        continue;
      }
      try {
        if ((await stat(requestFile)).size > 8192) throw new Error("Native request is too large");
        const request = JSON.parse(await readFile(requestFile, "utf8")) as Request;
        if (request.session !== this.session) continue;
        await this.execute(request, id, directory);
      } catch (error) {
        try {
          await this.atomic(join(directory, "result.json"), { ok: false, error: error instanceof Error ? error.message : String(error) });
        } catch (writeError) {
          this.error = writeError instanceof Error ? writeError.message : String(writeError);
        }
      }
    }
  }

  private async execute(request: Request, id: string, directory: string): Promise<void> {
    if (request.version !== 1 || request.id !== id || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(request.subject_id)) throw new Error("Invalid native request identity");
    if (!Number.isInteger(request.threads) || request.threads < 1 || request.threads > 1024) throw new Error("Invalid thread count");
    if (typeof request.input_path !== "string" || isAbsolute(request.input_path) || request.input_path.includes("\\") || request.input_path.split("/").some((part) => part === ".." || part === ".") || !/\.nii(?:\.gz)?$/i.test(request.input_path)) throw new Error("Invalid project-relative NIfTI path");
    const input = await inside(this.project, join(this.project, request.input_path));
    if (!(await stat(input)).isFile()) throw new Error("Input is not a file");
    const outputRoot = await inside(this.project, join(this.project, "derivatives/fastsurfer"));
    const subject = request.subject_id.startsWith("sub-") ? request.subject_id : `sub-${request.subject_id}`;
    const output = await inside(this.project, join(outputRoot, subject));
    if (await exists(output)) throw new Error("Native FastSurfer output already exists; refusing to overwrite");
    if (await exists(join(directory, "cancel"))) throw new Error("Native FastSurfer cancelled");
    await mkdir(outputRoot, { recursive: true });
    const stagedRoot = await inside(this.project, join(directory, "output"));
    const stagedOutput = await inside(this.project, join(stagedRoot, subject));
    await mkdir(stagedOutput, { recursive: true });
    const temporary = await realpath(await mkdtemp(join(tmpdir(), "ti-fastsurfer-")));
    const runtime = this.runtime!;
    const profile = join(temporary, "worker.sb");
    const readRoots = [this.project, runtime.sourceDir, dirname(dirname(runtime.pythonPath)), dirname(dirname(await realpath(runtime.pythonPath)))];
    await writeFile(profile, fastSurferSandbox(stagedOutput, directory, temporary, readRoots));
    // Upstream expands --py unquoted, so a wrapper avoids splitting Application Support paths.
    const pythonWrapper = join(temporary, "python");
    const quotedPython = "'" + runtime.pythonPath.replaceAll("'", "'\\''") + "'";
    await writeFile(pythonWrapper, `#!/bin/sh\nexec ${quotedPython} "$@"\n`, { mode: 0o700 });
    // BSD mktemp ignores TMPDIR without a template; keep upstream temporary logs inside the sandbox.
    await writeFile(join(temporary, "mktemp"), '#!/bin/sh\nif [ "$#" -eq 0 ]; then exec /usr/bin/mktemp "$TMPDIR/tmp.XXXXXXXX"; fi\nexec /usr/bin/mktemp "$@"\n', { mode: 0o700 });
    const logPath = join(temporary, "worker.log");
    const log = await open(logPath, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    const snapshot = async (): Promise<void> => {
      const destination = await inside(this.project, join(directory, "stdout.log"));
      const staging = `${destination}.${randomUUID()}.tmp`;
      await copyFile(logPath, staging, constants.COPYFILE_EXCL);
      await rename(staging, destination);
    };
    let snapshotPending: Promise<void> = Promise.resolve();
    await snapshot();
    let cancelled = false;
    const started = Date.now();
    let cancelTimer: ReturnType<typeof setInterval> | undefined;
    let heartbeatTimer: ReturnType<typeof setInterval> | undefined;
    let snapshotTimer: ReturnType<typeof setInterval> | undefined;
    try {
      const child = spawn("/usr/bin/sandbox-exec", ["-f", profile, "/bin/bash", join(runtime.sourceDir, "run_fastsurfer.sh"), "--seg_only", "--no_cereb", "--no_hypothal", "--no_cc", "--sid", subject, "--sd", stagedRoot, "--t1", input, "--device", "mps", "--viewagg_device", "cpu", "--threads", String(request.threads), "--batch", "1", "--py", pythonWrapper], {
        cwd: runtime.sourceDir, detached: true, stdio: ["ignore", log.fd, log.fd],
        env: { PATH: `${temporary}:/usr/bin:/bin:/usr/sbin:/sbin`, HOME: temporary, TMPDIR: temporary, FASTSURFER_HOME: runtime.sourceDir, PYTHONPATH: runtime.sourceDir, PYTHONDONTWRITEBYTECODE: "1", PYTORCH_ENABLE_MPS_FALLBACK: "1" },
      });
      this.current = child;
      // Docker Desktop can cache an open bind-mount inode; publish each log snapshot by rename.
      snapshotTimer = setInterval(() => {
        snapshotPending = snapshotPending.then(snapshot).catch(() => { cancelled = true; this.kill(child); });
      }, 2000);
      cancelTimer = setInterval(() => {
        void (async () => {
          const cancel = await exists(join(directory, "cancel"));
          let lastSeen = started;
          const heartbeatPath = await inside(this.project, join(directory, "heartbeat.json"));
          if (await exists(heartbeatPath)) {
            const heartbeat = JSON.parse(await readFile(heartbeatPath, "utf8")) as { lastSeen?: number };
            if (typeof heartbeat.lastSeen !== "number" || !Number.isFinite(heartbeat.lastSeen)) throw new Error("Invalid requester heartbeat");
            lastSeen = Math.min(Date.now(), heartbeat.lastSeen);
          }
          return cancel || Date.now() - lastSeen > 15000;
        })().then((cancel) => {
          if ((cancel || this.stopping) && !cancelled) { cancelled = true; this.kill(child); }
        }).catch(() => { cancelled = true; this.kill(child); });
      }, 250);
      heartbeatTimer = setInterval(() => { void this.heartbeat().catch(() => { cancelled = true; this.kill(child); }); }, 2000);
      const code = await new Promise<number | null>((done, reject) => { child.once("error", reject); child.once("close", done); });
      if (cancelled || this.stopping) throw new Error("Native FastSurfer cancelled");
      if (code !== 0) throw new Error(`Native FastSurfer exited with code ${code}`);
      const segmentation = await inside(this.project, join(stagedOutput, "mri/aparc.DKTatlas+aseg.deep.mgz"));
      if (!(await exists(segmentation)) || (await stat(segmentation)).size === 0) throw new Error("FastSurfer exited without producing a segmentation");
      await inside(this.project, output);
      await inside(this.project, stagedOutput);
      if (await exists(output)) throw new Error("Native FastSurfer output already exists; refusing to overwrite");
      await rename(stagedOutput, output);
      if (snapshotTimer) clearInterval(snapshotTimer);
      await snapshotPending;
      await snapshot();
      await this.atomic(join(directory, "result.json"), { ok: true });
    } finally {
      if (cancelTimer) clearInterval(cancelTimer);
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      if (snapshotTimer) clearInterval(snapshotTimer);
      this.current = null;
      try {
        await snapshotPending;
        await snapshot();
      } finally {
        await log.close();
        await rm(temporary, { recursive: true, force: true });
      }
    }
  }

  private kill(child: ChildProcess): void {
    if (child.pid) {
      try { process.kill(-child.pid, "SIGKILL"); } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
      }
    }
  }

  stop(): Promise<void> {
    ++this.generation;
    this.stopping = true;
    if (this.current) this.kill(this.current);
    const operation = this.lifecycle.then(() => this.halt());
    this.lifecycle = operation.catch(() => undefined);
    return operation;
  }

  private async halt(): Promise<void> {
    this.stopping = true;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (this.current) this.kill(this.current);
    await this.pumping;
    try {
      if (this.session) {
        const path = await inside(this.project, join(this.mailbox, "availability.json"));
        if (await exists(path)) {
          const value = JSON.parse(await readFile(path, "utf8")) as { session?: string };
          if (value.session === this.session) await rm(path);
        }
      }
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
    } finally {
      this.session = "";
      this.runtime = null;
    }
  }
}
