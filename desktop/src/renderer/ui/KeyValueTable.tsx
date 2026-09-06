import { Plus, Trash2 } from "lucide-react";
import { IconButton, Button } from "./Button";
import { TextInput } from "./Field";

export interface KeyValueRow {
  key: string;
  value: string;
}

export function KeyValueTable({
  rows,
  onRowsChange,
  keyPlaceholder = "Key",
  valuePlaceholder = "Value",
  addLabel = "Add row",
  disabled,
}: {
  rows: KeyValueRow[];
  onRowsChange: (rows: KeyValueRow[]) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  addLabel?: string;
  disabled?: boolean;
}) {
  function update(i: number, patch: Partial<KeyValueRow>) {
    onRowsChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function remove(i: number) {
    onRowsChange(rows.filter((_, idx) => idx !== i));
  }
  return (
    <div>
      <table className="kv-table">
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <td>
                <TextInput
                  value={row.key}
                  placeholder={keyPlaceholder}
                  disabled={disabled}
                  onChange={(e) => update(i, { key: e.target.value })}
                />
              </td>
              <td>
                <TextInput
                  value={row.value}
                  placeholder={valuePlaceholder}
                  disabled={disabled}
                  onChange={(e) => update(i, { value: e.target.value })}
                />
              </td>
              <td className="kv-remove">
                <IconButton
                  aria-label={`Remove row ${i + 1}`}
                  icon={<Trash2 size={14} />}
                  disabled={disabled}
                  onClick={() => remove(i)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button
        variant="ghost"
        size="sm"
        icon={<Plus size={14} />}
        disabled={disabled}
        onClick={() => onRowsChange([...rows, { key: "", value: "" }])}
      >
        {addLabel}
      </Button>
    </div>
  );
}
