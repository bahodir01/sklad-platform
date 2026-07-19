import { api } from "@/shared/api/client";
import { downloadBlob } from "@/shared/lib/download";
import { todayIso } from "@/shared/lib/format";

type Q = Record<string, string | number | boolean | undefined>;

const EXT: Record<"xlsx" | "pdf", string> = { xlsx: "xlsx", pdf: "pdf" };

/**
 * Экспорт отчёта файлом: GET {path}?format=xlsx|pdf (ТЗ §8). Качаем blob'ом
 * (Authorization в памяти) и сохраняем. `name` — префикс имени файла.
 */
export async function exportReport(
  path: string,
  name: string,
  params: Q,
  format: "xlsx" | "pdf",
): Promise<void> {
  const blob = await api.getBlob(path, { ...params, format });
  downloadBlob(blob, `${name}-${todayIso()}.${EXT[format]}`);
}
