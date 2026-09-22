/**
 * `submitJobGroup`: a batch is ONE `POST /api/jobs/groups` request. The pages used to loop
 * `POST /api/jobs` per subject; the fetch spy makes the difference visible — one call, every
 * subject inside it. There is no concurrency field: the server runs one job per product at a time
 * (docs/dev/DECISIONS.md 2026-09-22), so the retired `parallel_subjects` is never sent.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApi } from "../../src/renderer/api/client";
import { submitJobGroup } from "../../src/renderer/pages/_shared/run/jobGroups";

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

  it("sends every subject in a single POST /api/jobs/groups, with no concurrency field", async () => {
    await submitJobGroup("sim", { subject_id: "ernie" }, ["ernie", "101"], {}, client);
    const url = fetchMock.mock.calls[0]![0].url;
    expect(url).toContain("/api/jobs/groups");
    const body = await bodyOfOneCall();
    expect(body).toMatchObject({ kind: "sim", subject_ids: ["ernie", "101"] });
    expect("parallel_subjects" in body).toBe(false);
  });

  it("never substitutes client-side parallel POSTs for the server's one-at-a-time", async () => {
    await submitJobGroup("flex", { subject_id: "ernie" }, ["ernie", "101", "102"], {}, client);
    // Three subjects, one request: the sequencing is the server's, and there is no second call
    // for the renderer to space out, withhold, or race.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("carries per-subject configs, tags and overwrite when a page has them", async () => {
    await submitJobGroup("ex", { subject_id: "ernie" }, ["ernie", "101"], {
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
    await submitJobGroup("mex", { subject_id: "ernie" }, ["ernie"], {}, client);
    const body = await bodyOfOneCall();
    expect("subject_configs" in body).toBe(false);
    expect("tags" in body).toBe(false);
    expect("overwrite" in body).toBe(false);
  });
});
