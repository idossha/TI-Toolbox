/** Main-process orchestration for saving the live native scene into the active project. */

export interface NativeSceneSaveSession {
  origin: string;
  token: string;
}

export type NativeSceneSaveResult =
  | { ok: true; path: string }
  | { ok: false; reason: string }
  | { ok: false; cancelled: true };

interface NativeSceneDestinationResponse {
  ok: boolean;
  json(): Promise<unknown>;
}

interface NativeSceneSaveHandoff {
  hasScene: boolean;
  running: () => Promise<boolean>;
  confirm: () => Promise<boolean>;
  launch: () => Promise<void>;
}

export interface NativeSceneSaveDependencies {
  trusted: () => boolean;
  session: () => NativeSceneSaveSession | null;
  projectRoot: () => Promise<string | undefined>;
  fetchDestination: (url: string, init: RequestInit) => Promise<NativeSceneDestinationResponse>;
  resolveHostPath: (path: string) => Promise<{ ok: true; path: string } | { ok: false; reason: string }>;
  saveNativeScene: (destination: string, projectRoot: string) => Promise<string>;
  handoff: (request: NativeSceneSaveHandoff) => Promise<{ ok: true } | { ok: false; cancelled: true }>;
}

/**
 * Save through a host path while returning only the server-jailed project path to the renderer.
 *
 * The server owns project naming and confinement; Electron maps that path for native filesystem
 * access. Rechecking trust, session identity and project root immediately before native dispatch
 * prevents an in-flight request from crossing a project switch.
 */
export async function orchestrateNativeSceneSave(
  name: unknown,
  dependencies: NativeSceneSaveDependencies,
): Promise<NativeSceneSaveResult> {
  if (!dependencies.trusted() || typeof name !== "string" || !name.trim() || name.length > 80) {
    return { ok: false, reason: "Invalid native scene save request." };
  }
  try {
    const session = dependencies.session();
    const root = await dependencies.projectRoot();
    if (!session || !root) throw new Error("Native scene saving requires an active local project.");

    let jailedPath: string | undefined;
    const handoff = await dependencies.handoff({
      hasScene: false,
      running: async () => false,
      confirm: async () => false,
      launch: async () => {
        if (!dependencies.trusted() || session !== dependencies.session()) {
          throw new Error("The active project changed before saving.");
        }
        const response = await dependencies.fetchDestination(
          `${session.origin}/api/viewer/scenes/${encodeURIComponent(name)}/native-destination`,
          {
            method: "POST",
            headers: { authorization: `Bearer ${session.token}` },
            signal: AbortSignal.timeout(5000),
          },
        );
        const rawBody = await response.json();
        const body = rawBody && typeof rawBody === "object"
          ? rawBody as { scene_path?: unknown; detail?: unknown }
          : {};
        if (!response.ok || typeof body.scene_path !== "string") {
          throw new Error(
            typeof body.detail === "string"
              ? body.detail
              : "Could not prepare the project scene destination.",
          );
        }
        const mapped = await dependencies.resolveHostPath(body.scene_path);
        if (!mapped.ok) throw new Error(mapped.reason);
        const currentRoot = await dependencies.projectRoot();
        if (
          !dependencies.trusted()
          || session !== dependencies.session()
          || currentRoot !== root
        ) {
          throw new Error("The active project changed before saving.");
        }
        await dependencies.saveNativeScene(mapped.path, root);
        jailedPath = body.scene_path;
      },
    });
    if (!handoff.ok) return handoff;
    if (!jailedPath) throw new Error("TetraVox did not confirm the saved project scene path.");
    return { ok: true, path: jailedPath };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}
