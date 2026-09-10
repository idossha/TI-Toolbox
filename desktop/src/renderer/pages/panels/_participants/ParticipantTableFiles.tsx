import { useRef, useState } from "react";
import { Button } from "../../../ui/Button";
import { notify } from "../../../ui/Toast";
import { parseTable, serializeTable, type TableRecord } from "./tableFile";

export function ParticipantTableFiles({ columns, records, onImport, filename }: {
  columns: readonly string[];
  records: TableRecord[];
  onImport: (records: TableRecord[]) => void;
  filename: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  async function download(delimiter: "," | "\t") {
    const extension = delimiter === "," ? "csv" : "tsv";
    setBusy(true);
    try {
      const text = serializeTable(records, columns, delimiter);
      const name = `${filename}.${extension}`;
      // Electron requires its save bridge; blob downloads work only in the browser build.
      if (window.tit?.saveFile) {
        const result = await window.tit.saveFile(text, {
          defaultName: name,
          filters: [{ name: `${extension.toUpperCase()} participant table`, extensions: [extension] }],
        });
        if (!result.ok && "canceled" in result && result.canceled) return;
        if (!result.ok) throw new Error("reason" in result ? result.reason : "Could not write participant file.");
        return;
      }
      const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      notify.error(error instanceof Error ? error.message : "Could not export participant file.");
    } finally { setBusy(false); }
  }
  return (
    <div className="participants-field-tools" aria-label="Participant table files">
      <input ref={input} type="file" accept=".csv,.tsv" hidden onChange={async (event) => {
        const file = event.currentTarget.files?.[0];
        event.currentTarget.value = "";
        if (!file) return;
        setBusy(true);
        try {
          if (file.size > 5 * 1024 * 1024) throw new Error("Participant files must be smaller than 5 MB.");
          if (!/\.(csv|tsv)$/i.test(file.name)) throw new Error("Choose a .csv or .tsv file.");
          const imported = parseTable(await file.text(), columns, /\.tsv$/i.test(file.name) ? "\t" : ",");
          onImport(imported);
          notify.success(`Imported ${imported.length} participant rows.`);
        } catch (error) {
          notify.error(error instanceof Error ? error.message : "Could not read participant file.");
        } finally { setBusy(false); }
      }} />
      <Button size="sm" variant="secondary" disabled={busy} title="Import replaces the table after every row passes validation." onClick={() => input.current?.click()}>Import CSV/TSV</Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => download(",")}>Export CSV</Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => download("\t")}>Export TSV</Button>
    </div>
  );
}
