/**
 * The run pages' default builders read `/api/schema` (forms/appDefaults.tsx); unit tests give them
 * the committed `contracts/generated/config.schema.json`, the file the server serves.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { setAppDefaultsSchema } from "../../src/renderer/forms/appDefaults";

setAppDefaultsSchema(JSON.parse(readFileSync(resolve(__dirname, "../../../contracts/generated/config.schema.json"), "utf8")));
