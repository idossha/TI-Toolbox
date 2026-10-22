/**
 * The sphere shape `buildConfig` reads (x, y, z, radius, all optional while a row is being typed)
 * and its empty value. The spheres themselves are edited in the shared ROI picker
 * (`pages/_shared/roi`); the Analyzer's old sphere-row editor that lived here is gone.
 */
export interface Sphere {
  x: number | undefined;
  y: number | undefined;
  z: number | undefined;
  radius: number | undefined;
}

export const EMPTY_SPHERE: Sphere = {
  x: undefined,
  y: undefined,
  z: undefined,
  radius: undefined,
};
