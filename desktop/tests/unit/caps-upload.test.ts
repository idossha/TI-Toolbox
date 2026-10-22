/**
 * The EEG caps panel's upload call (`pages/panels/caps/api.ts`, `uploadCap`) against the route's
 * documented answers (`tit/server/routes/caps.py`, `upload`, 2026-10-22, p14):
 *
 * - 422 with a string `detail` (the cap validator's row message) is shown as that sentence;
 * - 422 with FastAPI's list `detail` — what the `EntityName` rule answers for a file name such as
 *   `MyCap (1).csv` or `Kappe_ü.csv` (body captured from the real server with a TestClient) — is
 *   shown as the rule, not as "failed with HTTP 422";
 * - 409 "The project already has a cap named …" can be replaced: Replace resends the same file with
 *   `overwrite=true`; 409 "… is a cap the image already ships" cannot (overwrite never replaces an
 *   image cap), and the panel's caps list is what tells the two apart.
 *
 * `fetch` is stubbed; every response body below is the server's own wording.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../src/renderer/api/client";
import { canReplaceUpload, uploadCap, type CapStatus } from "../../src/renderer/pages/panels/caps/api";

/** FastAPI's 422 for `?name=MyCap (1).csv`, from `POST /api/caps/upload` on the real app. */
const NAME_RULE_422 = {
  detail: [
    {
      type: "value_error",
      loc: ["query", "name"],
      msg: "Value error, invalid name 'MyCap (1).csv': letters, digits, '.', '_', '-' and inner spaces only, not starting with '.', at most 128 characters",
      input: "MyCap (1).csv",
      ctx: { error: {} },
    },
  ],
};

const csv = (name: string) => new File(["Electrode,10,0,80,Fz\n"], name, { type: "text/csv" });

function answer(status: number, body: unknown) {
  const fetcher = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

async function refusal(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

const cap = (name: string, source: CapStatus["source"]): CapStatus => ({ name, source, on_subject: false, subject_mtime: null });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("uploadCap", () => {
  it("sends the file under its name, without overwrite unless asked", async () => {
    const fetcher = answer(201, { name: "My Cap.csv", electrodes: 1 });
    expect(await uploadCap(csv("My Cap.csv"))).toEqual({ name: "My Cap.csv", electrodes: 1 });
    const url = new URL(fetcher.mock.calls[0]![0], "http://x");
    expect(url.pathname).toBe("/api/caps/upload");
    expect(url.searchParams.get("name")).toBe("My Cap.csv");
    expect(url.searchParams.has("overwrite")).toBe(false);
    expect(fetcher.mock.calls[0]![1]?.method).toBe("POST");
  });

  it("asks the server to replace when overwrite is set", async () => {
    const fetcher = answer(201, { name: "Mine.csv", electrodes: 3 });
    await uploadCap(csv("Mine.csv"), true);
    const url = new URL(fetcher.mock.calls[0]![0], "http://x");
    expect(url.searchParams.get("name")).toBe("Mine.csv");
    expect(url.searchParams.get("overwrite")).toBe("true");
  });

  it("shows the validator's sentence for a refused file", async () => {
    answer(422, { detail: "Row 2: write the type exactly as Electrode; SimNIBS skips a row typed 'electrode'." });
    const error = await refusal(uploadCap(csv("x.csv")));
    expect(error.status).toBe(422);
    expect(error.message).toBe("Row 2: write the type exactly as Electrode; SimNIBS skips a row typed 'electrode'.");
  });

  it("shows the name rule for a file name the server refuses", async () => {
    answer(422, NAME_RULE_422);
    const error = await refusal(uploadCap(csv("MyCap (1).csv")));
    expect(error.status).toBe(422);
    expect(error.message).not.toMatch(/HTTP 422/);
    expect(error.message).not.toMatch(/^Value error/);
    expect(error.message).toContain("invalid name 'MyCap (1).csv'");
    expect(error.message).toContain("letters, digits, '.', '_', '-' and inner spaces only");
  });

  it("falls back to the status when the body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502 })));
    const error = await refusal(uploadCap(csv("x.csv")));
    expect(error.message).toBe("/api/caps/upload failed with HTTP 502");
  });
});

describe("canReplaceUpload", () => {
  const projectTaken = () => refusal((answer(409, { detail: "The project already has a cap named Mine.csv" }), uploadCap(csv("Mine.csv"))));
  const imageCap = () => refusal((answer(409, { detail: "EEG10-10.csv is a cap the image already ships; rename the file" }), uploadCap(csv("EEG10-10.csv"))));

  it("offers Replace for a name the project's own caps already use", async () => {
    expect(canReplaceUpload(await projectTaken(), "Mine.csv", [cap("Mine.csv", "project"), cap("EEG10-10.csv", "simnibs")])).toBe(true);
  });

  it("offers Replace when the list has not caught up with the upload that took the name", async () => {
    expect(canReplaceUpload(await projectTaken(), "Mine.csv", [])).toBe(true);
  });

  it("never offers Replace for a cap the image ships", async () => {
    const error = await imageCap();
    expect(canReplaceUpload(error, "EEG10-10.csv", [cap("EEG10-10.csv", "simnibs")])).toBe(false);
    expect(canReplaceUpload(error, "EEG10-10.csv", [cap("EEG10-10.csv", "ti-toolbox")])).toBe(false);
  });

  it("never offers Replace for a refusal that is not a name conflict", async () => {
    answer(422, NAME_RULE_422);
    expect(canReplaceUpload(await refusal(uploadCap(csv("Mine.csv"))), "Mine.csv", [cap("Mine.csv", "project")])).toBe(false);
    expect(canReplaceUpload(new Error("offline"), "Mine.csv", [cap("Mine.csv", "project")])).toBe(false);
  });
});
