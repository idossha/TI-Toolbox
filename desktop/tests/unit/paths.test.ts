import { describe, expect, it } from "vitest";
import {
  containerToHostPath,
  hasDotSegment,
  hostToContainerPath,
  mapContainerToHostViaProjectRoot,
  mapHostToContainerViaProjectRoot,
  type ProjectMount,
} from "../../src/shared/paths";

describe("hostToContainerPath / containerToHostPath", () => {
  describe("Windows drive paths", () => {
    const mount: ProjectMount = { hostDir: "C:\\Users\\ido\\datasets\\000", platform: "win32" };

    it("maps a nested host path into the mount", () => {
      expect(hostToContainerPath("C:\\Users\\ido\\datasets\\000\\derivatives\\SimNIBS\\x.nii.gz", mount)).toBe(
        "/mnt/000/derivatives/SimNIBS/x.nii.gz",
      );
    });

    it("maps the project root itself", () => {
      expect(hostToContainerPath("C:\\Users\\ido\\datasets\\000", mount)).toBe("/mnt/000");
    });

    it("round-trips container -> host with backslashes", () => {
      expect(containerToHostPath("/mnt/000/derivatives/x.nii.gz", mount)).toBe(
        "C:\\Users\\ido\\datasets\\000\\derivatives\\x.nii.gz",
      );
    });

    it("is case-insensitive on the drive letter and segments", () => {
      expect(hostToContainerPath("c:\\USERS\\Ido\\DATASETS\\000\\a.txt", mount)).toBe("/mnt/000/a.txt");
    });

    it("returns null for a path outside the project", () => {
      expect(hostToContainerPath("C:\\Users\\ido\\datasets\\other\\a.txt", mount)).toBeNull();
    });

    it("accepts forward-slash Windows paths too (Docker Desktop's own convention)", () => {
      expect(hostToContainerPath("C:/Users/ido/datasets/000/a.txt", mount)).toBe("/mnt/000/a.txt");
    });
  });

  describe("WSL UNC paths", () => {
    const mount: ProjectMount = { hostDir: "\\\\wsl.localhost\\Ubuntu\\home\\ido\\datasets\\000", platform: "win32" };

    it("maps a nested path", () => {
      expect(hostToContainerPath("\\\\wsl.localhost\\Ubuntu\\home\\ido\\datasets\\000\\sub\\a.txt", mount)).toBe(
        "/mnt/000/sub/a.txt",
      );
    });

    it("round-trips back to the UNC form", () => {
      expect(containerToHostPath("/mnt/000/sub/a.txt", mount)).toBe(
        "\\\\wsl.localhost\\Ubuntu\\home\\ido\\datasets\\000\\sub\\a.txt",
      );
    });

    it("treats a different distro (different UNC share) as outside the project", () => {
      expect(hostToContainerPath("\\\\wsl.localhost\\Debian\\home\\ido\\datasets\\000\\a.txt", mount)).toBeNull();
    });

    it("also recognises the legacy \\\\wsl$\\ form", () => {
      const legacyMount: ProjectMount = { hostDir: "\\\\wsl$\\Ubuntu\\home\\ido\\000", platform: "win32" };
      expect(hostToContainerPath("\\\\wsl$\\Ubuntu\\home\\ido\\000\\a.txt", legacyMount)).toBe("/mnt/000/a.txt");
    });
  });

  describe("macOS roots (case-insensitive by default)", () => {
    const mount: ProjectMount = { hostDir: "/Users/Ido/datasets/000", platform: "darwin" };

    it("maps a nested path with matching case", () => {
      expect(hostToContainerPath("/Users/Ido/datasets/000/derivatives/a.txt", mount)).toBe("/mnt/000/derivatives/a.txt");
    });

    it("maps a path that differs only in case (APFS default is case-insensitive)", () => {
      expect(hostToContainerPath("/users/ido/DATASETS/000/a.txt", mount)).toBe("/mnt/000/a.txt");
    });

    it("round-trips back to the original host casing (from the mount, not the request)", () => {
      expect(containerToHostPath("/mnt/000/a.txt", mount)).toBe("/Users/Ido/datasets/000/a.txt");
    });

    it("returns null outside the project", () => {
      expect(hostToContainerPath("/Users/Ido/datasets/other/a.txt", mount)).toBeNull();
    });
  });

  describe("Linux roots (case-sensitive)", () => {
    const mount: ProjectMount = { hostDir: "/home/ido/datasets/000", platform: "linux" };

    it("maps a nested path with matching case", () => {
      expect(hostToContainerPath("/home/ido/datasets/000/a.txt", mount)).toBe("/mnt/000/a.txt");
    });

    it("does NOT map a path that differs only in case", () => {
      expect(hostToContainerPath("/home/ido/DATASETS/000/a.txt", mount)).toBeNull();
    });
  });

  describe("containerToHostPath edge cases", () => {
    const mount: ProjectMount = { hostDir: "/home/ido/datasets/000", platform: "linux" };

    it("rejects a container path for a different project mount", () => {
      expect(containerToHostPath("/mnt/other-project/a.txt", mount)).toBeNull();
    });

    it("rejects a container path that merely shares the prefix as a substring", () => {
      // "/mnt/0001" must not match the "/mnt/000" mount.
      expect(containerToHostPath("/mnt/0001/a.txt", mount)).toBeNull();
    });

    it("maps the bare mount root", () => {
      expect(containerToHostPath("/mnt/000", mount)).toBe("/home/ido/datasets/000");
    });
  });
});

