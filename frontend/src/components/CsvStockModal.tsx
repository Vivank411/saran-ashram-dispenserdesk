import { useState, useRef } from "react";
import { api } from "../api/client";
import { Icon } from "./Icon";
import { useToast } from "./Toasts";
import { Field, Modal } from "./ui";

interface CsvRowPreview {
  code?: string;
  name?: string;
  unit?: string;
  stock?: string;
  rate?: string;
  cost?: string;
  company?: string;
}

export default function CsvStockModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [csvText, setCsvText] = useState("");
  const [fileName, setFileName] = useState("");
  const [mode, setMode] = useState<"set_count" | "add_stock">("set_count");
  const [reason, setReason] = useState("CSV physical stock update");
  const [preview, setPreview] = useState<CsvRowPreview[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function parsePreview(text: string) {
    const lines = text
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length < 2) {
      setPreview([]);
      setRowCount(0);
      return;
    }
    const headers = lines[0]
      .split(",")
      .map((h) => h.trim().toLowerCase().replace(/["\s]/g, "_"));
    const rows: CsvRowPreview[] = [];
    for (let i = 1; i < Math.min(lines.length, 6); i++) {
      const vals = lines[i].split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
      const row: Record<string, string> = {};
      headers.forEach((h, idx) => {
        row[h] = vals[idx] || "";
      });
      rows.push({
        code: row.code || row.id,
        name: row.name || row.medicine_name || row.medicine,
        unit: row.unit,
        stock: row.stock || row.qty || row.quantity,
        rate: row.rate || row.price || row.selling_rate,
        cost: row.cost,
        company: row.company,
      });
    }
    setRowCount(lines.length - 1);
    setPreview(rows);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = (event.target?.result as string) || "";
      setCsvText(text);
      parsePreview(text);
    };
    reader.readAsText(file);
  }

  async function handleDownloadSample() {
    try {
      const res = await api.get("/medicines/export-csv", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute(
        "download",
        `stock_template_${new Date().toISOString().slice(0, 10)}.csv`
      );
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast("Downloaded stock template CSV");
    } catch {
      toast("Could not download template", "error");
    }
  }

  async function handleSubmit() {
    if (!csvText.trim()) {
      toast("Please select a CSV file first", "warn");
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await api.post<{
        updated: number;
        created: number;
        errors?: string[];
        alerts?: string[];
      }>("/medicines/import-csv", {
        csv_content: csvText,
        mode,
        reason: reason.trim() || "CSV Stock Update",
      });

      const { updated, created, errors, alerts } = res.data;
      toast(`Stock updated: ${updated} updated, ${created} created.`);
      if (alerts && alerts.length > 0) {
        alerts.forEach((msg) => toast(msg, "warn"));
      }
      if (errors && errors.length > 0) {
        toast(`${errors.length} rows had warnings or skipped.`, "warn");
      }
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const errorMsg =
        (err as { response?: { data?: { error?: { message?: string } } } })?.response
          ?.data?.error?.message || "Failed to import CSV";
      toast(errorMsg, "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Modal
      title="Upload Stock CSV"
      onClose={onClose}
      sub="Bulk update stock quantities, selling rates, and medicines from a CSV spreadsheet."
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={isSubmitting || !csvText.trim()}
          >
            <Icon name="upload" className="h-4 w-4" />
            {isSubmitting ? "Importing..." : `Apply CSV (${rowCount} items)`}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {/* Helper bar */}
        <div className="flex items-center justify-between rounded-md border border-neutral-200 bg-neutral-50 p-3 text-xs text-muted dark:border-neutral-800 dark:bg-neutral-900">
          <div>
            Format: <span className="font-mono text-ink font-medium">code, name, unit, stock, rate, cost, mrp, company</span>
          </div>
          <button
            type="button"
            className="btn btn-sm"
            onClick={handleDownloadSample}
          >
            <Icon name="download" className="h-3.5 w-3.5" />
            Download Current Stock CSV
          </button>
        </div>

        {/* Update Mode */}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Stock Update Mode">
            <select
              className="input"
              value={mode}
              onChange={(e) => setMode(e.target.value as "set_count" | "add_stock")}
            >
              <option value="set_count">Set Count (Physical count correction)</option>
              <option value="add_stock">Add Stock (Receive shipment/receipt)</option>
            </select>
          </Field>
          <Field label="Reason / Reference">
            <input
              className="input"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Audit Count Nov 2026, Invoice #1234"
            />
          </Field>
        </div>

        {/* File Picker */}
        <Field label="Select CSV File">
          <div
            onClick={() => fileInputRef.current?.click()}
            className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-neutral-300 p-5 text-center transition hover:border-accent hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900"
          >
            <Icon name="upload" className="mb-2 h-7 w-7 text-muted" />
            <span className="text-sm font-semibold text-ink">
              {fileName ? fileName : "Click to choose CSV file"}
            </span>
            <span className="mt-1 text-xs text-muted">
              {fileName
                ? `${rowCount} rows ready to import`
                : "Supports .csv files exported from Excel, Tally, or Google Sheets"}
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>
        </Field>

        {/* Preview Table */}
        {preview.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <div className="text-xs font-semibold text-ink">
              Preview (Showing first {preview.length} of {rowCount} rows):
            </div>
            <div className="max-h-40 overflow-auto rounded border border-neutral-200 text-xs dark:border-neutral-800">
              <table className="w-full text-left">
                <thead className="bg-neutral-100 text-[11px] uppercase tracking-wider text-muted dark:bg-neutral-800">
                  <tr>
                    <th className="p-1.5">Code</th>
                    <th className="p-1.5">Name</th>
                    <th className="p-1.5">Unit</th>
                    <th className="p-1.5 text-right">Stock</th>
                    <th className="p-1.5 text-right">Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                  {preview.map((r, i) => (
                    <tr key={i} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50">
                      <td className="p-1.5 font-mono">{r.code || "—"}</td>
                      <td className="p-1.5 font-medium">{r.name || "—"}</td>
                      <td className="p-1.5 text-muted">{r.unit || "—"}</td>
                      <td className="p-1.5 text-right font-semibold text-ink">{r.stock || "—"}</td>
                      <td className="p-1.5 text-right text-muted">{r.rate || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
