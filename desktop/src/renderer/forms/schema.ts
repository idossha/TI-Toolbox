/**
 * `/api/schema` loader — fetched once and cached in memory for the life of the renderer. The
 * response is `contracts/schema.json`: a JSON-Schema document whose `$defs` hold one entry per
 * config dataclass (`SimulationConfig`, `FlexConfig`, ... — see plan §3). Config-shaped forms
 * resolve their schema by name from this single cached document instead of hitting the network
 * once per config kind.
 */
export type JSONSchema = Record<string, unknown>;

let cached: Promise<JSONSchema> | null = null;

/** Fetch and cache `/api/schema`. Safe to call from many components; the network call happens once. */
export function loadSchema(): Promise<JSONSchema> {
  if (!cached) {
    cached = fetch("/api/schema", { credentials: "same-origin" }).then((res) => {
      if (!res.ok) {
        cached = null; // let a later call retry instead of caching a failure forever
        throw new Error(`GET /api/schema failed with HTTP ${res.status}`);
      }
      return res.json() as Promise<JSONSchema>;
    });
  }
  return cached;
}

/** Test-only escape hatch: forces the next `loadSchema()` call to refetch. */
export function resetSchemaCache(): void {
  cached = null;
}

/** Resolve one `$defs`/`definitions` entry from a schema document by name. */
export function resolveDef(root: JSONSchema, name: string): JSONSchema {
  const defs = (root.$defs ?? root.definitions) as Record<string, JSONSchema> | undefined;
  const def = defs?.[name];
  if (!def) throw new Error(`Schema has no $defs/${name}`);
  return def;
}

/** Load `/api/schema` (from cache) and resolve one named config's definition. */
export async function loadConfigSchema(name: string): Promise<JSONSchema> {
  return resolveDef(await loadSchema(), name);
}

export interface SchemaProperty {
  type?: string | string[];
  enum?: unknown[];
  default?: unknown;
  title?: string;
  description?: string;
  items?: SchemaProperty;
  properties?: Record<string, SchemaProperty>;
  minimum?: number;
  maximum?: number;
  [key: string]: unknown;
}

export function schemaProperties(def: JSONSchema): Record<string, SchemaProperty> {
  return (def.properties as Record<string, SchemaProperty> | undefined) ?? {};
}

export function requiredFields(def: JSONSchema): string[] {
  return (def.required as string[] | undefined) ?? [];
}

/** Build a partial values object from every property's `default`, for `useForm({ defaultValues })`. */
export function defaultsFromSchema(def: JSONSchema): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(schemaProperties(def))) {
    if ("default" in prop) out[key] = prop.default;
  }
  return out;
}
