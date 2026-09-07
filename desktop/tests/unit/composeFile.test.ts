import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  StackError,
  buildContainerPlan,
  durationToNs,
  interpolate,
  parseBind,
  parseComposeFile,
  parsePort,
  resolvedName,
  splitCommand,
  type Stack,
} from "../../src/shared/composeFile";

/**
 * The compose subset the app implements (`docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)` §1), against the
 * fixture that mirrors the shipped file's keys (`tests/e2e/fixtures/compose-v3.fixture.yml`) and,
 * at the bottom, against the shipped file itself.
 */

const FIXTURE = join(__dirname, "..", "e2e", "fixtures", "compose-v3.fixture.yml");
const SHIPPED = join(__dirname, "..", "..", "docker", "docker-compose.v3.yml");

const ENV: Record<string, string> = {
  LOCAL_PROJECT_DIR: "/Users/ido/datasets/000",
  PROJECT_DIR_NAME: "000",
  TIT_USER_CONFIG: "/Users/ido/.config/ti-toolbox",
  TZ: "America/Chicago",
  TIT_HOST_OS: "darwin",
  TIT_HOST_OS_VERSION: "24.6.0",
  TIT_HOST_ARCH: "arm64",
  TIT_SERVER_PORT: "8801",
  TIT_SERVER_TOKEN: "sekret",
};

function parseFixture(): Stack {
  return parseComposeFile(readFileSync(FIXTURE, "utf8"), ENV);
}

describe("interpolate", () => {
  it("substitutes ${VAR} and $VAR", () => {
    expect(interpolate("${A}/x", { A: "/a" })).toBe("/a/x");
    expect(interpolate("$A/x", { A: "/a" })).toBe("/a/x");
  });

  it("uses ${VAR:-default} and ${VAR-default} when unset", () => {
    expect(interpolate("${A:-fallback}", {})).toBe("fallback");
    expect(interpolate("${A-fallback}", {})).toBe("fallback");
    expect(interpolate("${A:-fallback}", { A: "real" })).toBe("real");
  });

  it("treats $$ as a literal dollar", () => {
    expect(interpolate("$$HOME", {})).toBe("$HOME");
  });

  it("throws a StackError naming an unset variable with no default", () => {
    expect(() => interpolate("${NOPE}", {}, "services.tit.image")).toThrow(StackError);
    expect(() => interpolate("${NOPE}", {})).toThrow(/\$\{NOPE\} is not set/);
  });
});

describe("small parsers", () => {
  it("converts compose durations to nanoseconds", () => {
    expect(durationToNs("10s", "k")).toBe(10_000_000_000);
    expect(durationToNs("500ms", "k")).toBe(500_000_000);
    expect(durationToNs("2m", "k")).toBe(120_000_000_000);
  });

  it("rejects a duration without a unit", () => {
    expect(() => durationToNs("10", "healthcheck.interval")).toThrow(/not a duration/);
  });

  it("parses a bind with and without a mode, and rejects an unknown mode", () => {
    expect(parseBind("/host:/container", "k")).toEqual({ source: "/host", target: "/container", readOnly: false, named: false });
    expect(parseBind("/host:/container:ro", "k").readOnly).toBe(true);
    expect(() => parseBind("/host:/container:z", "k")).toThrow(/unsupported mount mode/);
  });

  it("keeps a Windows drive letter out of the source:target split", () => {
    expect(parseBind("C:\\Users\\ido\\p:/mnt/p", "k")).toEqual({ source: "C:\\Users\\ido\\p", target: "/mnt/p", readOnly: false, named: false });
  });

  it("refuses a port mapping that is not explicitly on loopback", () => {
    expect(parsePort("127.0.0.1:8765:8765", "k")).toEqual({ hostIp: "127.0.0.1", hostPort: 8765, containerPort: 8765, protocol: "tcp" });
    expect(() => parsePort("8765:8765", "k")).toThrow(/never publishes a port on all interfaces/);
    expect(() => parsePort("0.0.0.0:8765:8765", "k")).toThrow(/only 127\.0\.0\.1 is allowed/);
  });

  it("splits a shell-form command, honouring quotes", () => {
    expect(splitCommand(`bash -lc "echo one two"`)).toEqual(["bash", "-lc", "echo one two"]);
    expect(splitCommand(`a 'b c' d`)).toEqual(["a", "b c", "d"]);
    expect(() => splitCommand(`a "unterminated`)).toThrow(/unterminated/);
  });
});

