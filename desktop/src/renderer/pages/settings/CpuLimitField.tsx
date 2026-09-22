import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../ui/Button";
import { InlineError } from "../../ui/Feedback";
import { Field } from "../../ui/Field";
import { Slider } from "../../ui/Toggle";
import { getCpuLimit, putCpuLimit } from "./api";

/** Cores a percent resolves to — the server's own rule (`tit.cpu.cpu_limit`). */
export function coresFor(percent: number, available: number): number {
  return Math.max(1, Math.floor((percent * available) / 100));
}

/**
 * The global CPU limit (user-wide, `GET/PUT /api/cpu-limit`): the scheduler's CPU budget and what
 * every "use all the cores" default resolves to. Applied with its own button so dragging the slider
 * does not save every step; a change applies to jobs started after it.
 */
export function CpuLimitField() {
  const client = useQueryClient();
  const limit = useQuery({ queryKey: ["cpu-limit"], queryFn: getCpuLimit });
  const [draft, setDraft] = useState<number | null>(null);
  const save = useMutation({
    mutationFn: putCpuLimit,
    onSuccess: (next) => {
      client.setQueryData(["cpu-limit"], next);
      setDraft(null);
    },
  });
  const data = limit.data;
  const percent = draft ?? data?.percent ?? 70;
  const available = data?.available_cores ?? 0;
  return (
    <Field
      label="CPU limit"
      help={`Share of this machine's cores TI-Toolbox jobs may use together. Default ${data?.default_percent ?? 70} % leaves headroom for your computer; raise it for faster searches.`}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <div style={{ width: 260, maxWidth: "100%" }}>
          <Slider value={percent} onValueChange={setDraft} min={10} max={100} step={5} unit="%" showNumberInput={false} disabled={!data} aria-label="CPU limit" />
        </div>
        <span className="field-help mono" data-testid="cpu-limit-summary">
          {data ? `${percent} % · ${coresFor(percent, available)} of ${available} cores` : "…"}
        </span>
        <Button size="sm" disabled={draft === null || draft === data?.percent} loading={save.isPending} onClick={() => draft !== null && save.mutate(draft)}>
          Apply
        </Button>
      </div>
      {(limit.error || save.error) && <InlineError message={(limit.error || save.error)!.message} />}
    </Field>
  );
}