describe("mapContainerToHostViaProjectRoot", () => {
  it("maps a nested path via an arbitrary (containerRoot, hostRoot) pair, not the /mnt/<name> convention", () => {
    expect(
      mapContainerToHostViaProjectRoot(
        "/data/project/derivatives/SimNIBS/x.nii.gz",
        "/data/project",
        "/Users/ido/datasets/000",
        "darwin",
      ),
    ).toBe("/Users/ido/datasets/000/derivatives/SimNIBS/x.nii.gz");
  });

  it("maps the bare project root", () => {
    expect(mapContainerToHostViaProjectRoot("/data/project", "/data/project", "/Users/ido/datasets/000", "darwin")).toBe(
      "/Users/ido/datasets/000",
    );
  });

  it("returns null when hostRoot is unknown (Project.host_path was null)", () => {
    expect(mapContainerToHostViaProjectRoot("/data/project/a.txt", "/data/project", null, "darwin")).toBeNull();
  });

  it("returns null for a path outside containerRoot", () => {
    expect(mapContainerToHostViaProjectRoot("/data/other/a.txt", "/data/project", "/Users/ido/datasets/000", "darwin")).toBeNull();
  });

  it("rejects a path that merely shares the prefix as a substring", () => {
    expect(mapContainerToHostViaProjectRoot("/data/project2/a.txt", "/data/project", "/Users/ido/datasets/000", "darwin")).toBeNull();
  });

  it("maps to Windows host syntax", () => {
    expect(mapContainerToHostViaProjectRoot("/mnt/proj/a.txt", "/mnt/proj", "C:\\Users\\ido\\proj", "win32")).toBe(
      "C:\\Users\\ido\\proj\\a.txt",
    );
  });
});

describe("hasDotSegment (ra_14 finding 3)", () => {
  it.each([
    ["/mnt/proj/../etc/passwd"],
    ["/mnt/proj/./secret"],
    ["..\\..\\Windows\\System32"],
    [".\\config"],
    ["/mnt/proj/a/../../outside"],
    [".."],
    ["."],
    ["/mnt/proj/a/..\\b"], // mixed separators
  ])("flags %s", (path) => {
    expect(hasDotSegment(path)).toBe(true);
  });

  it.each([
    ["/mnt/proj/derivatives/x.nii.gz"],
    ["/mnt/proj/a..b/file.txt"], // a dot *inside* a segment, not the whole segment
    ["/mnt/proj/..hidden/file"], // dotfile-style prefix, not a literal ".." segment
    ["/mnt/proj"],
    [""],
  ])("does not flag %s", (path) => {
    expect(hasDotSegment(path)).toBe(false);
  });
});

describe("mapHostToContainerViaProjectRoot (ra_13 finding 8)", () => {
  it("maps a nested host path via an arbitrary (containerRoot, hostRoot) pair", () => {
    expect(
      mapHostToContainerViaProjectRoot(
        "/Users/ido/datasets/000/derivatives/SimNIBS/x.nii.gz",
        "/data/project",
        "/Users/ido/datasets/000",
        "darwin",
      ),
    ).toBe("/data/project/derivatives/SimNIBS/x.nii.gz");
  });

  it("maps the bare project root", () => {
    expect(mapHostToContainerViaProjectRoot("/Users/ido/datasets/000", "/data/project", "/Users/ido/datasets/000", "darwin")).toBe(
      "/data/project",
    );
  });

  it("returns null when hostRoot is unknown (Project.host_path was null)", () => {
    expect(mapHostToContainerViaProjectRoot("/Users/ido/datasets/000/a.txt", "/data/project", null, "darwin")).toBeNull();
  });

  it("returns null for a host path outside hostRoot", () => {
    expect(mapHostToContainerViaProjectRoot("/Users/ido/datasets/other/a.txt", "/data/project", "/Users/ido/datasets/000", "darwin")).toBeNull();
  });

  it("rejects a path that merely shares the prefix as a substring", () => {
    expect(
      mapHostToContainerViaProjectRoot("/Users/ido/datasets/0001/a.txt", "/data/project", "/Users/ido/datasets/000", "darwin"),
    ).toBeNull();
  });

  it("round-trips with mapContainerToHostViaProjectRoot", () => {
    const containerRoot = "/data/project";
    const hostRoot = "/Users/ido/datasets/000";
    const hostPath = "/Users/ido/datasets/000/derivatives/a.txt";
    const container = mapHostToContainerViaProjectRoot(hostPath, containerRoot, hostRoot, "darwin");
    expect(container).toBe("/data/project/derivatives/a.txt");
    expect(mapContainerToHostViaProjectRoot(container as string, containerRoot, hostRoot, "darwin")).toBe(hostPath);
  });

  it("is case-sensitive on Linux", () => {
    expect(mapHostToContainerViaProjectRoot("/home/ido/DATASETS/000/a.txt", "/data/project", "/home/ido/datasets/000", "linux")).toBeNull();
  });

  it("maps from Windows host syntax", () => {
    expect(mapHostToContainerViaProjectRoot("C:\\Users\\ido\\proj\\a.txt", "/mnt/proj", "C:\\Users\\ido\\proj", "win32")).toBe(
      "/mnt/proj/a.txt",
    );
  });
});
