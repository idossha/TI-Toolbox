/**
 * What ⌘K can reach (plan §1). The palette is the only place a shortcut is learned now that the
 * nav rows carry no badges, and it is the only way to reach a hidden page — so the list itself,
 * not its rendering, is what is worth pinning.
 */
import { describe, expect, it, vi } from "vitest";
import { buildCommands, groupCommands, type Command, type CommandContext } from "../../src/renderer/app/commands";

function ctx(over: Partial<CommandContext> = {}): CommandContext {
  return {
    pageCommands: [],
    pages: [
      { id: "subjects", title: "Subjects", purpose: "Browse subjects.", shortcut: "1" },
      { id: "dev", title: "Gallery", purpose: "Component gallery." },
    ],
    subjects: [{ id: "ernie" }, { id: "bert" }],
    runningJobs: [],
    theme: "system",
    modKey: (k) => `⌘${k}`,
    modShiftKey: (k) => `⌘⇧${k}`,
    navigate: vi.fn(),
    setSubject: vi.fn(),
    setTheme: vi.fn(),
    openJobs: vi.fn(),
    openKeyboardSheet: vi.fn(),
    openQuickNotes: vi.fn(),
    ...over,
  };
}

const find = (list: Command[], id: string) => list.find((c) => c.id === id);

describe("buildCommands", () => {
  it("lists every page it is given, hidden ones included — that is what palette-only means", () => {
    const list = buildCommands(ctx());
    expect(find(list, "page:subjects")?.label).toBe("Subjects");
    expect(find(list, "page:dev")?.label).toBe("Gallery");
  });

  it("teaches the shortcut in the hint, since the nav rows no longer carry badges", () => {
    const list = buildCommands(ctx());
    expect(find(list, "page:subjects")?.hint).toBe("⌘1");
    expect(find(list, "page:dev")?.hint).toBeUndefined();
  });

  it("matches a page on its purpose without printing it", () => {
    const row = find(buildCommands(ctx()), "page:subjects")!;
    expect(row.keywords).toBe("Browse subjects.");
    expect(row.label).toBe("Subjects");
  });

  it("navigates by page id", () => {
    const c = ctx();
    find(buildCommands(c), "page:subjects")!.run();
    expect(c.navigate).toHaveBeenCalledWith("/subjects");
  });

  it("switches the subject rather than navigating", () => {
    const c = ctx();
    const row = find(buildCommands(c), "subject:bert")!;
    expect(row.section).toBe("Subjects");
    row.run();
    expect(c.setSubject).toHaveBeenCalledWith("bert");
    expect(c.navigate).not.toHaveBeenCalled();
  });

  it("lists running jobs with their state and opens the jobs panel", () => {
    const c = ctx({
      runningJobs: [{ id: "job-12", kind: "simulation", subject_ids: ["ernie"], state: "running" }],
    });
    const row = find(buildCommands(c), "job:job-12")!;
    expect(row.label).toBe("simulation · ernie");
    expect(row.hint).toBe("running");
    expect(row.keywords).toBe("job-12");
    row.run();
    expect(c.openJobs).toHaveBeenCalledOnce();
  });

  it("shows a job with no subject as an em dash rather than an empty label", () => {
    const c = ctx({ runningJobs: [{ id: "j", kind: "leadfield", subject_ids: [], state: "queued" }] });
    expect(find(buildCommands(c), "job:j")?.label).toBe("leadfield · —");
  });

  it("carries the three theme settings and marks the current one", () => {
    const c = ctx({ theme: "dark" });
    const list = buildCommands(c);
    expect(list.filter((x) => x.id.startsWith("theme:")).map((x) => x.label)).toEqual([
      "Theme: system",
      "Theme: light",
      "Theme: dark",
    ]);
    expect(find(list, "theme:dark")?.hint).toBe("current");
    expect(find(list, "theme:light")?.hint).toBeUndefined();
    find(list, "theme:light")!.run();
    expect(c.setTheme).toHaveBeenCalledWith("light");
  });

  it("carries the app's own verbs with their shortcuts", () => {
    const c = ctx();
    const list = buildCommands(c);
    expect(find(list, "action:settings")?.hint).toBe("⌘,");
    expect(find(list, "action:notes")?.hint).toBe("⌘⇧N");
    expect(find(list, "action:jobs")?.hint).toBe("⌘J");
    expect(find(list, "action:keys")?.hint).toBe("?");
    find(list, "action:help")!.run();
    expect(c.navigate).toHaveBeenCalledWith("/help");
    find(list, "action:keys")!.run();
    expect(c.openKeyboardSheet).toHaveBeenCalledOnce();
    find(list, "action:notes")!.run();
    expect(c.openQuickNotes).toHaveBeenCalledOnce();
  });

  it("puts the page's own commands first, ahead of navigation", () => {
    const pageCommand: Command = { id: "run", label: "Run simulation", section: "Page", run: vi.fn() };
    const list = buildCommands(ctx({ pageCommands: [pageCommand] }));
    expect(list[0]).toBe(pageCommand);
  });

  it("gives every entry a unique id", () => {
    const list = buildCommands(ctx({ runningJobs: [{ id: "a", kind: "k", subject_ids: [], state: "running" }] }));
    expect(new Set(list.map((c) => c.id)).size).toBe(list.length);
  });
});

describe("groupCommands", () => {
  it("orders the sections Page · Pages · Subjects · Jobs · Actions and drops the empty ones", () => {
    const list = buildCommands(
      ctx({
        pageCommands: [{ id: "run", label: "Run", section: "Page", run: vi.fn() }],
        runningJobs: [{ id: "a", kind: "k", subject_ids: [], state: "running" }],
      }),
    );
    expect(groupCommands(list).map((g) => g.section)).toEqual(["Page", "Pages", "Subjects", "Jobs", "Actions"]);
  });

  it("drops Page and Jobs when the screen registered nothing and nothing is running", () => {
    expect(groupCommands(buildCommands(ctx())).map((g) => g.section)).toEqual(["Pages", "Subjects", "Actions"]);
  });

  it("drops Subjects in a project with none", () => {
    expect(groupCommands(buildCommands(ctx({ subjects: [] }))).map((g) => g.section)).toEqual(["Pages", "Actions"]);
  });
});
