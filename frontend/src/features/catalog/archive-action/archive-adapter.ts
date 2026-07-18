import type { CatalogEntity } from "@/shared/api/query-keys";

/**
 * Единственное место, где живёт расхождение контракта (§9.6, К-D).
 *
 * Кнопки «Удалить» в проекте НЕТ вообще (SV-8; DELETE отсутствует и на бэке).
 * Единственный необратимый-на-вид жест — «В архив», всегда PATCH.
 * units архивируются через is_active=false, остальные — через status='archived'.
 * Если словарь когда-нибудь унифицируют до status — правится этот один файл.
 */

interface ArchivableRow {
  is_active?: boolean;
  status?: "active" | "archived";
}

/** Тело PATCH для перевода в архив / из архива. */
export function archiveBody(entity: CatalogEntity, archive: boolean): Record<string, unknown> {
  if (entity === "units") {
    return { is_active: !archive };
  }
  return { status: archive ? "archived" : "active" };
}

/** Признак «строка в архиве» по адаптированному полю. */
export function isRowArchived(entity: CatalogEntity, row: ArchivableRow): boolean {
  if (entity === "units") {
    return row.is_active === false;
  }
  return row.status === "archived";
}
