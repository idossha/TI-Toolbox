/**
 * 2026-11-02: the desktop describes every field neutrally and ranks none for compliance
 * (docs/dev/DECISIONS.md "Field metrics are described, never ranked for compliance").
 *
 * The descriptions in `pages/analyzer/fields.ts` are the Simulator's Output-field tooltips and the
 * field help elsewhere; the carrier-only help sits beside the same checkboxes. They state what a
 * field is (formula, units, zero-to-peak or RMS), never which one to compare with exposure limits
 * or that one "is not a compliance metric". The forbidden words below are the maintainer's request,
 * not derived from the code; the Python registry is held to the same rule by
 * tests/test_field_registry.py::TestOutputFieldDefinitions.
 *
 * Run: cd desktop && npx vitest run tests/unit/field-descriptions.test.ts
 */
import { describe, expect, it } from "vitest";
import { FIELD_REGISTRY } from "../../src/renderer/pages/analyzer/fields";
import { CARRIER_ONLY_HELP, WRITE_NIFTIS_HELP } from "../../src/renderer/pages/simulator/types";

const FORBIDDEN = ["complian", "exposure", "icnirp", "limit"];

describe("field descriptions", () => {
  const texts = [...FIELD_REGISTRY.map((f) => [f.name, f.description] as const), ["CARRIER_ONLY_HELP", CARRIER_ONLY_HELP] as const, ["WRITE_NIFTIS_HELP", WRITE_NIFTIS_HELP] as const];

  it("has descriptions to check", () => {
    expect(FIELD_REGISTRY.length).toBeGreaterThanOrEqual(6);
  });

  it.each(texts)("%s makes no compliance or exposure-limit claim", (_name, text) => {
    for (const word of FORBIDDEN) expect(text.toLowerCase()).not.toContain(word);
  });

  it("still states the peak and RMS conventions", () => {
    expect(FIELD_REGISTRY.find((f) => f.name === "hf_peak")?.description).toContain("zero-to-peak");
    expect(FIELD_REGISTRY.find((f) => f.name === "hf_rms")?.description).toContain("RMS carrier field over time");
  });
});
