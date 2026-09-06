import { Plus, Trash2, MapPin } from "lucide-react";
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { Button, IconButton } from "../../ui/Button";
import { Checkbox } from "../../ui/Toggle";
import { Field, TextInput } from "../../ui/Field";
import { NumberInput } from "../../ui/NumberInput";
import { Select } from "../../ui/Select";
import { Callout, EmptyState, Skeleton } from "../../ui/Feedback";
import { Card, CardHeader, CardBody } from "../../ui/Layout";
import { notify } from "../../ui/Toast";
import { usePageSession } from "../../app/pageSession";
import { getFreehand, putFreehand, type ElectrodePosition, type FreehandConfig } from "./api";
import { defaultCurrents, type SelectedRow } from "./types";

/** Matches `Montage.simulation_mode`: 2 or 4+ pairs, i.e. 4 or 8+ positions (an even count). */
function isValidPositionCount(n: number): boolean {
  return n % 2 === 0 && (n / 2 === 2 || n / 2 >= 4);
}

function pairsFromPositions(positions: ElectrodePosition[]): [[number, number, number], [number, number, number]][] {
  const out: [[number, number, number], [number, number, number]][] = [];
  for (let i = 0; i + 1 < positions.length; i += 2) {
    const a = positions[i];
    const b = positions[i + 1];
    if (!a || !b) continue;
    out.push([
      [a.x, a.y, a.z],
      [b.x, b.y, b.z],
    ]);
  }
  return out;
}

function rowId(subject: string, name: string) {
  return `freehand:${subject}:${name}`;
}

const EMPTY_POSITION: ElectrodePosition = { label: "", x: 0, y: 0, z: 0 };

