import { useState } from "react";
import { toast } from "sonner";
import { FileSpreadsheet, FileText } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { exportReport } from "@/entities/report/api/export";
import { ApiError } from "@/shared/api/errors";

type Q = Record<string, string | number | boolean | undefined>;

interface ExportButtonsProps {
  path: string;
  name: string;
  params: Q;
  /** Выгрузка недоступна (напр. ДДС без обязательной категории). */
  disabled?: boolean;
}

/** Кнопки экспорта отчёта в xlsx/pdf (ТЗ §8). Качают файл blob'ом. */
export function ExportButtons({ path, name, params, disabled }: ExportButtonsProps) {
  const [busy, setBusy] = useState<"xlsx" | "pdf" | null>(null);

  async function run(format: "xlsx" | "pdf") {
    setBusy(format);
    try {
      await exportReport(path, name, params, format);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Не удалось выгрузить отчёт");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => run("xlsx")} disabled={disabled || busy !== null}>
        <FileSpreadsheet className="h-4 w-4" />
        {busy === "xlsx" ? "Выгрузка…" : "Excel"}
      </Button>
      <Button variant="outline" size="sm" onClick={() => run("pdf")} disabled={disabled || busy !== null}>
        <FileText className="h-4 w-4" />
        {busy === "pdf" ? "Выгрузка…" : "PDF"}
      </Button>
    </div>
  );
}
