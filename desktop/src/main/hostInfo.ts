/**
 * Host identity passed into the compose env, matching the `TIT_HOST_*` variables
 * `package/src/backend/env.js`'s `buildRuntimeEnv` sets today (kept identical so
 * `tit.telemetry`'s `_canonical_arch()` sees the same values regardless of launcher).
 */
import { arch, platform, release } from "node:os";

const ARCH_MAP: Record<string, string> = { x64: "x86_64", x32: "x86", ia32: "x86", arm64: "arm64" };

export function canonicalArch(nodeArch: string = arch()): string {
  return ARCH_MAP[nodeArch] ?? nodeArch;
}

export function timezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export interface HostOsInfo {
  os: string;
  version: string;
  arch: string;
}

export function hostOsInfo(): HostOsInfo {
  return { os: platform(), version: release(), arch: canonicalArch() };
}
