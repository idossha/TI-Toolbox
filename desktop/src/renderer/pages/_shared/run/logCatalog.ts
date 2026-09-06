/**
 * The two requests the Terminal's `file` source makes (DESIGN.md v3 §4.6 + fix lane FXU1).
 *
 * `GET /api/catalog/logs?subject=&kind=` does not exist in `contracts/openapi.v1.yaml` yet — it is
 * reported to the orchestrator as a `tit/server/routes/catalog_v1.py` follow-up and is served by
 * `tests/mock-server/server.mjs`. Both helpers therefore treat **any** failure as "no log file",
 * because the fallback is a designed state ("What will run"), not an error: a server without the
 * route must show a useful pane, never a red box.
 *
 * `GET /api/files/text?path=&tail=` is real (`tit/server/routes/files.py::text`), jailed to the
 * project, and is the only way this pane reads bytes off disk.
 */
import type { LogFileEntry } from "./terminalSources";

async function getJson(url: string): Promise<unknown> {
  const res = await fetch(url, { credentials: "same-origin", headers: { accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} failed with HTTP ${res.status}`);
  return res.json();
}

/** Newest-first log files for one subject, filtered to `kinds`. `[]` on any failure. */
export async function listLogFiles(subject: string, kinds: string[]): Promise<LogFileEntry[]> {
  if (!subject || kinds.length === 0) return [];
  const url = `/api/catalog/logs?subject=${encodeURIComponent(subject)}&kind=${encodeURIComponent(kinds.join(","))}&limit=20`;
  try {
    const data = await getJson(url);
    if (!Array.isArray(data)) return [];
    return data.filter(
      (e): e is LogFileEntry =>
        !!e && typeof e === "object" && typeof (e as LogFileEntry).path === "string" && typeof (e as LogFileEntry).modified === "string",
    );
  } catch {
    return [];
  }
}

/** The last `tail` lines of a text file inside the project jail. `""` on any failure. */
export async function readLogTail(path: string, tail = 200): Promise<string> {
  try {
    const res = await fetch(`/api/files/text?path=${encodeURIComponent(path)}&tail=${tail}`, {
      credentials: "same-origin",
      headers: { accept: "text/plain" },
    });
    if (!res.ok) return "";
    return await res.text();
  } catch {
    return "";
  }
}
