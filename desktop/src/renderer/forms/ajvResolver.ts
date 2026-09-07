/**
 * react-hook-form resolver backed by Ajv's draft 2020-12 build (`ajv/dist/2020`), matching the
 * `$schema` dialect `dev/build_contract.py` writes into `contracts/generated/config.schema.json`. We do not use
 * `@hookform/resolvers/ajv` because it hardcodes the draft-07 `Ajv` class — see
 * `desktop/src/renderer/forms/README.md`.
 */
import Ajv2020 from "ajv/dist/2020";
import type { ErrorObject, ValidateFunction } from "ajv";
import { toNestErrors, validateFieldsNatively } from "@hookform/resolvers";
import type { FieldError, FieldValues, ResolverOptions, ResolverResult } from "react-hook-form";
import { loadSchema, type JSONSchema } from "./schema";

let sharedAjv: Ajv2020 | null = null;

/** One Ajv instance for the renderer's lifetime; schemas are added to it as they're compiled. */
function getAjv(): Ajv2020 {
  if (!sharedAjv) {
    // strict:false — the config schemas are generated from dataclasses we don't fully control
    // yet (Stage 0/F1b); an unrecognised keyword or format must not hard-fail validation.
    sharedAjv = new Ajv2020({ allErrors: true, strict: false, useDefaults: true });
  }
  return sharedAjv;
}

/**
 * `/api/schema` is one JSON-Schema *document*: every config's `$defs/<Name>` entry `$ref`s its
 * siblings by an absolute pointer into that same document (`#/$defs/<Other>`), never in a way
 * that's self-contained. Compiling one extracted `$defs/<Name>` object on its own — stripped of
 * every other `$defs` entry — makes Ajv throw `can't resolve reference #/$defs/<Other> from id #`
 * for any config that isn't a flat leaf: electrode/ROI `oneOf` branches, `PreprocessConfig`'s
 * `qsi*_config`, `SimulationConfig`'s `Montage`, and more. Reported independently by several page
 * lanes hitting the same crash (`pages/preprocess/PARITY.md` #4, `pages/optimizer-flex/PARITY.md`
 * #4, `pages/simulator/PARITY.md` #7, `tests/unit/optimizer-ex-defaults.test.ts`'s file comment) —
 * this is that fix. The whole document is added to Ajv exactly once, under one fixed key; a named
 * `$defs` entry is then resolved *from within it* via `ajv.getSchema(key + "#/$defs/<Name>")`, so
 * every sibling `$ref` stays resolvable because it's still part of the one schema Ajv compiled.
 */
const SCHEMA_DOC_KEY = "tit-contract-schema.json";
let schemaDocAdded: Promise<void> | null = null;

function ensureSchemaDocAdded(): Promise<void> {
  if (!schemaDocAdded) {
    schemaDocAdded = loadSchema().then((doc) => {
      getAjv().addSchema(doc, SCHEMA_DOC_KEY);
    });
  }
  return schemaDocAdded;
}

function ajvErrorsToFieldErrors(errors: ErrorObject[]): Record<string, FieldError> {
  // Object.create(null): a plain {} would let an error at a path named "constructor" or
  // "toString" silently vanish behind the inherited member of the same name.
  const out: Record<string, FieldError> = Object.create(null);
  for (const error of errors) {
    let instancePath = error.instancePath;
    if (error.keyword === "required") {
      const missing = (error.params as { missingProperty?: string }).missingProperty;
      if (missing) instancePath += `/${missing}`;
    }
    const path = instancePath.replace(/^\//, "").replace(/\//g, ".");
    if (!out[path]) out[path] = { type: error.keyword, message: error.message };
  }
  return out;
}

export type AjvFormResolver<T extends FieldValues> = (
  values: T,
  context: unknown,
  options: ResolverOptions<T>,
) => Promise<ResolverResult<T>>;

/**
 * Build a resolver for one config kind. Pass the schema name to resolve it — with every sibling
 * `$ref` intact — from the cached `/api/schema` document, or an already-loaded, self-contained
 * schema object (e.g. a test fixture with no cross-`$defs` refs of its own) to compile it in
 * isolation exactly as before.
 */
export function createAjvResolver<T extends FieldValues>(schemaOrName: string | JSONSchema): AjvFormResolver<T> {
  let compiled: ValidateFunction | null = null;
  let compiling: Promise<ValidateFunction> | null = null;

  async function ensureCompiled(): Promise<ValidateFunction> {
    if (compiled) return compiled;
    if (!compiling) {
      compiling = (async () => {
        if (typeof schemaOrName === "string") {
          await ensureSchemaDocAdded();
          const validate = getAjv().getSchema(`${SCHEMA_DOC_KEY}#/$defs/${schemaOrName}`);
          if (!validate) throw new Error(`Schema has no $defs/${schemaOrName}`);
          compiled = validate;
        } else {
          compiled = getAjv().compile(schemaOrName);
        }
        return compiled;
      })();
    }
    return compiling;
  }

  return async (values, _context, options) => {
    const validate = await ensureCompiled();
    // Ajv mutates in place (useDefaults etc.) — validate a clone so RHF's live values are untouched.
    const parsed = structuredClone(values) as T;
    const valid = validate(parsed);

    if (options.shouldUseNativeValidation) validateFieldsNatively({}, options);

    if (valid) return { values: parsed, errors: {} };
    return {
      values: {},
      errors: toNestErrors(ajvErrorsToFieldErrors((validate.errors ?? []) as ErrorObject[]), options),
    };
  };
}
