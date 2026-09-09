# Developer documentation

Start with [CONTRIBUTING.md](CONTRIBUTING.md) to run the application locally, then read
[ARCHITECTURE.md](ARCHITECTURE.md) for the relevant subsystem. Agents enter through
[AGENTS.md](../../AGENTS.md); MCP clients can use `read_dev_doc` to read these same files.
These developer pages are excluded from the documentation website.

## Ownership

| Page | Owns | Update style |
|---|---|---|
| [ARCHITECTURE](ARCHITECTURE.md) | Components, data flow, boundaries and invariants | Revise to match current code |
| [DESIGN](DESIGN.md) | UI behavior and interaction conventions | Revise to match the current product |
| [CONTRIBUTING](CONTRIBUTING.md) | Local development, tests and shared-checkout workflow | Keep commands current |
| [RELEASE](RELEASE.md) | Build/distribution procedure, current acceptance work and roadmap | Replace stale status; remove completed tasks |
| [BENCHMARKS](BENCHMARKS.md) | Reproducible validation and performance evidence, with scope and limitations | Keep useful baselines; replace superseded receipts |
| [DECISIONS](DECISIONS.md) | Significant choices, rationale and dated milestones | Append significant decisions/milestones; mark reversals as superseded |

## Keep the set concise

A fact has one owner. Link to it from other pages instead of copying paragraphs or test tables.
Current-state documents are editable references, not append-only journals. Routine test runs,
temporary paths, agent handoffs and verbatim conversations belong in run artifacts or Git history.
Retain decision identities where code cites them, but do not preserve obsolete implementation plans
as current requirements. Full earlier documentation remains available through Git history.

User-visible fixes and upgrade guidance belong in [release notes](../releases/v3.0.0.md), with a
brief [changelog](../releases/changelog.md) entry. Scientific corrections use the same process:
state affected workflows and actions proportionately, without a separate developer audit document.

## Adjacent references

- [Root CONTRIBUTING](../../CONTRIBUTING.md): branch and pull-request policy.
- [Contracts](../../contracts/README.md): generated schemas and contract-change procedure;
  [CHANGES](../../contracts/CHANGES.md) retains its append-only record.
- [Desktop](../../desktop/README.md) and [container blueprint](../../container/blueprint/README.md):
  component-specific commands.
- [Docs site](../README.md): localhost preview and API generation.
- [Agent plugin](../../agent-plugin/README.md): portable skills and read-only MCP access.
- [Wiki](../wiki/overview.md): user workflows; module READMEs: subsystem APIs.

Old `TODO.md`, roadmap, spike and lane-note paths are historical references. Current open work is
in [RELEASE.md](RELEASE.md#b-current-readiness-and-follow-ups); use Git history for retired plans.