describe("parseComposeFile on the v3 fixture", () => {
  it("parses exactly one service, with no freesurfer and no X11 (decisions D2/D3)", () => {
    const stack = parseFixture();
    expect(Object.keys(stack.services)).toEqual(["tit"]);
    expect(stack.services.tit?.environment.DISPLAY).toBeUndefined();
    expect(JSON.stringify(stack)).not.toMatch(/X11|Xauthority|freesurfer/i);
  });

  it("interpolates the project mount and the published port from the env map", () => {
    const tit = parseFixture().services.tit;
    expect(tit?.volumes).toContainEqual({ source: "/Users/ido/datasets/000", target: "/mnt/000", readOnly: false, named: false });
    expect(tit?.ports).toEqual([{ hostIp: "127.0.0.1", hostPort: 8801, containerPort: 8801, protocol: "tcp" }]);
    expect(tit?.environment.TIT_SERVER_TOKEN).toBe("sekret");
  });

  it("uses the :- default when the app does not set the variable", () => {
    expect(parseFixture().services.tit?.environment.TIT_STATIC_DIR).toBe("/opt/ti-toolbox/ui");
  });

  it("marks a mount of a declared top-level volume as named", () => {
    const named = parseFixture().services.tit?.volumes.filter((v) => v.named);
    expect(named).toEqual([{ source: "tit_cache", target: "/opt/ti-toolbox/cache", readOnly: false, named: true }]);
  });

  it("reads the healthcheck, converting its durations to nanoseconds", () => {
    const hc = parseFixture().services.tit?.healthcheck;
    expect(hc?.test[0]).toBe("CMD-SHELL");
    expect(hc?.test[1]).toContain("8801"); // interpolated, not left as ${TIT_SERVER_PORT}
    expect(hc?.intervalNs).toBe(10_000_000_000);
    expect(hc?.timeoutNs).toBe(3_000_000_000);
    expect(hc?.startPeriodNs).toBe(20_000_000_000);
    expect(hc?.retries).toBe(30);
  });

  it("keeps platform and init, which the container create body needs", () => {
    const tit = parseFixture().services.tit;
    expect(tit?.platform).toBe("linux/amd64");
    expect(tit?.init).toBe(true);
    expect(tit?.workingDir).toBe("/ti-toolbox");
  });

  // `/ti-toolbox` is where the image checks the repo out and pip-installs `tit` from, so a bind
  // there replaces the image's own toolbox. It must appear only when a developer asked for it.
  it("drops the dev-repo mount entirely when TIT_REPO_DIR is empty", () => {
    const targets = parseFixture().services.tit?.volumes.map((v) => v.target);
    expect(targets).not.toContain("/ti-toolbox");
  });

  it("drops it just the same when TIT_REPO_DIR is absent from the env map altogether", () => {
    const stack = parseComposeFile(readFileSync(FIXTURE, "utf8"), ENV);
    expect(stack.services.tit?.volumes.map((v) => v.target)).not.toContain("/ti-toolbox");
  });

  it("mounts it when TIT_REPO_DIR names a directory", () => {
    const stack = parseComposeFile(readFileSync(FIXTURE, "utf8"), { ...ENV, TIT_REPO_DIR: "/Users/ido/repo" });
    expect(stack.services.tit?.volumes).toContainEqual({ source: "/Users/ido/repo", target: "/ti-toolbox", readOnly: false, named: false });
  });

  it("an empty *target* is still an error — an optional mount is an empty source, not a broken line", () => {
    const text = `
services:
  tit:
    image: x:1
    ports: ["127.0.0.1:1:1"]
    volumes:
      - /host:\${NOTHING:-}
`;
    expect(() => parseComposeFile(text, {})).toThrow(StackError);
  });
});

