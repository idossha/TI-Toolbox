import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ResolverOptions } from "react-hook-form";
import { createAjvResolver } from "../../src/renderer/forms/ajvResolver";
import { resetSchemaCache, type JSONSchema } from "../../src/renderer/forms/schema";
import { buildSimulationConfig } from "../../src/renderer/pages/simulator/buildConfig";
import type { SelectedRow } from "../../src/renderer/pages/simulator/types";
import { buildExConfig, defaultExFormState, savedTargets } from "../../src/renderer/pages/optimizer/exConfig";
import { defaultConfig as defaultPreprocessConfig } from "../../src/renderer/pages/preprocess/index";

/**
 * `forms/ajvResolver.ts::createAjvResolver(name)` used to compile one `$defs/<Name>` entry
 * extracted from `contracts/schema.json` in isolation — stripped of every sibling `$defs` its own
 * `$ref`s point to — so it threw `can't resolve reference #/$defs/<Other> from id #` at *compile*
 * time (before any value was even checked) for every config that isn't a flat leaf. `ExConfig`,
 * `PreprocessConfig` and `SimulationConfig` all hit this (electrodes' `oneOf` branches, the
 * `qsi*_config` fields, `Montage`), which is why `tests/unit/optimizer-ex-defaults.test.ts`,
 * `tests/unit/preprocess-defaults.test.ts` and `tests/unit/simulator-defaults.test.ts` each built
 * their own page-local Ajv setup instead of calling the shared resolver by name (see their file
 * comments). These tests exercise the *fixed* shared resolver directly, the way every page is
 * meant to call it (`createAjvResolver("<Name>")`, per `forms/README.md`), against real
 * config-builder output from three different pages — proof the fix generalises, not just a
 * `ConfigX`-shaped synthetic case.
 */

// contracts/schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as JSONSchema;

const noopOptions = { shouldUseNativeValidation: false } as unknown as ResolverOptions<Record<string, unknown>>;

beforeEach(() => {
  // `createAjvResolver(name)` fetches `/api/schema` via `forms/schema.ts`'s `loadSchema()` —
  // stub `fetch` to serve the same document read from disk above, and reset its cache so every
  // test in this file (each gets a fresh resolver closure) sees the stub rather than a real
  // network call.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(schemaDoc), { status: 200, headers: { "content-type": "application/json" } })),
  );
  resetSchemaCache();
});

async function validate(name: string, values: Record<string, unknown>) {
  const resolver = createAjvResolver<Record<string, unknown>>(name);
  return resolver(values, undefined, noopOptions);
}

describe("createAjvResolver(name): cross-referencing config schemas compile and validate", () => {
  it("a montage-source SimulationConfig (nested Montage `$defs`) validates", async () => {
    const row: SelectedRow = {
      id: "montage:GSN-HydroCel-185:uni_polar:F3_F4:ernie",
      subjectId: "ernie",
      source: "montage",
      kind: "uni_polar",
      eegNet: "GSN-HydroCel-185",
      name: "F3_F4",
      pairs: [["E24", "E124"]],
      currents: "1.0,1.0",
    };
    const config = buildSimulationConfig(row, {
      conductivity: "scalar",
      electrodeShape: "ellipse",
      dimensions: [8, 8],
      gelThickness: 4,
      outputFields: ["TI_max"],
      customConductivities: {},
    });
    const result = await validate("SimulationConfig", config as unknown as Record<string, unknown>);
    expect(result.errors).toEqual({});
  });

  it("an ExConfig (bucketed electrodes' `oneOf` `$defs`) validates", async () => {
    const target = savedTargets(["Thalamus_target"], false)[0]!;
    const form = { ...defaultExFormState(), buckets: { e1_plus: ["F7"], e1_minus: ["P7"], e2_plus: ["F3"], e2_minus: ["P3"] } };
    const config = buildExConfig("ernie", "/mnt/example/leadfields/GSN-HydroCel-185/leadfield.hdf5", form, target, "");
    const result = await validate("ExConfig", config as unknown as Record<string, unknown>);
    expect(result.errors).toEqual({});
  });

  it("a PreprocessConfig (qsi*_config `$defs`, both null when off) validates", async () => {
    const values = { ...defaultPreprocessConfig(), subject_ids: ["ernie"] };
    const result = await validate("PreprocessConfig", values as unknown as Record<string, unknown>);
    expect(result.errors).toEqual({});
  });

  it("does not throw/reject for a config with cross-`$defs` refs, even when the value itself is invalid", async () => {
    // The original bug crashed at *compile* time (unresolvable $ref), before any value was
    // checked — reproduce that shape with a value that's merely wrong (bad enum), and confirm the
    // resolver still runs to completion (rejecting or invalid-with-field-errors would both be a
    // legitimate outcome; throwing "can't resolve reference" is the one this fix rules out).
    const result = await validate("ExConfig", { current_mode: "not-a-real-value" });
    expect(Object.keys(result.errors).length).toBeGreaterThan(0);
  });
});
