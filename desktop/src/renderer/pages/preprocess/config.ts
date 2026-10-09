import { appDefaults } from "../../forms/appDefaults";
import type { PreprocessConfig } from "./api";

/** The Pre-processing form's starting values (`x-app-defaults.pre`, see PARITY.md). */
export function defaultConfig(): PreprocessConfig {
  return { ...(appDefaults("pre", "PreprocessConfig") as PreprocessConfig), subject_ids: [] };
}
