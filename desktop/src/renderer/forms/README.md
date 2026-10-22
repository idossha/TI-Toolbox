# forms/

Config-schema-driven form infrastructure shared by every page.

- `schema.ts` — fetches and caches `/api/schema` (`contracts/generated/config.schema.json`) once per renderer
  session; `resolveDef(root, name)` resolves one `$defs` entry (`SimulationConfig`, `FlexConfig`,
  ...), and `defaultsFromSchema(def)` collects every property's `default`.
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
- `appDefaults.tsx` — `appDefaults(kind, configClass)`: what a run page starts with, `x-app-defaults[kind]`
  of the same document (`tit/server/app_defaults.py`) over the class's schema `default`s;
  `withAppDefaults(Page)` renders a page only once the document has loaded, so the pages' default
  builders can read it synchronously. Unit tests load the committed file
  (`tests/unit/setup-app-defaults.ts`).

Pages import these modules directly (`forms/schema`, `forms/ajvResolver`, `forms/appDefaults`);
there is no barrel. Each page builds its own fields from `ui/` primitives.