export function FreehandTab({
  selectedSubjects,
  selectedRows,
  onAddRow,
  onRemoveRow,
}: {
  selectedSubjects: string[];
  selectedRows: SelectedRow[];
  onAddRow: (row: SelectedRow) => void;
  onRemoveRow: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const queries = useQueries({
    queries: selectedSubjects.map((subject) => ({
      queryKey: ["freehand", subject],
      queryFn: () => getFreehand(subject),
    })),
  });

  // Source tabs may unmount the editor; an unfinished placement belongs to the project session.
  const [editSubject, setEditSubject] = usePageSession<string | undefined>("freehand.subject", undefined);
  const [name, setName] = usePageSession("freehand.name", "");
  const [positions, setPositions] = usePageSession<ElectrodePosition[]>("freehand.positions", () => [
    { ...EMPTY_POSITION }, { ...EMPTY_POSITION }, { ...EMPTY_POSITION }, { ...EMPTY_POSITION },
  ]);

  const activeEditSubject = editSubject ?? selectedSubjects[0];

  const save = useMutation({
    mutationFn: () => {
      // FreehandConfig.type is on-disk stim_configs semantics (unipolar/multipolar), not
      // xyz/label — U for a 2-pair (4-position) montage, M for 4+ pairs (8+ positions). See
      // contracts/openapi.v1.yaml's FreehandConfig doc comment / tit/catalog.py::_read_freehand_file.
      const type: FreehandConfig["type"] = positions.length / 2 >= 4 ? "M" : "U";
      return putFreehand(activeEditSubject!, name.trim(), { name: name.trim(), type, electrode_positions: positions });
    },
    onSuccess: () => {
      notify.success(`Saved free-hand configuration "${name.trim()}" for ${activeEditSubject}.`);
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["freehand", activeEditSubject] });
    },
    onError: (err: unknown) => notify.error("Could not save the free-hand configuration.", err instanceof Error ? err.message : undefined),
  });

  const isLoading = selectedSubjects.length > 0 && queries.some((q) => q.isPending);
  const rows: { subject: string; config: FreehandConfig }[] = [];
  selectedSubjects.forEach((subject, i) => {
    for (const config of queries[i]?.data ?? []) rows.push({ subject, config });
  });

  const validCount = isValidPositionCount(positions.length);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <Card>
        <CardHeader title="New free-hand configuration" />
        <CardBody>
          <div className="form-grid">
            <Field label="Subject" htmlFor="sim-freehand-subject" required>
              <Select
                id="sim-freehand-subject"
                value={activeEditSubject}
                onValueChange={setEditSubject}
                options={selectedSubjects.map((s) => ({ value: s, label: s }))}
                placeholder="Choose a subject"
                disabled={selectedSubjects.length === 0}
              />
            </Field>
            <Field label="Configuration name" htmlFor="sim-freehand-name" required>
              <TextInput id="sim-freehand-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. custom_4electrode" />
            </Field>
          </div>
          <div className="data-table-container scroll-x" style={{ marginTop: "var(--space-3)" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Label</th>
                  <th data-align="right">X (mm)</th>
                  <th data-align="right">Y (mm)</th>
                  <th data-align="right">Z (mm)</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, i) => (
                  <tr key={i}>
                    <td className="mono">{i + 1}</td>
                    <td>
                      <TextInput
                        value={pos.label ?? ""}
                        aria-label={`Position ${i + 1} label`}
                        placeholder="optional"
                        onChange={(e) => setPositions((p) => p.map((row, idx) => (idx === i ? { ...row, label: e.target.value } : row)))}
                      />
                    </td>
                    {(["x", "y", "z"] as const).map((axis) => (
                      <td key={axis} data-align="right">
                        <NumberInput
                          value={pos[axis]}
                          step={0.1}
                          onValueChange={(v) => setPositions((p) => p.map((row, idx) => (idx === i ? { ...row, [axis]: v ?? 0 } : row)))}
                          aria-label={`Position ${i + 1} ${axis.toUpperCase()}`}
                        />
                      </td>
                    ))}
                    <td>
                      <IconButton
                        aria-label={`Remove position ${i + 1}`}
                        icon={<Trash2 size={14} />}
                        disabled={positions.length <= 2}
                        onClick={() => setPositions((p) => p.filter((_, idx) => idx !== i))}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-3)" }}>
            <Button variant="ghost" size="sm" icon={<Plus size={14} />} onClick={() => setPositions((p) => [...p, { ...EMPTY_POSITION }])}>
              Add position
            </Button>
            <Button
              variant="primary"
              loading={save.isPending}
              disabled={!activeEditSubject || !name.trim() || !validCount || positions.some((p) => p.x === undefined || p.y === undefined || p.z === undefined)}
              onClick={() => save.mutate()}
            >
              Save configuration
            </Button>
          </div>
          {!validCount && <span className="field-error">Use 4 positions (2 pairs, standard TI) or 8 or more (4+ pairs, multi-channel mTI).</span>}
        </CardBody>
      </Card>

      {selectedSubjects.length === 0 && <Callout kind="info">Pick at least one subject above to see or add its free-hand configurations.</Callout>}
      {isLoading && <Skeleton height={100} />}
      {selectedSubjects.length > 0 && !isLoading && rows.length === 0 && (
        <EmptyState icon={<MapPin size={24} />} message="No free-hand configurations for the selected subjects yet — create one above." />
      )}
      {rows.length > 0 && (
        <div className="data-table-container scroll-x">
          <table className="data-table">
            <thead>
              <tr>
                <th />
                <th>Subject</th>
                <th>Configuration</th>
                <th>Positions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ subject, config }) => {
                const id = rowId(subject, config.name);
                const checked = selectedRows.some((r) => r.id === id);
                const pairs = pairsFromPositions(config.electrode_positions);
                return (
                  <tr key={id}>
                    <td>
                      <Checkbox
                        checked={checked}
                        disabled={pairs.length === 0}
                        onCheckedChange={(on) => {
                          if (on) {
                            onAddRow({
                              id,
                              subjectId: subject,
                              source: "freehand",
                              name: config.name,
                              xyzPairs: pairs,
                              currents: defaultCurrents(pairs.length),
                            });
                          } else {
                            onRemoveRow(id);
                          }
                        }}
                      />
                    </td>
                    <td className="mono">{subject}</td>
                    <td className="mono">{config.name}</td>
                    <td className="text-dense">{config.electrode_positions.length} positions ({pairs.length} pairs)</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
