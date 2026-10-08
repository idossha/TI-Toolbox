/**
 * The run pages' starting values: `x-app-defaults[kind]` of `/api/schema` (written from
 * `tit/server/app_defaults.py`, the one table the server also fills into an agent's config) over
 * the config class's own schema `default`s. ARCHITECTURE §6 "App defaults".
 *
 * Read synchronously (`appDefaults`) by the pages' form-state builders, so each run page renders
 * only once the schema has loaded (`withAppDefaults`): no first frame with values the server does
 * not have, and no second copy of them here.
 */
import { useQuery } from "@tanstack/react-query";
import type { ComponentType } from "react";
import { InlineError } from "../ui/Feedback";
import { defaultsFromSchema, loadSchema, resolveDef, type JSONSchema } from "./schema";

let loaded: JSONSchema | null = null;

/** Make *doc* (an `/api/schema` document) the source `appDefaults` reads. */
export function setAppDefaultsSchema(doc: JSONSchema): void {
  loaded = doc;
}

/** A fresh copy of what *kind*'s page starts with, as `configClass` fields (wire names). */
export function appDefaults(kind: string, configClass: string): Record<string, unknown> {
  if (!loaded) throw new Error("app defaults read before /api/schema loaded (wrap the page in withAppDefaults)");
  const table = (loaded["x-app-defaults"] ?? {}) as Record<string, Record<string, unknown>>;
  return structuredClone({ ...defaultsFromSchema(resolveDef(loaded, configClass)), ...table[kind] });
}

/** *Page*, rendered once `/api/schema` is loaded (an inline error with Retry if it fails). */
export function withAppDefaults<P extends object>(Page: ComponentType<P>): ComponentType<P> {
  return function WithAppDefaults(props: P) {
    const schema = useQuery({
      queryKey: ["schema"],
      queryFn: async () => {
        setAppDefaultsSchema(await loadSchema());
        return true;
      },
      staleTime: Infinity,
    });
    if (schema.isError) {
      return <InlineError message="Could not load the form defaults." detail={String(schema.error)} onAction={() => void schema.refetch()} />;
    }
    return schema.data ? <Page {...props} /> : null;
  };
}
