import { describe, expect, it } from "vitest";
import { buildStackEnv, computeProjectName, generateToken, hash8, stackErrorMessage, type StackErrorKind } from "../../src/shared/compose";

describe("generateToken", () => {
  it("is base64url (no +, /, or = padding) and non-empty", () => {
    const token = generateToken();
    expect(token.length).toBeGreaterThan(0);
    expect(token).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("is different every call", () => {
    expect(generateToken()).not.toBe(generateToken());
  });

  it("scales roughly with the requested byte length", () => {
    expect(generateToken(32).length).toBeGreaterThan(generateToken(4).length);
  });
});

describe("hash8 / computeProjectName", () => {
  it("is stable for the same input", () => {
    expect(hash8("/Users/ido/datasets/000")).toBe(hash8("/Users/ido/datasets/000"));
  });

  it("is 8 lowercase hex characters", () => {
    expect(hash8("anything")).toMatch(/^[0-9a-f]{8}$/);
  });

  it("differs for different project directories", () => {
    expect(hash8("/a/b")).not.toBe(hash8("/a/c"));
  });

  it("computeProjectName is safe as a docker object-name prefix", () => {
    const name = computeProjectName("/Users/ido/datasets/000");
    expect(name).toMatch(/^ti-toolbox-[0-9a-f]{8}$/);
  });
});

describe("buildStackEnv", () => {
  const base = {
    hostProjectDir: "/Users/ido/datasets/000",
    projectDirName: "000",
    userConfigDir: "/Users/ido/.config/ti-toolbox",
    port: 8801,
    token: "sekret",
    timezone: "America/Chicago",
    hostOs: "darwin",
    hostOsVersion: "24.6.0",
    hostArch: "arm64",
  };

  it("carries every required variable", () => {
    expect(buildStackEnv(base)).toMatchObject({
      LOCAL_PROJECT_DIR: "/Users/ido/datasets/000",
      PROJECT_DIR_NAME: "000",
      TIT_USER_CONFIG: "/Users/ido/.config/ti-toolbox",
      TIT_SERVER_PORT: "8801",
      TIT_SERVER_TOKEN: "sekret",
    });
  });

  it("no longer carries DISPLAY or FREESURFER_VOLUME (decisions D2/D3)", () => {
    const env = buildStackEnv(base);
    expect(env.DISPLAY).toBeUndefined();
    expect(env.FREESURFER_VOLUME).toBeUndefined();
    expect(Object.keys(env)).not.toContain("FS_LICENSE");
  });

  it("includes the dev-only overrides only when given", () => {
    expect(buildStackEnv(base).TIT_STATIC_DIR).toBeUndefined();
    const env = buildStackEnv({ ...base, repoDir: "/Users/ido/repo", staticDir: "/ti-toolbox/desktop/out/renderer" });
    expect(env.TIT_REPO_DIR).toBe("/Users/ido/repo");
    expect(env.TIT_STATIC_DIR).toBe("/ti-toolbox/desktop/out/renderer");
  });

  // The key must be PRESENT and EMPTY, not absent: `stack.ts` interpolates the compose file from
  // `{...process.env, ...buildStackEnv(...)}`, so an absent key lets a stray host `TIT_REPO_DIR`
  // through and bind-mounts a host directory over the image's own baked-in `/ti-toolbox`.
  it("supplies TIT_REPO_DIR as an empty string when there is no dev repo to mount", () => {
    const env = buildStackEnv(base);
    expect(Object.keys(env)).toContain("TIT_REPO_DIR");
    expect(env.TIT_REPO_DIR).toBe("");
  });

  it("port is a string (container env vars are always strings)", () => {
    expect(typeof buildStackEnv(base).TIT_SERVER_PORT).toBe("string");
  });
});

describe("stackErrorMessage", () => {
  const kinds: StackErrorKind[] = [
    "not-installed",
    "not-running",
    "socket-permission",
    "unsupported-engine",
    "image-pull-failed",
    "health-timeout",
    "container-exited",
    "compose-invalid",
    "unknown",
  ];

  it("gives every failure its own message", () => {
    const messages = kinds.map((k) => stackErrorMessage(k));
    expect(new Set(messages).size).toBe(kinds.length);
  });

  it("tells a Linux user the docker-group fix for a socket permission error", () => {
    const message = stackErrorMessage("socket-permission");
    expect(message).toMatch(/usermod -aG docker/);
  });

  it("distinguishes Docker missing from Docker not running", () => {
    expect(stackErrorMessage("not-installed")).toMatch(/Install Docker Desktop/);
    expect(stackErrorMessage("not-running")).toMatch(/not running/i);
    expect(stackErrorMessage("not-installed")).not.toEqual(stackErrorMessage("not-running"));
  });

  it("names Podman as the unsupported engine", () => {
    expect(stackErrorMessage("unsupported-engine")).toMatch(/Podman/);
  });

  it("appends the detail it is given, and never leaves an empty parenthesis when it is not", () => {
    expect(stackErrorMessage("image-pull-failed", "manifest unknown")).toContain("(manifest unknown)");
    expect(stackErrorMessage("image-pull-failed")).not.toContain("(");
  });
});
