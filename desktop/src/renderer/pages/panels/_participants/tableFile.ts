/** Local participant-table interchange. Headers are explicit; malformed imports never replace rows. */
export const CLUSTER_COLUMNS = ["subject_id", "simulation_name", "response", "effect_size", "weight"] as const;
export const AVERAGE_COLUMNS = ["subject_id", "simulation_name", "group"] as const;
export type TableRecord = Record<string, string>;

export function parseTable(text: string, columns: readonly string[], delimiter: "," | "\t"): TableRecord[] {
  const source = text.replace(/^\uFEFF/, "");
  const records: string[][] = [];
  let row: string[] = [], cell = "", quoted = false, closed = false;
  const endCell = () => { row.push(cell); cell = ""; closed = false; };
  const endRow = () => { endCell(); if (row.length > 1 || row.some((value) => value !== "")) records.push(row); row = []; };
  for (let i = 0; i < source.length; i++) {
    const char = source[i]!;
    if (quoted) {
      if (char === '"') {
        if (source[i + 1] === '"') { cell += '"'; i++; }
        else { quoted = false; closed = true; }
      } else cell += char;
    } else if (char === delimiter) endCell();
    else if (char === "\r" || char === "\n") { endRow(); if (char === "\r" && source[i + 1] === "\n") i++; }
    else if (char === '"' && cell === "" && !closed) quoted = true;
    else {
      if (closed || char === '"') throw new Error("Invalid quoting in participant table.");
      cell += char;
    }
  }
  if (quoted) throw new Error("Unclosed quoted field in participant table.");
  if (cell !== "" || row.length > 0 || closed) endRow();
  const header = records.shift()?.map((value) => value.trim());
  if (!header || header.length !== columns.length || new Set(header).size !== header.length || columns.some((name) => !header.includes(name))) {
    throw new Error(`Expected columns: ${columns.join(", ")}.`);
  }
  if (records.length === 0) throw new Error("The table contains no participant rows.");
  return records.map((values, index) => {
    if (values.length !== header.length) throw new Error(`Row ${index + 2}: expected ${header.length} fields.`);
    const record = Object.fromEntries(header.map((name, i) => [name, values[i]!.trim()]));
    for (const name of ["subject_id", "simulation_name", ...(columns.includes("group") ? ["group"] : [])]) {
      if (!record[name]) throw new Error(`Row ${index + 2}: ${name} is required.`);
    }
    if (columns.includes("response")) {
      if (record.response !== "0" && record.response !== "1") throw new Error(`Row ${index + 2}: response must be 0 or 1.`);
      for (const name of ["effect_size", "weight"]) {
        const value = record[name]!;
        if (value !== "" && (!Number.isFinite(Number(value)) || (name === "weight" && Number(value) <= 0))) {
          throw new Error(`Row ${index + 2}: ${name} must be ${name === "weight" ? "positive" : "a finite number"}.`);
        }
      }
    }
    return record;
  });
}

export function serializeTable(records: TableRecord[], columns: readonly string[], delimiter: "," | "\t"): string {
  const quote = (value: string) => /["\r\n,\t]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
  return [columns, ...records.map((record) => columns.map((name) => record[name] ?? ""))]
    .map((row) => row.map(quote).join(delimiter)).join("\r\n") + "\r\n";
}
