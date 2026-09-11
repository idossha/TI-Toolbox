// Pins mailbox isolation and real sandbox process behavior using authored shell fixtures.
// Run: npx vitest run src/main/fastsurferWorker.test.ts (Apple Silicon integration leg).
import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdtemp, mkdir, writeFile, readFile, rm, stat, symlink, access } from "node:fs/promises";
import * as fs from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { FastSurferWorker, fastSurferSandbox } from "./fastsurferWorker";

vi.mock("node:fs/promises", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs/promises")>();
  return { ...actual, access: vi.fn(actual.access) };
});

const roots: string[] = [];
const workers: FastSurferWorker[] = [];
afterEach(async () => { for (const worker of workers.splice(0)) await worker.stop(); for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true }); });
const delay = (ms: number): Promise<void> => new Promise((done) => setTimeout(done, ms));
async function waitJson(path: string): Promise<Record<string, unknown>> {
  for (let n = 0; n < 150; n++) {
    try { return JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>; } catch { await delay(100); }
  }
  throw new Error(`Timed out: ${path}`);
}
async function fixture(script: string): Promise<{ worker: FastSurferWorker; project: string; mailbox: string; runtime: string }> {
  const root = await mkdtemp(join(tmpdir(), "tit-worker-test-")); roots.push(root);
  const runtime = join(root, "runtime"); const project = join(root, "project");
  await mkdir(runtime); await mkdir(project); await writeFile(join(project, "input.nii"), "fixture");
  await writeFile(join(runtime, "run_fastsurfer.sh"), script);
  const worker = new FastSurferWorker(); workers.push(worker);
  await worker.start(project, { sourceDir: runtime, pythonPath: "/usr/bin/true" });
  return { worker, project, runtime, mailbox: join(project, "code/ti-toolbox/native-fastsurfer") };
}
async function request(worker: FastSurferWorker, mailbox: string, overrides: Record<string, unknown> = {}): Promise<string> {
  const id = randomUUID(); const dir = join(mailbox, "requests", id); await mkdir(dir);
  await writeFile(join(dir, "request.json"), JSON.stringify({ version: 1, session: worker.status().session, id, subject_id: "101", threads: 2, input_path: "input.nii", ...overrides }));
  return dir;
}
const script = `#!/bin/bash
printf '%s\\n' "$@"
while [ "$#" -gt 0 ]; do case "$1" in --sd) sd="$2"; shift;; --sid) sid="$2"; shift;; esac; shift; done
mkdir -p "$sd/$sid/mri"
printf segmentation > "$sd/$sid/mri/aparc.DKTatlas+aseg.deep.mgz"
`;