describe("parseComposeFile rejects what it cannot realise", () => {
  const base = `
services:
  tit:
    image: x:1
    ports: ["127.0.0.1:1:1"]
`;

  it("names an unsupported top-level key", () => {
    expect(() => parseComposeFile(base + "\nconfigs:\n  a: {}\n", {})).toThrow(/configs is not supported/);
  });

  it("names an unsupported service key — the legacy file's depends_on/tty/stdin_open", () => {
    for (const key of ["depends_on: [freesurfer]", "tty: true", "stdin_open: true", "env_file: .env"]) {
      const err = (() => {
        try {
          parseComposeFile(base + `    ${key}\n`, {});
          return null;
        } catch (e) {
          return e as StackError;
        }
      })();
      expect(err).toBeInstanceOf(StackError);
      expect(err?.key).toBe(`services.tit.${key.split(":")[0]}`);
    }
  });

  it("names an unsupported healthcheck key", () => {
    expect(() => parseComposeFile(base + "    healthcheck:\n      test: [CMD, true]\n      start_interval: 1s\n", {})).toThrow(/healthcheck.start_interval is not supported/);
  });

  it("names an unsupported network or volume key", () => {
    expect(() => parseComposeFile(base + "\nnetworks:\n  n:\n    external: true\n", {})).toThrow(/networks.n.external is not supported/);
    expect(() => parseComposeFile(base + "\nvolumes:\n  v:\n    external: true\n", {})).toThrow(/volumes.v.external is not supported/);
  });

  it("refuses a service that names a network the file does not declare", () => {
    expect(() => parseComposeFile(base + "    networks: [missing]\n", {})).toThrow(/not declared under networks/);
  });

  it("refuses a file with no services, and one that is not YAML", () => {
    expect(() => parseComposeFile("services: {}\n", {})).toThrow(/no services are declared/);
    expect(() => parseComposeFile("services:\n  - [\n", {})).toThrow(StackError);
  });

  it("accepts and ignores the obsolete top-level version key", () => {
    expect(Object.keys(parseComposeFile('version: "3.8"\n' + base, {}).services)).toEqual(["tit"]);
  });
});

describe("buildContainerPlan", () => {
  const plan = () =>
    buildContainerPlan(parseFixture(), {
      serviceName: "tit",
      projectName: "ti-toolbox-deadbeef",
      labels: { "tit.project": "ti-toolbox-deadbeef", "tit.stack": "ti-toolbox-v3" },
    });

  it("names the container, network and volume the way compose itself would", () => {
    const p = plan();
    expect(p.containerName).toBe("ti-toolbox-deadbeef-tit-1");
    expect(p.networkName).toBe("ti-toolbox-deadbeef_ti_network");
    expect(p.namedVolumes).toEqual(["ti-toolbox-deadbeef_tit_cache"]);
    expect(resolvedName("p", "v", "explicit")).toBe("explicit");
  });

  it("splits the image reference for the pull call", () => {
    expect(plan().imageName).toBe("idossha/ti-toolbox");
    expect(plan().imageTag).toBe("v3.0.0-dev");
  });

  it("publishes the port on 127.0.0.1 only", () => {
    expect(plan().body.HostConfig.PortBindings).toEqual({ "8801/tcp": [{ HostIp: "127.0.0.1", HostPort: "8801" }] });
    expect(plan().body.ExposedPorts).toEqual({ "8801/tcp": {} });
  });

  it("merges the app's labels over the compose file's own", () => {
    expect(plan().body.Labels).toMatchObject({ "org.ti-toolbox.service": "tit", "tit.project": "ti-toolbox-deadbeef", "tit.stack": "ti-toolbox-v3" });
  });

  it("resolves the named volume in Binds and leaves host paths alone", () => {
    expect(plan().body.HostConfig.Binds).toEqual([
      "/Users/ido/datasets/000:/mnt/000",
      "/Users/ido/.config/ti-toolbox:/root/.config/ti-toolbox",
      "/var/run/docker.sock:/var/run/docker.sock",
      "ti-toolbox-deadbeef_tit_cache:/opt/ti-toolbox/cache",
    ]);
  });

  it("carries init, working dir, restart policy, network and healthcheck into the create body", () => {
    const body = plan().body;
    expect(body.HostConfig.Init).toBe(true);
    expect(body.WorkingDir).toBe("/ti-toolbox");
    expect(body.HostConfig.RestartPolicy).toEqual({ Name: "unless-stopped" });
    expect(body.HostConfig.NetworkMode).toBe("ti-toolbox-deadbeef_ti_network");
    expect(body.NetworkingConfig?.EndpointsConfig).toHaveProperty("ti-toolbox-deadbeef_ti_network");
    expect(body.Healthcheck?.Interval).toBe(10_000_000_000);
  });

  it("passes the environment as KEY=VALUE strings", () => {
    expect(plan().body.Env).toContain("TIT_SERVER_TOKEN=sekret");
    expect(plan().body.Env).toContain("TIT_SERVER_PORT=8801");
  });

  it("refuses a service that publishes no port or more than one", () => {
    const two = parseComposeFile('services:\n  tit:\n    image: x:1\n    ports: ["127.0.0.1:1:1", "127.0.0.1:2:2"]\n', {});
    expect(() => buildContainerPlan(two, { serviceName: "tit", projectName: "p", labels: {} })).toThrow(/exactly one port/);
    const none = parseComposeFile("services:\n  tit:\n    image: x:1\n", {});
    expect(() => buildContainerPlan(none, { serviceName: "tit", projectName: "p", labels: {} })).toThrow(/exactly one port/);
  });

  it("refuses a service name the file does not declare", () => {
    expect(() => buildContainerPlan(parseFixture(), { serviceName: "freesurfer", projectName: "p", labels: {} })).toThrow(/no service named "freesurfer"/);
  });
});

