// @vitest-environment jsdom
/**
 * The execution-policy grammar (IMPLEMENTATION_PLAN.md R3): one control, one meaning, and one
 * request shape.
 *
 * Two things are asserted here that a page-level test cannot:
 *
 * 1. `SubjectsInParallel` is the SAME control everywhere — so the tests below read its rendered
 *    label and testid rather than any page's copy of them, and a page that grew its own number
 *    box would not be covered by them.
 * 2. `submitJobGroup` sends ONE request for a whole batch. The pages used to loop
 *    `POST /api/jobs`, awaited per subject, and call that "sequential" — it decided nothing. The
 *    fetch spy below is what makes the difference visible: one call, one `parallel_subjects`,
 *    every subject inside it.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SubjectsInParallel, parallelSummary } from "../../src/renderer/pages/_shared/run/SubjectsInParallel";
import { createApi } from "../../src/renderer/api/client";
import { submitJobGroup } from "../../src/renderer/pages/_shared/run/jobGroups";

describe("parallelSummary — the words a collapsed section states", () => {
  it("calls a cap of 1 sequential, not '1 in parallel'", () => {
    expect(parallelSummary(1)).toBe("sequential");
  });

  it("states the cap past that", () => {
    expect(parallelSummary(4)).toBe("4 in parallel");
  });
});

describe("SubjectsInParallel — the one shared control", () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
  });

  function render(node: React.ReactElement): void {
    act(() => root.render(node));
  }

  it("renders one number input labelled 'Subjects in parallel'", () => {
    render(<SubjectsInParallel value={2} onChange={() => {}} subjectCount={3} />);
    const input = host.querySelector<HTMLInputElement>('[data-testid="subjects-in-parallel"]');
    expect(input).not.toBeNull();
    expect(input!.value).toBe("2");
    expect(host.textContent).toContain("Subjects in parallel");
    // The help is behind `Field`'s (i) trigger, so it is present as a trigger rather than as
    // text — what matters is that this control carries one at all.
    expect(host.querySelector(".field-help-trigger")).not.toBeNull();
  });

  it("caps the value at the number of selected subjects and floors it at 1", () => {
    const seen: number[] = [];
    render(<SubjectsInParallel value={1} onChange={(v) => seen.push(v)} subjectCount={2} />);
    const input = host.querySelector<HTMLInputElement>('[data-testid="subjects-in-parallel"]')!;
    expect(input.max).toBe("2");
    expect(input.min).toBe("1");
  });
});

describe("submitJobGroup — one request for the whole batch", () => {
  // Node's `Request` rejects a relative URL, so the client under test gets an absolute base —
  // the same shape `tests/unit/client.test.ts` uses.
  const fetchMock = vi.fn<(input: Request) => Promise<Response>>();
  const client = createApi({ baseUrl: "http://127.0.0.1:8765", fetch: (input) => fetchMock(input) });

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ group_id: "g1", jobs: [] }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
  });

  async function bodyOfOneCall(): Promise<Record<string, unknown>> {
    expect(fetchMock).toHaveBeenCalledTimes(1);
    return (await fetchMock.mock.calls[0]![0].clone().json()) as Record<string, unknown>;
  }

  it("sends every subject and the cap in a single POST /api/jobs/groups", async () => {
    await submitJobGroup("sim", { subject_id: "ernie" }, ["ernie", "101"], 2, {}, client);
    const url = fetchMock.mock.calls[0]![0].url;
    expect(url).toContain("/api/jobs/groups");
    const body = await bodyOfOneCall();
    expect(body).toMatchObject({ kind: "sim", subject_ids: ["ernie", "101"], parallel_subjects: 2 });
  });

  it("never substitutes client-side parallel POSTs for the cap", async () => {
    await submitJobGroup("flex", { subject_id: "ernie" }, ["ernie", "101", "102"], 1, {}, client);
    // Three subjects, one request: the sequencing is the server's, and there is no second call
    // for the renderer to space out, withhold, or race.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("carries per-subject configs, tags and overwrite when a page has them", async () => {
    await submitJobGroup("ex", { subject_id: "ernie" }, ["ernie", "101"], 2, {
      subjectConfigs: [
        { subject_id: "ernie", config: { subject_id: "ernie", leadfield_hdf: "/a" } },
        { subject_id: "101", config: { subject_id: "101", leadfield_hdf: "/b" } },
      ],
      tags: ["ex-batch"],
      overwrite: true,
    }, client);
    const body = await bodyOfOneCall();
    expect(body.subject_configs).toEqual([
      { subject_id: "ernie", config: { subject_id: "ernie", leadfield_hdf: "/a" } },
      { subject_id: "101", config: { subject_id: "101", leadfield_hdf: "/b" } },
    ]);
    expect(body.tags).toEqual(["ex-batch"]);
    expect(body.overwrite).toBe(true);
  });

  it("omits the optional fields entirely when a page has none", async () => {
    await submitJobGroup("mex", { subject_id: "ernie" }, ["ernie"], 1, {}, client);
    const body = await bodyOfOneCall();
    expect("subject_configs" in body).toBe(false);
    expect("tags" in body).toBe(false);
    expect("overwrite" in body).toBe(false);
  });
});
