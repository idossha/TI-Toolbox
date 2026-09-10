/**
 * Renders one form control from a JSON-schema property, when the generic mapping is enough:
 * enum -> Select, boolean -> Switch, number/integer -> NumberInput, array of strings -> MultiSelect,
 * anything else -> TextInput. Pages reach for this on plain scalar/enum fields and drop back to a
 * hand-built `Field` + ui primitive for anything schema-shaped fields don't cover well (nested
 * objects, coordinate triples, electrode pairs, ...).
 */
import type { ReactNode } from "react";
import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";
import { Field, TextInput } from "../ui/Field";
import { NumberInput } from "../ui/NumberInput";
import { Select } from "../ui/Select";
import { Switch } from "../ui/Toggle";
import { MultiSelect } from "../ui/Combobox";
import type { SchemaProperty } from "./schema";

export function SchemaField<T extends FieldValues>({
  name,
  control,
  property,
  label,
  required = false,
  error,
}: {
  name: Path<T>;
  control: Control<T>;
  property: SchemaProperty;
  label?: string;
  required?: boolean;
  error?: string;
}) {
  const fieldLabel = label ?? property.title ?? String(name);
  const help = property.description;

  return (
    <Controller
      name={name}
      control={control}
      render={({ field }) => {
        let control_: ReactNode;

        if (property.enum) {
          const options = property.enum.map((v) => ({ value: String(v), label: String(v) }));
          control_ = (
            <Select
              value={field.value === undefined ? undefined : String(field.value)}
              onValueChange={field.onChange}
              options={options}
              invalid={Boolean(error)}
            />
          );
        } else if (property.type === "boolean") {
          control_ = <Switch checked={Boolean(field.value)} onCheckedChange={field.onChange} aria-label={fieldLabel} />;
        } else if (property.type === "number" || property.type === "integer") {
          control_ = (
            <NumberInput
              value={field.value === undefined || field.value === null ? undefined : Number(field.value)}
              onValueChange={field.onChange}
              min={property.minimum}
              max={property.maximum}
              step={property.type === "integer" ? 1 : undefined}
              invalid={Boolean(error)}
            />
          );
        } else if (property.type === "array" && property.items?.type === "string") {
          const options = (property.items.enum ?? []).map((v) => ({ value: String(v), label: String(v) }));
          const values: string[] = Array.isArray(field.value) ? field.value : [];
          control_ = <MultiSelect values={values} onValuesChange={field.onChange} options={options} />;
        } else {
          control_ = (
            <TextInput
              value={field.value ?? ""}
              onChange={(e) => field.onChange(e.target.value)}
              invalid={Boolean(error)}
            />
          );
        }

        return (
          <Field label={fieldLabel} required={required} help={help} error={error}>
            {control_}
          </Field>
        );
      }}
    />
  );
}