/**
 * The shipped file, whichever generation of it is on disk. Lane W2 is rewriting it to the one-`tit`
 * shape; until that lands the tree still holds the legacy two-service file, and the assertion worth
 * making about *that* one is that the parser refuses it by name rather than silently dropping its
 * freesurfer service and X11 mounts.
 */
describe("the shipped docker-compose.v3.yml", () => {
  const text = readFileSync(SHIPPED, "utf8");
  const rewritten = !/^\s*freesurfer:/m.test(text);

  it(rewritten ? "parses into a single tit service on loopback" : "is still the legacy file, and is refused by name", () => {
    if (!rewritten) {
      let thrown: StackError | null = null;
      try {
        parseComposeFile(text, { ...ENV, DISPLAY: ":0", HOME: "/Users/ido", TIT_REPO_DIR: "/repo" });
      } catch (err) {
        thrown = err as StackError;
      }
      expect(thrown).toBeInstanceOf(StackError);
      expect(thrown?.message).toMatch(/is not supported by this app/);
      return;
    }
    const stack = parseComposeFile(text, { ...ENV, TIT_REPO_DIR: "/repo" });
    expect(Object.keys(stack.services)).toEqual(["tit"]);
    expect(stack.services.tit?.ports[0]?.hostIp).toBe("127.0.0.1");
    expect(JSON.stringify(stack)).not.toMatch(/X11|Xauthority|freesurfer/i);
    const plan = buildContainerPlan(stack, { serviceName: "tit", projectName: "ti-toolbox-deadbeef", labels: {} });
    expect(plan.imageName).toMatch(/ti-toolbox/);
  });

  // The shipped file is the one a packaged app reads, so the "no dev mount by default" property is
  // asserted against it directly, not only against the fixture that mirrors it.
  it("bind-mounts nothing over /ti-toolbox by default, and does when a repo is named", () => {
    if (!rewritten) return;
    const withoutRepo = parseComposeFile(text, { ...ENV, TIT_REPO_DIR: "" });
    const plan = buildContainerPlan(withoutRepo, { serviceName: "tit", projectName: "ti-toolbox-deadbeef", labels: {} });
    expect(plan.body.HostConfig.Binds.join(" ")).not.toContain(":/ti-toolbox");

    const withRepo = parseComposeFile(text, { ...ENV, TIT_REPO_DIR: "/Users/ido/repo" });
    const devPlan = buildContainerPlan(withRepo, { serviceName: "tit", projectName: "ti-toolbox-deadbeef", labels: {} });
    expect(devPlan.body.HostConfig.Binds).toContain("/Users/ido/repo:/ti-toolbox");
  });
});
