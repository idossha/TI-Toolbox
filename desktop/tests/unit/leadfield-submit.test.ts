/**
 * The leadfield submission never replaces a file on its own (G1-5, 2026-11-01).
 *
 * The step's config always asks to compute (`overwrite: true`, else the runner keeps an existing
 * file whatever electrode was asked for); the REQUEST's `overwrite` is the user's answer to the
 * server's 409, so it is false until "Replace and rerun" and true only then.
 * Reproduce: cd desktop && npx vitest run tests/unit/leadfield-submit.test.ts
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const POST = vi.fn();
vi.mock("../../src/renderer/api/client", async (original) => ({
  ...(await original<object>()),
  api: { POST },
}));

const { submitLeadfieldJob, defaultLeadfieldElectrode } = await import("../../src/renderer/pages/optimizer/api");

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue({ data: { id: "j1" }, response: { ok: true, status: 201 } });
});

describe("submitLeadfieldJob", () => {
  it("sends the request's overwrite as false until the user answers the 409", async () => {
    await submitLeadfieldJob("ernie", "GSN-HydroCel-185", defaultLeadfieldElectrode());
    const body = POST.mock.calls[0]![1].body;
    expect(body.overwrite).toBe(false);
    expect(body).toMatchObject({ kind: "leadfield", subject_ids: ["ernie"], config: { overwrite: true } });
  });

  it("sends overwrite true only when 'Replace and rerun' resends it", async () => {
    await submitLeadfieldJob("ernie", "GSN-HydroCel-185", defaultLeadfieldElectrode(), true);
    expect(POST.mock.calls[0]![1].body.overwrite).toBe(true);
  });
});
