# forms/

Config-schema-driven form infrastructure shared by every page. Owned by F2 (design system).

- `schema.ts` — fetches and caches `/api/schema` (`contracts/schema.json`) once per renderer
  session; `loadConfigSchema(name)` resolves one `$defs` entry (`SimulationConfig`, `FlexConfig`,
  ...).
- `ajvResolver.ts` — `createAjvResolver(name | schema)` returns a react-hook-form `resolver`. Uses
  **`ajv/dist/2020`** (the `Ajv2020` class), not the default `ajv` export and not
  `@hookform/resolvers/ajv` — that package's resolver hardcodes `new Ajv(...)` from the draft-07
  build, which does not fully understand the 2020-12 keywords `dev/build_contract.py` emits
  (`$defs`, `prefixItems`, etc.). We reuse its `toNestErrors`/`validateFieldsNatively` helpers
  (exported from the `@hookform/resolvers` root) so error-path nesting matches the ecosystem
  convention; we do not import its `ajv` subpath resolver itself. Called with a schema **name**,
  it adds the whole `/api/schema` document to Ajv once and resolves that one `$defs` entry from
  within it (`ajv.getSchema(key + "#/$defs/<Name>")`), so a config whose schema `$ref`s a sibling
  `$defs` entry (most of them — electrode/ROI `oneOf` branches, `PreprocessConfig`'s
  `qsi*_config`, `SimulationConfig`'s `Montage`, ...) still resolves; called with an already-loaded
  schema **object**, it compiles that object in isolation, so a self-contained test fixture with no
  cross-`$defs` refs of its own still works without a network fetch.
- `SchemaField.tsx` — renders one property generically (enum → Select, boolean → Switch, number →
  NumberInput, array-of-strings → MultiSelect, else TextInput). Reach for a hand-built `Field` +
  ui primitive instead when a property needs page-specific behaviour (nested objects, coordinate
  triples, electrode pairs — the schema doesn't know these are one widget).
- `serverErrors.ts` — `applyServerErrors(setError, errors)` maps a `/api/validate` or job-submit
  error body (`{path, message}[]`) onto react-hook-form fields; `formLevelErrors` pulls out the
  ones with no field path (root/plan-level problems) for the Plan panel to show instead.

## Usage sketch

```tsx
const schema = await loadConfigSchema("SimulationConfig");
const form = useForm({
  resolver: createAjvResolver("SimulationConfig"),
  defaultValues: defaultsFromSchema(schema),
});
```

On a 422 from `/api/validate` or `/api/jobs`, call `applyServerErrors(form.setError, body.errors)`
and show `formLevelErrors(body.errors)` in the Plan panel (DESIGN.md §2, §6.3).
