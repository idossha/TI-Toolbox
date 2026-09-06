/** `/api/health` polling, shared by the manual "Connect" flow and `stack.start`'s attach/fresh paths. */
import { net } from "electron";

export const HEALTH_POLL_MS = 500;
export const HEALTH_TIMEOUT_MS = 15_000;

export async function waitForHealth(origin: string, timeoutMs = HEALTH_TIMEOUT_MS): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "no response";
  while (Date.now() < deadline) {
    try {
      const res = await net.fetch(`${origin}/api/health`, { signal: AbortSignal.timeout(HEALTH_POLL_MS * 2) });
      if (res.ok) {
        const body = (await res.json()) as { status?: string };
        if (body.status === "ok") return;
        lastError = `health status ${String(body.status)}`;
      } else {
        lastError = `HTTP ${res.status}`;
      }
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, HEALTH_POLL_MS));
  }
  throw new Error(`Server at ${origin} did not answer /api/health within ${timeoutMs / 1000}s (${lastError})`);
}

/** Bearer request so an invalid/stale token surfaces as a clear error, not a raw 401 page. */
export async function checkToken(origin: string, token: string): Promise<void> {
  const res = await net.fetch(`${origin}/api/version`, {
    headers: { authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(5000),
  });
  if (res.status === 401) throw new Error("The server rejected the token");
  if (!res.ok) throw new Error(`GET /api/version failed with HTTP ${res.status}`);
}