describe("native worker sandbox profile", () => {
  it("denies networking and general writes and quotes paths", () => {
    const profile = fastSurferSandbox('/project/"quoted', "/mailbox", "/tmp/owned");
    expect(profile).toContain("(deny network*)"); expect(profile).toContain("(deny file-write*)"); expect(profile).toContain('\\"quoted');
  });
});
describe.skipIf(process.platform !== "darwin" || process.arch !== "arm64")("Apple Silicon worker (requires macOS sandbox-exec)", () => {
  it("runs fixed Metal arguments and verifies segmentation", async () => {
    const { worker, mailbox } = await fixture(script); const dir = await request(worker, mailbox);
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: true });
    const log = await readFile(join(dir, "stdout.log"), "utf8");
    expect(log).toContain("--device\nmps\n--viewagg_device\ncpu\n");
    expect(log).toContain("--seg_only\n--no_cereb\n--no_hypothal\n--no_cc");
  });
  it("rejects traversal and symlink inputs without running", async () => {
    const { worker, mailbox, project, runtime } = await fixture(script);
    await symlink(join(runtime, "run_fastsurfer.sh"), join(project, "escape.nii"));
    for (const input_path of ["../outside.nii", "escape.nii"]) {
      const dir = await request(worker, mailbox, { input_path }); const result = await waitJson(join(dir, "result.json"));
      expect(result.ok).toBe(false); await expect(access(join(dir, "stdout.log"))).rejects.toThrow();
    }
  });
  it("does not execute another session and removes its own availability", async () => {
    const { worker, mailbox } = await fixture(script); const dir = await request(worker, mailbox, { session: randomUUID() });
    await delay(1300); await expect(access(join(dir, "stdout.log"))).rejects.toThrow();
    await worker.stop(); await expect(access(join(mailbox, "availability.json"))).rejects.toThrow();
  });
  it("treats successful exit without output as failure", async () => {
    const { worker, mailbox } = await fixture("exit 0\n"); const dir = await request(worker, mailbox);
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: false, error: "FastSurfer exited without producing a segmentation" });
  });
  it("cancels a live process group", async () => {
    const { worker, mailbox } = await fixture("sleep 60 &\necho started:$!\nwait\n"); const dir = await request(worker, mailbox);
    for (let n = 0; n < 50; n++) { try { if ((await readFile(join(dir, "stdout.log"), "utf8")).includes("started")) break; } catch { /* Poll until spawned. */ } await delay(100); }
    const log = await readFile(join(dir, "stdout.log"), "utf8");
    const childPid = Number(log.match(/started:(\d+)/)?.[1]);
    expect(childPid).toBeGreaterThan(1);
    await writeFile(join(dir, "cancel"), "");
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: false, error: "Native FastSurfer cancelled" });
    expect(() => process.kill(childPid, 0)).toThrow();
  });
  it("kills a worker when its server heartbeat expires", async () => {
    const { worker, mailbox } = await fixture("echo started\nsleep 60 &\nwait\n"); const dir = await request(worker, mailbox);
    await writeFile(join(dir, "heartbeat.json"), JSON.stringify({ lastSeen: Date.now() - 20000 }));
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: false, error: "Native FastSurfer cancelled" });
  });
  it("protects existing subject outputs", async () => {
    const { worker, mailbox, project } = await fixture(script);
    await mkdir(join(project, "derivatives/fastsurfer/sub-101"), { recursive: true });
    const dir = await request(worker, mailbox);
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: false, error: "Native FastSurfer output already exists; refusing to overwrite" });
    await expect(access(join(dir, "stdout.log"))).rejects.toThrow();
  });
  it("does not publish a worker after stop revokes an in-flight start", async () => {
    const { worker, mailbox, project, runtime } = await fixture(script);
    let resume!: () => void;
    let entered!: () => void;
    const pending = new Promise<void>((done) => { resume = done; });
    const waiting = new Promise<void>((done) => { entered = done; });
    const original = (await vi.importActual<typeof import("node:fs/promises")>("node:fs/promises")).access;
    const spy = vi.mocked(fs.access).mockImplementationOnce(async (...args) => {
      entered(); await pending; return original(...args);
    });
    try {
      const starting = worker.start(project, { sourceDir: runtime, pythonPath: "/usr/bin/true" }).catch((error: unknown) => error);
      await waiting;
      const stopping = worker.stop();
      resume();
      expect(await starting).toEqual(new Error("Native FastSurfer start cancelled"));
      await stopping;
      expect(worker.status().running).toBe(false);
      expect(worker.status().session).toBeNull();
      await expect(access(join(mailbox, "availability.json"))).rejects.toThrow();
    } finally { resume(); spy.mockImplementation(original); }
  });
  it("publishes outputs only after completion and replaces log inodes", async () => {
    const { worker, mailbox, project } = await fixture(script + 'echo first\nsleep 3\necho final\n');
    const dir = await request(worker, mailbox);
    for (let n = 0; n < 50; n++) {
      try { await access(join(dir, "output/sub-101/mri/aparc.DKTatlas+aseg.deep.mgz")); break; } catch { await delay(100); }
    }
    await expect(access(join(project, "derivatives/fastsurfer/sub-101"))).rejects.toThrow();
    const initial = await stat(join(dir, "stdout.log"));
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: true });
    expect((await stat(join(dir, "stdout.log"))).ino).not.toBe(initial.ino);
    expect(await readFile(join(dir, "stdout.log"), "utf8")).toContain("final");
    expect(await readFile(join(project, "derivatives/fastsurfer/sub-101/mri/aparc.DKTatlas+aseg.deep.mgz"), "utf8")).toBe("segmentation");
  }, 10000);
  it("continues past malformed and symlink mailbox entries", async () => {
    const { worker, mailbox, runtime } = await fixture(script);
    await symlink(runtime, join(mailbox, "requests", "00000000-0000-0000-0000-000000000001"));
    const bad = join(mailbox, "requests", "00000000-0000-0000-0000-000000000002");
    await mkdir(bad); await writeFile(join(bad, "request.json"), "{");
    const dir = await request(worker, mailbox);
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: true });
  });
  it("creates upstream temporary logs only in its owned directory", async () => {
    const { worker, mailbox } = await fixture('mktemp\n' + script);
    const dir = await request(worker, mailbox);
    expect(await waitJson(join(dir, "result.json"))).toEqual({ ok: true });
    const log = await readFile(join(dir, "stdout.log"), "utf8");
    expect(log).toMatch(/ti-fastsurfer-[^/]+\/tmp\./);
    expect(log).not.toContain("Operation not permitted");
  });
  it("sandbox denies reading a different project", async () => {
    const { worker, mailbox, runtime } = await fixture('cat ../secret.txt\nexit 1\n');
    await writeFile(join(runtime, "../secret.txt"), "private");
    const dir = await request(worker, mailbox);
    expect((await waitJson(join(dir, "result.json"))).ok).toBe(false);
    const log = await readFile(join(dir, "stdout.log"), "utf8");
    expect(log).toContain("Operation not permitted"); expect(log).not.toContain("private");
  });
  it("sandbox denies writes outside the selected output", async () => {
    const { worker, mailbox, project } = await fixture('echo forbidden > ../project/forbidden\nexit 1\n'); const dir = await request(worker, mailbox);
    expect((await waitJson(join(dir, "result.json"))).ok).toBe(false);
    expect(await readFile(join(dir, "stdout.log"), "utf8")).toContain("Operation not permitted");
    await expect(access(join(project, "forbidden"))).rejects.toThrow();
  });
});
