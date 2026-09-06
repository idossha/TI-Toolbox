import * as PopoverPrimitive from "@radix-ui/react-popover";
import { Command } from "cmdk";
import { Check, ChevronDown, X } from "lucide-react";
import { useState } from "react";
import { usePageActive } from "../app/pageActivity";
import { cn } from "./utils";

export interface ComboboxOption {
  value: string;
  label: string;
}

/**
 * Every option carries its own **name** and its own **value**, rather than leaving both to be
 * inferred from whatever the label happens to print.
 *
 * The failure this prevents, measured (lane SCC §6.6, on the container): a spec holding exactly
 * what the server gave it — a region's `hemi`, `id` and `name` — could not address the option the
 * picker renders for it, because reconstructing the accessible name meant also knowing which
 * separator this component chose to print between the hemisphere and the name ("L · bankssts",
 * U+00B7 with a space each side). Both real scene specs work around it with a `/^L/` regex over
 * the label. `aria-label` names the option explicitly with the same string it shows (so no
 * accessible name changes), and `data-option-value` is the identity a caller already has.
 */
function optionAttrs(opt: ComboboxOption): { "aria-label": string; "data-option-value": string } {
  return { "aria-label": opt.label, "data-option-value": opt.value };
}

export function Combobox({
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyMessage = "No matches.",
  loading = false,
  disabled,
  id,
  "aria-label": ariaLabel,
}: {
  value: string | undefined;
  onValueChange: (value: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  /** True while an async option source is fetching. */
  loading?: boolean;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}) {
  const active = usePageActive();
  const [open, setOpen] = useState(false);
  // The portal unmounts on tab switches; the unfinished search belongs to its retained page.
  const [search, setSearch] = useState("");
  const selected = options.find((o) => o.value === value);

  function changeOpen(next: boolean) {
    if (!active || disabled) return;
    setOpen(next);
    if (!next) setSearch("");
  }

  return (
    <PopoverPrimitive.Root open={active && open} onOpenChange={changeOpen}>
      <PopoverPrimitive.Trigger asChild>
        <button
          id={id}
          type="button"
          disabled={disabled}
          className="combobox-trigger"
          data-placeholder={selected ? undefined : ""}
          aria-label={ariaLabel}
          title={selected?.label}
        >
          <span className="picker-value">{selected?.label ?? placeholder}</span>
          <ChevronDown className="picker-chevron" size={14} aria-hidden />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          className="popover-content combobox-popover"
          sideOffset={4}
          align="start"
          collisionPadding={8}
          onCloseAutoFocus={(event) => { if (!active) event.preventDefault(); }}
        >
          <Command loop>
            <Command.Input className="control combobox-search" placeholder={searchPlaceholder} value={search} onValueChange={setSearch} />
            <Command.List className="combobox-list">
              {loading && <Command.Loading className="combobox-empty">Loading…</Command.Loading>}
              {!loading && <Command.Empty className="combobox-empty">{emptyMessage}</Command.Empty>}
              {options.map((opt) => (
                <Command.Item
                  key={opt.value}
                  value={opt.label}
                  className="combobox-option"
                  {...optionAttrs(opt)}
                  onSelect={() => {
                    onValueChange(opt.value);
                    changeOpen(false);
                  }}
                >
                  <span className="picker-option-mark" aria-hidden>
                    {opt.value === value && <Check size={14} />}
                  </span>
                  <span className="picker-option-label">{opt.label}</span>
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

export function MultiSelect({
  values,
  onValuesChange,
  options,
  placeholder = "Add…",
  disabled,
  id,
  "aria-label": ariaLabel,
}: {
  values: string[];
  onValuesChange: (values: string[]) => void;
  options: ComboboxOption[];
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}) {
  const active = usePageActive();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const labelOf = (v: string) => options.find((o) => o.value === v)?.label ?? v;
  const remaining = options.filter((o) => !values.includes(o.value));

  function changeOpen(next: boolean) {
    if (!active || disabled) return;
    setOpen(next);
    if (!next) setSearch("");
  }

  function remove(v: string) {
    onValuesChange(values.filter((x) => x !== v));
  }

  return (
    <PopoverPrimitive.Root open={active && open && !disabled} onOpenChange={changeOpen}>
      <PopoverPrimitive.Trigger asChild>
        <div
          id={id}
          role="combobox"
          aria-expanded={active && open && !disabled}
          aria-disabled={disabled || undefined}
          aria-label={ariaLabel}
          tabIndex={disabled ? -1 : 0}
          className={cn("multi-select")}
          onKeyDown={(e) => {
            if (disabled) return;
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              changeOpen(true);
            }
          }}
        >
          {values.map((v) => (
            /* A selected option leaves the list, so the chip is the only thing left to address it
               by — same identity, same attribute name, so a caller does not need to know which of
               the two it is looking at. */
            <span key={v} className="multi-select-chip" data-option-value={v}>
              {labelOf(v)}
              <button
                type="button"
                aria-label={`Remove ${labelOf(v)}`}
                disabled={disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  remove(v);
                }}
              >
                <X size={10} />
              </button>
            </span>
          ))}
          {values.length === 0 && <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{placeholder}</span>}
        </div>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          className="popover-content combobox-popover"
          sideOffset={4}
          align="start"
          collisionPadding={8}
          onCloseAutoFocus={(event) => { if (!active) event.preventDefault(); }}
        >
          <Command loop>
            <Command.Input className="control combobox-search" placeholder="Search…" value={search} onValueChange={setSearch} />
            <Command.List className="combobox-list">
              <Command.Empty className="combobox-empty">No more options.</Command.Empty>
              {remaining.map((opt) => (
                <Command.Item
                  key={opt.value}
                  value={opt.label}
                  className="combobox-option"
                  {...optionAttrs(opt)}
                  onSelect={() => onValuesChange([...values, opt.value])}
                >
                  {opt.label}
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
