/**
 * Free-port probing on `127.0.0.1`, so a second project's stack never collides with a first, and the
 * parsing of the launch environment values that choose ports and wait times. A launcher hands those
 * over as strings (`TIT_LAUNCH_PORT`, `TIT_LAUNCH_TIMEOUT`, …); a bad one is refused here, naming the
 * variable, instead of publishing port 0 or giving up on the server instantly.
 */
import { createServer } from "node:net";

const PORT_RANGE = "a port number from 1 to 65535";

/** A TCP port: an integer 1–65535. Port 0 would ask the OS for any port, which nothing then knows. */
export function isValidPort(value: number): boolean {
  return Number.isInteger(value) && value >= 1 && value <= 65535;
}

/** The port in `env[name]`; unset or blank gives `fallback`; anything but decimal digits naming 1–65535 throws. */
export function portFromEnv(name: string, fallback: number, env: NodeJS.ProcessEnv = process.env): number {
  const raw = env[name]?.trim();
  if (!raw) return fallback;
  const port = /^\d+$/.test(raw) ? Number(raw) : Number.NaN;
  if (!isValidPort(port)) throw new Error(`${name} must be ${PORT_RANGE} (got "${raw}").`);
  return port;
}

/** The positive, finite number in `env[name]`; unset or blank gives `fallback`; anything else throws. */
export function positiveFromEnv(name: string, fallback: number, env: NodeJS.ProcessEnv = process.env): number {
  const raw = env[name]?.trim();
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be a positive number (got "${raw}").`);
  return value;
}

export function isPortFree(port: number, host = "127.0.0.1"): Promise<boolean> {
  return new Promise((resolve) => {
    const srv = createServer();
    srv.once("error", () => resolve(false));
    srv.once("listening", () => srv.close(() => resolve(true)));
    srv.listen(port, host);
  });
}

export async function findFreePort(preferred = 8765, host = "127.0.0.1", maxTries = 500): Promise<number> {
  if (!isValidPort(preferred)) throw new Error(`The first port to try must be ${PORT_RANGE} (got ${preferred}).`);
  for (let i = 0; i < maxTries; i++) {
    const candidate = preferred + i;
    if (candidate > 65535) break;
    if (await isPortFree(candidate, host)) return candidate;
  }
  throw new Error(`No free port found on ${host} starting at ${preferred}`);
}
