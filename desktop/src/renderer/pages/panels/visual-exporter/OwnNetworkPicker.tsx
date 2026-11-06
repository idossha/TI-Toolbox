/**
 * "Your own file" on the Networks tab: a streamline file made for this head model, loaded once and
 * kept under the subject (`tit/tract/own.py`), so it is here on later runs. The server checks it
 * against the head model before anything is stored or queued, and its refusal is shown as it says it.
 */
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { Button } from "../../../ui/Button";
import { Callout } from "../../../ui/Feedback";
import { Field } from "../../../ui/Field";
import { Select } from "../../../ui/Select";
import { getOwnNetworks, loadOwnNetwork, type OwnNetwork } from "./api";

const count = (n: number): string => n.toLocaleString("en-US");
const percent = (fraction: number): string => `${(fraction * 100).toFixed(1)} %`;

export function OwnNetworkPicker({ subject, value, onChange }: { subject: string; value: string; onChange: (name: string) => void }) {
  const client = useQueryClient();
  const own = useQuery({ queryKey: ["tract-own", subject], queryFn: () => getOwnNetworks(subject) });
  const input = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chosen: OwnNetwork | undefined = own.data?.find((file) => file.name === value);

  async function load(file: File) {
    setLoading(true);
    setError(null);
    try {
      const record = await loadOwnNetwork(file, subject);
      await client.invalidateQueries({ queryKey: ["tract-own", subject] });
      onChange(record.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this file.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }} data-testid="ve-own-file">
      <Field label="Your own file" help={`A .trx, .tck or .trk file you made for sub-${subject}'s head model, in its T1 space (world RAS mm). It is kept under the subject and is checked before anything runs.`}>
        <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
          {(own.data?.length ?? 0) > 0 && (
            <Select id="ve-own-network" value={value || undefined} onValueChange={onChange} placeholder="Choose a loaded file" options={own.data!.map((file) => ({ value: file.name, label: file.source_filename }))} />
          )}
          <Button variant="secondary" icon={<Upload size={14} />} loading={loading} onClick={() => input.current?.click()} data-testid="ve-own-load">
            {loading ? "Checking…" : "Load a file…"}
          </Button>
          <input ref={input} type="file" accept=".trx,.tck,.trk" aria-label="Load a streamline file" hidden data-testid="ve-own-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void load(file);
            }} />
        </div>
      </Field>
      {error && <div data-testid="ve-own-error"><Callout kind="danger">{error}</Callout></div>}
      {own.error && <Callout kind="danger">{own.error.message}</Callout>}
      {chosen && (
        <div className="field-help" data-testid="ve-own-checks">
          <p>
            {count(chosen.n_streamlines)} streamlines · {percent(chosen.checks.fraction_points_in_brain)} of points in the brain, {percent(chosen.checks.fraction_points_in_head)} in the head · regions from {chosen.atlas}: {count(chosen.n_both_ends_labelled)} with both ends labelled, {count(chosen.n_unlabelled)} left unlabelled and still drawn.
          </p>
          <p>{chosen.checks.not_proven}</p>
        </div>
      )}
    </div>
  );
}
