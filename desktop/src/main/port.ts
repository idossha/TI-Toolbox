/** Free-port probing on `127.0.0.1`, so a second project's stack never collides with a first. */
import { createServer } from "node:net";

export function isPortFree(port: number, host = "127.0.0.1"): Promise<boolean> {
  return new Promise((resolve) => {
    const srv = createServer();
    srv.once("error", () => resolve(false));
    srv.once("listening", () => srv.close(() => resolve(true)));
    srv.listen(port, host);
  });
}

export async function findFreePort(preferred = 8765, host = "127.0.0.1", maxTries = 500): Promise<number> {
  for (let i = 0; i < maxTries; i++) {
    const candidate = preferred + i;
    if (candidate > 65535) break;
    if (await isPortFree(candidate, host)) return candidate;
  }
  throw new Error(`No free port found on ${host} starting at ${preferred}`);
}
